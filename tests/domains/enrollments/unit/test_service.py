from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.classes.exceptions import ClassNotFoundError
from sms.domains.classes.models import Class
from sms.domains.enrollments.exceptions import (
    ClassFullError,
    EnrollmentAlreadyExistsError,
    EnrollmentNotActiveError,
    EnrollmentNotFoundError,
)
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.enrollments.schemas import EnrollmentCreate
from sms.domains.enrollments.service import EnrollmentService
from sms.domains.students.exceptions import StudentNotFoundError
from sms.domains.students.models import Student

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing enrolled_at stamps, same pattern as
# tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeEnrollmentRepository(AbstractRepository[Enrollment]):
    """In-memory stand-in for EnrollmentRepository. add() mirrors
    uq_enrollments_student_class the same "pre-check narrows the window,
    doesn't close it" way as every other domain's fake (see docs/adr/0004) —
    it's the IntegrityError EnrollmentService.enroll's try/except is meant
    to catch when the pre-check misses a race. list() mirrors the real
    repository's pagination contract (sorted newest-first by enrolled_at)."""

    def __init__(self) -> None:
        self._enrollments: dict[UUID, Enrollment] = {}
        self._sequence = 0

    async def add(self, entity: Enrollment) -> Enrollment:
        for existing_id, existing in self._enrollments.items():
            if existing_id == entity.id:
                continue
            if existing.student_id == entity.student_id and existing.class_id == entity.class_id:
                raise IntegrityError("duplicate enrollment", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.enrolled_at is None:
            self._sequence += 1
            entity.enrolled_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._enrollments[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Enrollment | None:
        return self._enrollments.get(entity_id)

    async def list(
        self,
        *,
        student_id: UUID | None = None,
        class_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Enrollment], int]:
        results = list(self._enrollments.values())
        if student_id is not None:
            results = [e for e in results if e.student_id == student_id]
        if class_id is not None:
            results = [e for e in results if e.class_id == class_id]
        results.sort(key=lambda e: e.enrolled_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def remove(self, entity: Enrollment) -> None:
        self._enrollments.pop(entity.id, None)

    async def get_by_student_and_class(
        self, student_id: UUID, class_id: UUID
    ) -> Enrollment | None:
        for enrollment in self._enrollments.values():
            if enrollment.student_id == student_id and enrollment.class_id == class_id:
                return enrollment
        return None

    async def count_active_by_class(self, class_id: UUID) -> int:
        return sum(
            1
            for e in self._enrollments.values()
            if e.class_id == class_id and e.status == EnrollmentStatus.ACTIVE
        )


class FakeClassRepository(AbstractRepository[Class]):
    """Minimal in-memory stand-in for ClassRepository. get_for_update()
    behaves identically to get() here — a single-threaded unit test has no
    concurrent transaction for a real row lock to matter against; the
    lock's actual concurrency-safety is code-review-verified, not something
    this fake needs to (or can) simulate."""

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

    async def get_for_update(self, entity_id: UUID) -> Class | None:
        return self._classes.get(entity_id)


class FakeStudentRepository(AbstractRepository[Student]):
    """Minimal in-memory stand-in for StudentRepository — EnrollmentService
    only ever calls .get() on it (existence check)."""

    def __init__(self) -> None:
        self._students: dict[UUID, Student] = {}

    async def add(self, entity: Student) -> Student:
        if entity.id is None:
            entity.id = uuid4()
        self._students[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Student | None:
        return self._students.get(entity_id)

    async def list(self) -> list[Student]:
        return list(self._students.values())

    async def remove(self, entity: Student) -> None:
        self._students.pop(entity.id, None)


def make_student_instance(**overrides: object) -> Student:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "student_number": f"S-{uuid4().hex[:8]}",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": date(2010, 1, 1),
        "email": f"{uuid4().hex[:8]}@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
    }
    defaults.update(overrides)
    return Student(**defaults)


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


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def enrollment_repository() -> FakeEnrollmentRepository:
    return FakeEnrollmentRepository()


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def student_repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def enrollment_service(
    enrollment_repository: FakeEnrollmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> EnrollmentService:
    return EnrollmentService(enrollment_repository, class_repository, student_repository)


@pytest.fixture
async def student(student_repository: FakeStudentRepository) -> Student:
    return await student_repository.add(make_student_instance())


@pytest.fixture
async def klass(class_repository: FakeClassRepository) -> Class:
    return await class_repository.add(make_class_instance(capacity=30))


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------


async def test_enroll_success(
    enrollment_service: EnrollmentService, student: Student, klass: Class
) -> None:
    enrollment = await enrollment_service.enroll(
        EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    assert enrollment.id is not None
    assert enrollment.student_id == student.id
    assert enrollment.class_id == klass.id
    assert enrollment.status == EnrollmentStatus.ACTIVE


async def test_enroll_nonexistent_student_raises(
    enrollment_service: EnrollmentService, klass: Class
) -> None:
    with pytest.raises(StudentNotFoundError):
        await enrollment_service.enroll(
            EnrollmentCreate(student_id=uuid4(), class_id=klass.id)
        )


async def test_enroll_nonexistent_class_raises(
    enrollment_service: EnrollmentService, student: Student
) -> None:
    with pytest.raises(ClassNotFoundError):
        await enrollment_service.enroll(
            EnrollmentCreate(student_id=student.id, class_id=uuid4())
        )


async def test_enroll_already_enrolled_raises(
    enrollment_service: EnrollmentService, student: Student, klass: Class
) -> None:
    await enrollment_service.enroll(EnrollmentCreate(student_id=student.id, class_id=klass.id))

    with pytest.raises(EnrollmentAlreadyExistsError):
        await enrollment_service.enroll(
            EnrollmentCreate(student_id=student.id, class_id=klass.id)
        )


async def test_enroll_class_at_capacity_raises(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    full_class = await class_repository.add(make_class_instance(capacity=1))
    first_student = await student_repository.add(make_student_instance())
    second_student = await student_repository.add(make_student_instance())

    await enrollment_service.enroll(
        EnrollmentCreate(student_id=first_student.id, class_id=full_class.id)
    )

    with pytest.raises(ClassFullError):
        await enrollment_service.enroll(
            EnrollmentCreate(student_id=second_student.id, class_id=full_class.id)
        )


async def test_enroll_succeeds_up_to_exactly_capacity(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    two_seat_class = await class_repository.add(make_class_instance(capacity=2))
    first_student = await student_repository.add(make_student_instance())
    second_student = await student_repository.add(make_student_instance())

    first = await enrollment_service.enroll(
        EnrollmentCreate(student_id=first_student.id, class_id=two_seat_class.id)
    )
    second = await enrollment_service.enroll(
        EnrollmentCreate(student_id=second_student.id, class_id=two_seat_class.id)
    )

    assert first.status == EnrollmentStatus.ACTIVE
    assert second.status == EnrollmentStatus.ACTIVE


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_success(
    enrollment_service: EnrollmentService, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    fetched = await enrollment_service.get(created.id)

    assert fetched.id == created.id


async def test_get_missing_raises(enrollment_service: EnrollmentService) -> None:
    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.get(uuid4())


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list_no_filters_returns_everything(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_b.id, class_id=class_b.id)
    )

    enrollments, total = await enrollment_service.list(limit=50, offset=0)

    assert len(enrollments) == 2
    assert total == 2


async def test_list_pagination_smoke(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    for _ in range(3):
        klass = await class_repository.add(make_class_instance(capacity=10))
        student = await student_repository.add(make_student_instance())
        await enrollment_service.enroll(
            EnrollmentCreate(student_id=student.id, class_id=klass.id)
        )

    page, total = await enrollment_service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 3


async def test_list_filtered_by_student_id(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_b.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_b.id, class_id=class_a.id)
    )

    enrollments, total = await enrollment_service.list(student_id=student_a.id, limit=50, offset=0)

    assert len(enrollments) == 2
    assert total == 2
    assert {e.class_id for e in enrollments} == {class_a.id, class_b.id}


async def test_list_filtered_by_class_id(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_b.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_b.id)
    )

    enrollments, total = await enrollment_service.list(class_id=class_a.id, limit=50, offset=0)

    assert len(enrollments) == 2
    assert total == 2
    assert {e.student_id for e in enrollments} == {student_a.id, student_b.id}


async def test_list_filtered_by_both(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    target = await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_a.id, class_id=class_b.id)
    )
    await enrollment_service.enroll(
        EnrollmentCreate(student_id=student_b.id, class_id=class_a.id)
    )

    enrollments, total = await enrollment_service.list(
        student_id=student_a.id, class_id=class_a.id, limit=50, offset=0
    )

    assert len(enrollments) == 1
    assert total == 1
    assert enrollments[0].id == target.id


# ---------------------------------------------------------------------------
# drop
# ---------------------------------------------------------------------------


async def test_drop_success(
    enrollment_service: EnrollmentService, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    dropped = await enrollment_service.drop(created.id)

    assert dropped.id == created.id
    assert dropped.status == EnrollmentStatus.DROPPED


async def test_drop_already_dropped_raises(
    enrollment_service: EnrollmentService, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    await enrollment_service.drop(created.id)

    with pytest.raises(EnrollmentNotActiveError):
        await enrollment_service.drop(created.id)


async def test_drop_missing_raises(enrollment_service: EnrollmentService) -> None:
    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.drop(uuid4())
