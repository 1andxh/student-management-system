from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.teachers.exceptions import (
    TeacherAlreadyExistsError,
    TeacherNotFoundError,
)
from sms.domains.teachers.models import Teacher
from sms.domains.teachers.schemas import TeacherCreate, TeacherUpdate
from sms.domains.teachers.service import TeacherService

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

    async def add(self, entity: Teacher) -> Teacher:
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
def service(repository: FakeTeacherRepository) -> TeacherService:
    return TeacherService(repository)


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


async def test_create_duplicate_user_id_raises(service: TeacherService) -> None:
    user_id = uuid4()
    await service.create(make_teacher_create(email="one@example.com", user_id=user_id))

    with pytest.raises(TeacherAlreadyExistsError):
        await service.create(make_teacher_create(email="two@example.com", user_id=user_id))


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
