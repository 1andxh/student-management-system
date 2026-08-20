from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sms.core.repository import AbstractRepository
from sms.domains.students.exceptions import (
    StudentAlreadyExistsError,
    StudentNotFoundError,
)
from sms.domains.students.models import Student
from sms.domains.students.schemas import StudentCreate, StudentUpdate
from sms.domains.students.service import StudentService

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing created_at stamps (see FakeStudentRepository.add),
# same pattern as tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeStudentRepository(AbstractRepository[Student]):
    """In-memory stand-in for StudentRepository, backed by a plain dict.
    Implements the full AbstractRepository contract plus the two
    domain-specific lookups so StudentService can be unit tested without a
    database. list() mirrors the real repository's pagination contract:
    sorted newest-first by created_at, sliced by limit/offset, returning
    (items, total) — total reflects the full filtered set, not just the
    slice."""

    def __init__(self) -> None:
        self._students: dict[UUID, Student] = {}
        self._sequence = 0

    async def add(self, entity: Student) -> Student:
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._students[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Student | None:
        return self._students.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Student], int]:
        all_students = sorted(
            self._students.values(), key=lambda s: s.created_at, reverse=True
        )
        return all_students[offset : offset + limit], len(all_students)

    async def remove(self, entity: Student) -> None:
        self._students.pop(entity.id, None)

    async def get_by_email(self, email: str) -> Student | None:
        for student in self._students.values():
            if student.email == email:
                return student
        return None

    async def get_by_student_number(self, student_number: str) -> Student | None:
        for student in self._students.values():
            if student.student_number == student_number:
                return student
        return None


def make_student_create(**overrides: object) -> StudentCreate:
    defaults: dict[str, object] = {
        "student_number": "S-0001",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": date(2010, 1, 1),
        "email": "ada@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
    }
    defaults.update(overrides)
    return StudentCreate(**defaults)


@pytest.fixture
def repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def service(repository: FakeStudentRepository) -> StudentService:
    return StudentService(repository)


async def test_create_success(service: StudentService) -> None:
    data = make_student_create()

    student = await service.create(data)

    assert student.id is not None
    assert student.student_number == "S-0001"
    assert student.first_name == "Ada"
    assert student.last_name == "Lovelace"
    assert student.email == "ada@example.com"
    assert student.enrollment_status == "active"


async def test_create_duplicate_email_raises(service: StudentService) -> None:
    await service.create(make_student_create(student_number="S-0001", email="dup@example.com"))

    with pytest.raises(StudentAlreadyExistsError):
        await service.create(
            make_student_create(student_number="S-0002", email="dup@example.com")
        )


async def test_create_duplicate_student_number_raises(service: StudentService) -> None:
    await service.create(make_student_create(student_number="S-DUP", email="one@example.com"))

    with pytest.raises(StudentAlreadyExistsError):
        await service.create(
            make_student_create(student_number="S-DUP", email="two@example.com")
        )


async def test_get_success(service: StudentService) -> None:
    created = await service.create(make_student_create())

    fetched = await service.get(created.id)

    assert fetched.id == created.id
    assert fetched.email == created.email


async def test_get_missing_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.get(uuid4())


async def test_list(service: StudentService) -> None:
    await service.create(make_student_create(student_number="S-0001", email="a@example.com"))
    await service.create(make_student_create(student_number="S-0002", email="b@example.com"))

    students, total = await service.list(limit=50, offset=0)

    assert len(students) == 2
    assert total == 2
    assert {s.student_number for s in students} == {"S-0001", "S-0002"}


async def test_list_pagination_slices_and_reports_total(service: StudentService) -> None:
    for i in range(5):
        await service.create(
            make_student_create(student_number=f"S-{i:04d}", email=f"s{i}@example.com")
        )

    page, total = await service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 5


async def test_list_pagination_offset_skips_correctly(service: StudentService) -> None:
    created = [
        await service.create(
            make_student_create(student_number=f"S-{i:04d}", email=f"off{i}@example.com")
        )
        for i in range(5)
    ]
    # newest-first: index 4 (last created) is first in the full ordering.
    expected_full_order_ids = [s.id for s in reversed(created)]

    page, total = await service.list(limit=2, offset=2)

    assert total == 5
    assert [s.id for s in page] == expected_full_order_ids[2:4]


async def test_list_newest_first_ordering(service: StudentService) -> None:
    first = await service.create(
        make_student_create(student_number="S-ORD-1", email="ord1@example.com")
    )
    second = await service.create(
        make_student_create(student_number="S-ORD-2", email="ord2@example.com")
    )
    third = await service.create(
        make_student_create(student_number="S-ORD-3", email="ord3@example.com")
    )

    page, total = await service.list(limit=50, offset=0)

    assert total == 3
    assert [s.id for s in page] == [third.id, second.id, first.id]


async def test_update_success(service: StudentService) -> None:
    created = await service.create(make_student_create())

    updated = await service.update(
        created.id, StudentUpdate(first_name="Augusta", enrollment_status="graduated")
    )

    assert updated.id == created.id
    assert updated.first_name == "Augusta"
    assert updated.enrollment_status == "graduated"
    assert updated.last_name == "Lovelace"


async def test_update_missing_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.update(uuid4(), StudentUpdate(first_name="Nobody"))


async def test_delete_success(service: StudentService, repository: FakeStudentRepository) -> None:
    created = await service.create(make_student_create())

    await service.delete(created.id)

    assert await repository.get(created.id) is None


async def test_delete_missing_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.delete(uuid4())
