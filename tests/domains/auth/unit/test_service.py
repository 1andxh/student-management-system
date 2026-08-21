from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sms.core.repository import AbstractRepository
from sms.core.security import hash_password, hash_token
from sms.domains.auth.exceptions import InvalidCredentialsError, InvalidRefreshTokenError
from sms.domains.auth.models import Session
from sms.domains.auth.schemas import LoginRequest, PinLoginRequest, TokenResponse
from sms.domains.auth.service import AuthService
from sms.domains.students.models import EnrollmentStatus, Student
from sms.domains.users.models import User, UserRole

# One-directional import (not the reverse) to avoid a circular import between
# this module and tests/domains/students/unit/test_service.py — see that
# file's comment for why it defines its own local FakeUserRepository instead
# of importing this module's. FakeStudentRepository already implements
# everything AuthService.login_with_pin needs (get_by_student_number), so
# there's no reason to duplicate that fake here.
from tests.domains.students.unit.test_service import FakeStudentRepository


def _make_student(**overrides: object) -> Student:
    """Builds a Student directly (not via StudentCreate/StudentService),
    since login_with_pin's test scenarios need control over pin_hash and
    user_id — fields StudentCreate doesn't carry (pin_hash is only ever set
    via StudentService.generate_pin in real usage)."""
    defaults: dict[str, object] = {
        "id": uuid4(),
        "student_number": "STU-0001",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": date(2010, 1, 1),
        "email": "pin-student@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
        "enrollment_status": EnrollmentStatus.ACTIVE,
        "user_id": None,
        "pin_hash": None,
    }
    defaults.update(overrides)
    return Student(**defaults)


class FakeUserRepository(AbstractRepository[User]):
    """In-memory stand-in for UserRepository, backed by a plain dict. Same
    style as FakeStudentRepository in tests/domains/students/test_service.py
    — implements the full AbstractRepository contract plus the
    domain-specific get_by_email lookup so AuthService can be unit tested
    without a database."""

    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    async def add(self, entity: User, *, commit: bool = True) -> User:
        # commit is accepted but irrelevant here — there's no real
        # transaction to defer, this just matches the real
        # UserRepository.add's signature. See docs/adr/0011.
        if entity.id is None:
            entity.id = uuid4()
        self._users[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> User | None:
        return self._users.get(entity_id)

    async def list(self) -> list[User]:
        return list(self._users.values())

    async def remove(self, entity: User) -> None:
        self._users.pop(entity.id, None)

    async def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email:
                return user
        return None

    async def count_active_super_admins(self) -> int:
        return sum(
            1
            for user in self._users.values()
            if user.role == UserRole.SUPER_ADMIN and user.is_active
        )


class FakeSessionRepository(AbstractRepository[Session]):
    """In-memory stand-in for SessionRepository, backed by a plain dict —
    same style as FakeUserRepository above. Adds the domain-specific
    get_by_token_hash lookup so AuthService.refresh/logout can be unit
    tested without a database. Entities are stored by reference, so tests
    can mutate a fetched Session (e.g. expires_at, revoked_at) in place to
    set up expired/revoked scenarios without a separate update method."""

    def __init__(self) -> None:
        self._sessions: dict[UUID, Session] = {}

    async def add(self, entity: Session) -> Session:
        if entity.id is None:
            entity.id = uuid4()
        self._sessions[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Session | None:
        return self._sessions.get(entity_id)

    async def list(self) -> list[Session]:
        return list(self._sessions.values())

    async def remove(self, entity: Session) -> None:
        self._sessions.pop(entity.id, None)

    async def get_by_token_hash(self, refresh_token_hash: str) -> Session | None:
        for session in self._sessions.values():
            if session.refresh_token_hash == refresh_token_hash:
                return session
        return None

    async def rotate(
        self,
        old_hash: str,
        new_hash: str,
        now: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        # Not truly atomic (no concurrency in these tests), but matches
        # the real SessionRepository.rotate's contract: fails if old_hash
        # no longer matches a non-revoked session.
        session = await self.get_by_token_hash(old_hash)
        if session is None or session.revoked_at is not None:
            return False
        session.refresh_token_hash = new_hash
        session.last_used_at = now
        session.user_agent = user_agent
        session.ip_address = ip_address
        return True


def make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "email": "ada@example.com",
        "hashed_password": hash_password("correct-horse"),
        "role": UserRole.ADMIN,
        "is_active": True,
    }
    defaults.update(overrides)
    return User(**defaults)


@pytest.fixture
def repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def session_repository() -> FakeSessionRepository:
    return FakeSessionRepository()


@pytest.fixture
def student_repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def service(
    repository: FakeUserRepository,
    session_repository: FakeSessionRepository,
    student_repository: FakeStudentRepository,
) -> AuthService:
    return AuthService(repository, session_repository, student_repository)


async def test_login_success(service: AuthService, repository: FakeUserRepository) -> None:
    await repository.add(make_user(email="ada@example.com"))

    result = await service.login(LoginRequest(email="ada@example.com", password="correct-horse"))

    assert isinstance(result, TokenResponse)
    assert result.token_type == "bearer"
    assert result.access_token
    assert len(result.access_token) > 0


async def test_login_wrong_password_raises(
    service: AuthService, repository: FakeUserRepository
) -> None:
    await repository.add(make_user(email="ada@example.com"))

    with pytest.raises(InvalidCredentialsError):
        await service.login(LoginRequest(email="ada@example.com", password="wrong-password"))


async def test_login_unknown_email_raises(service: AuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        await service.login(LoginRequest(email="nobody@example.com", password="whatever"))


async def test_login_inactive_user_raises(
    service: AuthService, repository: FakeUserRepository
) -> None:
    # Same InvalidCredentialsError as any other login failure, deliberately
    # — a distinct "inactive account" message would leak account state to
    # an unauthenticated caller. See docs/adr/0008.
    await repository.add(
        make_user(email="inactive@example.com", is_active=False, hashed_password=hash_password("pw"))
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login(LoginRequest(email="inactive@example.com", password="pw"))


async def test_login_returns_non_empty_refresh_token(
    service: AuthService, repository: FakeUserRepository
) -> None:
    await repository.add(make_user(email="ada@example.com"))

    result = await service.login(LoginRequest(email="ada@example.com", password="correct-horse"))

    assert result.refresh_token
    assert len(result.refresh_token) > 0


async def test_refresh_with_valid_token_returns_new_token_response(
    service: AuthService, repository: FakeUserRepository
) -> None:
    await repository.add(make_user(email="ada@example.com"))
    login_result = await service.login(
        LoginRequest(email="ada@example.com", password="correct-horse")
    )

    refreshed = await service.refresh(login_result.refresh_token)

    assert isinstance(refreshed, TokenResponse)
    assert refreshed.access_token
    assert refreshed.refresh_token


async def test_refresh_rotates_old_token_stops_working(
    service: AuthService, repository: FakeUserRepository
) -> None:
    await repository.add(make_user(email="ada@example.com"))
    login_result = await service.login(
        LoginRequest(email="ada@example.com", password="correct-horse")
    )
    old_refresh_token = login_result.refresh_token

    await service.refresh(old_refresh_token)

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(old_refresh_token)


async def test_refresh_with_unknown_token_raises(service: AuthService) -> None:
    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh("this-token-was-never-issued")


async def test_refresh_with_expired_session_raises(
    service: AuthService,
    repository: FakeUserRepository,
    session_repository: FakeSessionRepository,
) -> None:
    await repository.add(make_user(email="ada@example.com"))
    login_result = await service.login(
        LoginRequest(email="ada@example.com", password="correct-horse")
    )
    session = await session_repository.get_by_token_hash(hash_token(login_result.refresh_token))
    assert session is not None
    session.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(login_result.refresh_token)


async def test_refresh_with_revoked_session_raises(
    service: AuthService,
    repository: FakeUserRepository,
    session_repository: FakeSessionRepository,
) -> None:
    await repository.add(make_user(email="ada@example.com"))
    login_result = await service.login(
        LoginRequest(email="ada@example.com", password="correct-horse")
    )
    session = await session_repository.get_by_token_hash(hash_token(login_result.refresh_token))
    assert session is not None
    session.revoked_at = datetime.now(timezone.utc)

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(login_result.refresh_token)


async def test_logout_revokes_session(
    service: AuthService, repository: FakeUserRepository
) -> None:
    await repository.add(make_user(email="ada@example.com"))
    login_result = await service.login(
        LoginRequest(email="ada@example.com", password="correct-horse")
    )

    await service.logout(login_result.refresh_token)

    with pytest.raises(InvalidRefreshTokenError):
        await service.refresh(login_result.refresh_token)


async def test_logout_with_unknown_token_does_not_raise(service: AuthService) -> None:
    await service.logout("this-token-was-never-issued")


# ---------------------------------------------------------------------------
# login_with_pin
# ---------------------------------------------------------------------------


async def test_login_with_pin_success(
    service: AuthService,
    repository: FakeUserRepository,
    student_repository: FakeStudentRepository,
) -> None:
    user = await repository.add(make_user(email="pin-student@example.com", role=UserRole.STUDENT))
    await student_repository.add(
        _make_student(
            student_number="STU-PIN-1",
            email="pin-student@example.com",
            user_id=user.id,
            pin_hash=hash_password("123456"),
        )
    )

    result = await service.login_with_pin(
        PinLoginRequest(student_number="STU-PIN-1", pin="123456")
    )

    assert isinstance(result, TokenResponse)
    assert result.token_type == "bearer"
    assert result.access_token
    assert result.refresh_token


async def test_login_with_pin_wrong_pin_raises(
    service: AuthService,
    repository: FakeUserRepository,
    student_repository: FakeStudentRepository,
) -> None:
    user = await repository.add(make_user(email="pin-student2@example.com", role=UserRole.STUDENT))
    await student_repository.add(
        _make_student(
            student_number="STU-PIN-2",
            email="pin-student2@example.com",
            user_id=user.id,
            pin_hash=hash_password("123456"),
        )
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login_with_pin(
            PinLoginRequest(student_number="STU-PIN-2", pin="000000")
        )


async def test_login_with_pin_unknown_student_number_raises(service: AuthService) -> None:
    with pytest.raises(InvalidCredentialsError):
        await service.login_with_pin(
            PinLoginRequest(student_number="NO-SUCH-STUDENT", pin="123456")
        )


async def test_login_with_pin_no_pin_hash_set_raises(
    service: AuthService, student_repository: FakeStudentRepository
) -> None:
    await student_repository.add(
        _make_student(student_number="STU-PIN-3", email="pin-student3@example.com", pin_hash=None)
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login_with_pin(
            PinLoginRequest(student_number="STU-PIN-3", pin="123456")
        )


async def test_login_with_pin_no_linked_user_raises(
    service: AuthService, student_repository: FakeStudentRepository
) -> None:
    await student_repository.add(
        _make_student(
            student_number="STU-PIN-4",
            email="pin-student4@example.com",
            user_id=None,
            pin_hash=hash_password("123456"),
        )
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login_with_pin(
            PinLoginRequest(student_number="STU-PIN-4", pin="123456")
        )


async def test_login_with_pin_inactive_linked_user_raises(
    service: AuthService,
    repository: FakeUserRepository,
    student_repository: FakeStudentRepository,
) -> None:
    user = await repository.add(
        make_user(email="pin-student5@example.com", role=UserRole.STUDENT, is_active=False)
    )
    await student_repository.add(
        _make_student(
            student_number="STU-PIN-5",
            email="pin-student5@example.com",
            user_id=user.id,
            pin_hash=hash_password("123456"),
        )
    )

    with pytest.raises(InvalidCredentialsError):
        await service.login_with_pin(
            PinLoginRequest(student_number="STU-PIN-5", pin="123456")
        )
