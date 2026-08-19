from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sms.core.repository import AbstractRepository
from sms.core.security import hash_password, hash_token
from sms.domains.auth.exceptions import InvalidCredentialsError, InvalidRefreshTokenError
from sms.domains.auth.models import Session, User, UserRole
from sms.domains.auth.schemas import LoginRequest, TokenResponse
from sms.domains.auth.service import AuthService


class FakeUserRepository(AbstractRepository[User]):
    """In-memory stand-in for UserRepository, backed by a plain dict. Same
    style as FakeStudentRepository in tests/domains/students/test_service.py
    — implements the full AbstractRepository contract plus the
    domain-specific get_by_email lookup so AuthService can be unit tested
    without a database."""

    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    async def add(self, entity: User) -> User:
        if entity.id is None:
            entity.id = uuid4()
        self._users[entity.id] = entity
        return entity

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
def service(
    repository: FakeUserRepository, session_repository: FakeSessionRepository
) -> AuthService:
    # login() now also creates a Session (see sms.domains.auth.service),
    # so every service instance needs both repositories wired even for
    # tests that only exercise the pre-existing login/credentials paths.
    return AuthService(repository, session_repository)


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
