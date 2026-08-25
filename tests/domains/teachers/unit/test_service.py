# FakeClassRepository below defines a method literally named `list`
# followed by `list_by_teacher_id`, whose return annotation is
# `list[Class]` — without this, that annotation would resolve `list`
# against the *method* named `list` already bound in the class namespace,
# not the builtin, and raise TypeError at class-definition time. Same fix
# as src/sms/domains/classes/repository.py's identical comment.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.core.security import DUMMY_PASSWORD_HASH, verify_password
from sms.domains.classes.models import Class
from sms.domains.teachers.exceptions import (
    TeacherAlreadyExistsError,
    TeacherHasNoLinkedRecordError,
    TeacherNotFoundError,
)
from sms.domains.teachers.models import Teacher
from sms.domains.teachers.schemas import TeacherCreate, TeacherCredentialsRead, TeacherUpdate
from sms.domains.teachers.service import TeacherService
from sms.domains.users.exceptions import UserNotFoundError
from sms.domains.users.models import User, UserRole

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing created_at stamps (see FakeTeacherRepository.add),
# same pattern as tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeTeacherRepository(AbstractRepository[Teacher]):
    """In-memory stand-in for TeacherRepository, backed by a plain dict.
    Implements the full AbstractRepository contract plus the two
    domain-specific lookups so TeacherService can be unit tested without a
    database. list() mirrors the real repository's pagination contract —
    see FakeStudentRepository.list() in the students unit tests for the
    same shape."""

    def __init__(self) -> None:
        self._teachers: dict[UUID, Teacher] = {}
        self._sequence = 0

    async def add(self, entity: Teacher, *, commit: bool = True) -> Teacher:
        # commit is accepted but irrelevant here — there's no real
        # transaction to defer, this just matches the real (post-Stage-10)
        # TeacherRepository.add's signature, mirroring
        # FakeStudentRepository.add in tests/domains/students/unit/
        # test_service.py.
        #
        # Mirrors the real uq_teachers_email / uq_teachers_user_id
        # constraints, same "pre-check narrows the window, doesn't close
        # it" reasoning as every other domain's create() (docs/adr/0004) —
        # TeacherService.update() pre-checks too, but this keeps the fake
        # faithful to what Postgres actually does if a race ever slips
        # past that pre-check, rather than only being correct by construction.
        for existing_id, existing in self._teachers.items():
            if existing_id == entity.id:
                continue
            if existing.email == entity.email:
                raise IntegrityError("duplicate email", params=None, orig=Exception())
            if entity.user_id is not None and existing.user_id == entity.user_id:
                raise IntegrityError("duplicate user_id", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._teachers[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> Teacher | None:
        return self._teachers.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Teacher], int]:
        all_teachers = sorted(
            self._teachers.values(), key=lambda t: t.created_at, reverse=True
        )
        return all_teachers[offset : offset + limit], len(all_teachers)

    async def remove(self, entity: Teacher) -> None:
        self._teachers.pop(entity.id, None)

    async def get_by_email(self, email: str) -> Teacher | None:
        for teacher in self._teachers.values():
            if teacher.email == email:
                return teacher
        return None

    async def get_by_user_id(self, user_id: UUID) -> Teacher | None:
        for teacher in self._teachers.values():
            if teacher.user_id == user_id:
                return teacher
        return None


class FakeUserRepository(AbstractRepository[User]):
    """Local, minimal stand-in for UserRepository — only what
    TeacherService.generate_credentials and _require_teacher_role_user need
    (create-or-reuse a linked User via the commit=False two-write pattern,
    plus get_by_email/get). Mirrors the local duplicate in
    tests/domains/students/unit/test_service.py — not shared/imported across
    domain test modules, same one-way-dependency reasoning documented
    there."""

    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    async def add(self, entity: User, *, commit: bool = True) -> User:
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


class FakeClassRepository(AbstractRepository[Class]):
    """Minimal in-memory stand-in for ClassRepository — TeacherService.
    get_my_classes only ever calls list_by_teacher_id on it."""

    def __init__(self) -> None:
        self._classes: dict[UUID, Class] = {}

    async def add(self, entity: Class) -> Class:
        if entity.id is None:
            entity.id = uuid4()
        self._classes[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Class | None:
        return self._classes.get(entity_id)

    async def list(self) -> list[Class]:
        return list(self._classes.values())

    async def remove(self, entity: Class) -> None:
        self._classes.pop(entity.id, None)

    async def list_by_teacher_id(self, teacher_id: UUID) -> list[Class]:
        return [c for c in self._classes.values() if c.teacher_id == teacher_id]


def make_teacher_create(**overrides: object) -> TeacherCreate:
    defaults: dict[str, object] = {
        "first_name": "Ada",
        "last_name": "Lovelace",
        "email": "ada@example.com",
        "hire_date": date(2020, 1, 1),
    }
    defaults.update(overrides)
    return TeacherCreate(**defaults)


@pytest.fixture
def repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def user_repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def service(
    repository: FakeTeacherRepository,
    user_repository: FakeUserRepository,
    class_repository: FakeClassRepository,
) -> TeacherService:
    return TeacherService(repository, user_repository, class_repository)


async def test_create_success(service: TeacherService) -> None:
    data = make_teacher_create()

    teacher = await service.create(data)

    assert teacher.id is not None
    assert teacher.first_name == "Ada"
    assert teacher.last_name == "Lovelace"
    assert teacher.email == "ada@example.com"
    assert teacher.hire_date == date(2020, 1, 1)
    assert teacher.user_id is None


async def test_create_duplicate_email_raises(service: TeacherService) -> None:
    await service.create(make_teacher_create(email="dup@example.com"))

    with pytest.raises(TeacherAlreadyExistsError):
        await service.create(make_teacher_create(email="dup@example.com"))


async def test_create_duplicate_user_id_raises(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    # Linked to a real TEACHER-role User — a valid link, otherwise the new
    # _require_teacher_role_user check (not the thing under test here) would
    # be what raises, not the duplicate-user_id path.
    user = await user_repository.add(
        User(
            email="linked-dup@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.TEACHER,
            is_active=True,
        )
    )
    await service.create(make_teacher_create(email="one@example.com", user_id=user.id))

    with pytest.raises(TeacherAlreadyExistsError):
        await service.create(make_teacher_create(email="two@example.com", user_id=user.id))


async def test_get_success(service: TeacherService) -> None:
    created = await service.create(make_teacher_create())

    fetched = await service.get(created.id)

    assert fetched.id == created.id
    assert fetched.email == created.email


async def test_get_missing_raises(service: TeacherService) -> None:
    with pytest.raises(TeacherNotFoundError):
        await service.get(uuid4())


async def test_list(service: TeacherService) -> None:
    await service.create(make_teacher_create(email="a@example.com"))
    await service.create(make_teacher_create(email="b@example.com"))

    teachers, total = await service.list(limit=50, offset=0)

    assert len(teachers) == 2
    assert total == 2
    assert {t.email for t in teachers} == {"a@example.com", "b@example.com"}


async def test_list_pagination_smoke(service: TeacherService) -> None:
    for i in range(3):
        await service.create(make_teacher_create(email=f"pg{i}@example.com"))

    page, total = await service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 3


async def test_update_success(service: TeacherService) -> None:
    created = await service.create(make_teacher_create())

    updated = await service.update(created.id, TeacherUpdate(first_name="Augusta"))

    assert updated.id == created.id
    assert updated.first_name == "Augusta"
    assert updated.last_name == "Lovelace"


async def test_update_missing_raises(service: TeacherService) -> None:
    with pytest.raises(TeacherNotFoundError):
        await service.update(uuid4(), TeacherUpdate(first_name="Nobody"))


async def test_delete_success(
    service: TeacherService, repository: FakeTeacherRepository
) -> None:
    created = await service.create(make_teacher_create())

    await service.delete(created.id)

    assert await repository.get(created.id) is None


async def test_delete_missing_raises(service: TeacherService) -> None:
    with pytest.raises(TeacherNotFoundError):
        await service.delete(uuid4())


# ---------------------------------------------------------------------------
# _require_teacher_role_user (exercised via create()/update())
# ---------------------------------------------------------------------------


async def test_create_with_valid_teacher_role_user_id_succeeds(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    user = await user_repository.add(
        User(
            email="valid-link@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.TEACHER,
            is_active=True,
        )
    )

    teacher = await service.create(make_teacher_create(email="linked1@example.com", user_id=user.id))

    assert teacher.user_id == user.id


async def test_create_with_non_teacher_role_user_id_raises(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    admin_user = await user_repository.add(
        User(
            email="wrong-role@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )

    with pytest.raises(UserNotFoundError):
        await service.create(
            make_teacher_create(email="linked2@example.com", user_id=admin_user.id)
        )


async def test_create_with_nonexistent_user_id_raises(service: TeacherService) -> None:
    with pytest.raises(UserNotFoundError):
        await service.create(make_teacher_create(email="linked3@example.com", user_id=uuid4()))


async def test_update_user_id_to_valid_teacher_role_succeeds(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    created = await service.create(make_teacher_create(email="preupdate1@example.com"))
    user = await user_repository.add(
        User(
            email="update-link@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.TEACHER,
            is_active=True,
        )
    )

    updated = await service.update(created.id, TeacherUpdate(user_id=user.id))

    assert updated.user_id == user.id


async def test_update_user_id_to_non_teacher_role_raises(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    created = await service.create(make_teacher_create(email="preupdate2@example.com"))
    student_role_user = await user_repository.add(
        User(
            email="update-wrong-role@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.STUDENT,
            is_active=True,
        )
    )

    with pytest.raises(UserNotFoundError):
        await service.update(created.id, TeacherUpdate(user_id=student_role_user.id))


# ---------------------------------------------------------------------------
# generate_credentials
# ---------------------------------------------------------------------------


async def test_generate_credentials_first_issuance_creates_linked_user(
    service: TeacherService,
    repository: FakeTeacherRepository,
    user_repository: FakeUserRepository,
) -> None:
    created = await service.create(
        make_teacher_create(email="creds1@example.com", hire_date=date(2021, 1, 1))
    )
    assert created.user_id is None

    result = await service.generate_credentials(created.id)

    assert isinstance(result, TeacherCredentialsRead)
    assert result.email == "creds1@example.com"
    assert len(result.password) > 0

    refreshed = await repository.get(created.id)
    assert refreshed is not None
    assert refreshed.user_id is not None

    linked_user = await user_repository.get(refreshed.user_id)
    assert linked_user is not None
    assert linked_user.email == created.email
    assert linked_user.role == UserRole.TEACHER
    assert linked_user.is_active is True
    assert verify_password(result.password, linked_user.hashed_password)
    # The generated password must never be stored as the fixed dummy hash —
    # that constant exists purely for login's constant-time oracle defense
    # (docs/adr/0008); reusing it as a real stored credential would let
    # anyone who knows the dummy value log in as this account.
    assert linked_user.hashed_password != DUMMY_PASSWORD_HASH


async def test_generate_credentials_first_issuance_email_collision_raises(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    await user_repository.add(
        User(
            email="taken@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    created = await service.create(make_teacher_create(email="taken@example.com"))

    with pytest.raises(TeacherAlreadyExistsError):
        await service.generate_credentials(created.id)


async def test_generate_credentials_reissuance_resets_password_without_creating_second_user(
    service: TeacherService,
    repository: FakeTeacherRepository,
    user_repository: FakeUserRepository,
) -> None:
    created = await service.create(make_teacher_create(email="creds2@example.com"))
    first_result = await service.generate_credentials(created.id)
    users_after_first = await user_repository.list()
    assert len(users_after_first) == 1
    linked_user_id = users_after_first[0].id

    second_result = await service.generate_credentials(created.id)

    users_after_second = await user_repository.list()
    assert len(users_after_second) == 1  # no second User created — reused the link
    assert users_after_second[0].id == linked_user_id
    assert second_result.password != first_result.password

    refreshed_user = await user_repository.get(linked_user_id)
    assert refreshed_user is not None
    assert verify_password(second_result.password, refreshed_user.hashed_password)
    # The old password must no longer work after a reset.
    assert not verify_password(first_result.password, refreshed_user.hashed_password)


async def test_generate_credentials_reissuance_existing_linked_user_not_teacher_role_raises(
    service: TeacherService,
    repository: FakeTeacherRepository,
    user_repository: FakeUserRepository,
) -> None:
    non_teacher_user = await user_repository.add(
        User(
            email="became-admin@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.ADMIN,
            is_active=True,
        )
    )
    created = await service.create(
        make_teacher_create(email="became-admin@example.com", user_id=None)
    )
    # Directly link the teacher to the (non-TEACHER) user, bypassing
    # create()/update()'s own role validation — simulates a row that
    # somehow ended up linked to an account whose role changed since, the
    # scenario generate_credentials's re-issuance branch must still guard
    # against.
    created.user_id = non_teacher_user.id
    await repository.add(created)

    with pytest.raises(UserNotFoundError):
        await service.generate_credentials(created.id)


async def test_generate_credentials_missing_teacher_raises(service: TeacherService) -> None:
    with pytest.raises(TeacherNotFoundError):
        await service.generate_credentials(uuid4())


# ---------------------------------------------------------------------------
# get_my_classes
# ---------------------------------------------------------------------------


def make_class_instance(**overrides: object) -> Class:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "subject_id": uuid4(),
        "term_id": uuid4(),
        "teacher_id": uuid4(),
        "capacity": 30,
        "room": "Room 101",
    }
    defaults.update(overrides)
    return Class(**defaults)


async def test_get_my_classes_returns_only_callers_classes(
    service: TeacherService,
    user_repository: FakeUserRepository,
    class_repository: FakeClassRepository,
) -> None:
    user = await user_repository.add(
        User(
            email="myclasses1@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.TEACHER,
            is_active=True,
        )
    )
    teacher = await service.create(make_teacher_create(email="myclasses1@example.com", user_id=user.id))
    owned = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    await class_repository.add(make_class_instance())  # someone else's class

    classes = await service.get_my_classes(user.id)

    assert [c.id for c in classes] == [owned.id]


async def test_get_my_classes_no_classes_returns_empty_list(
    service: TeacherService, user_repository: FakeUserRepository
) -> None:
    user = await user_repository.add(
        User(
            email="myclasses2@example.com",
            hashed_password="not-a-real-hash",
            role=UserRole.TEACHER,
            is_active=True,
        )
    )
    await service.create(make_teacher_create(email="myclasses2@example.com", user_id=user.id))

    classes = await service.get_my_classes(user.id)

    assert classes == []


async def test_get_my_classes_no_linked_teacher_record_raises(service: TeacherService) -> None:
    with pytest.raises(TeacherHasNoLinkedRecordError):
        await service.get_my_classes(uuid4())
