# Prevents the "method named `list_*` shadows the builtin `list` for every
# later annotation in the same class body" gotcha — same root cause
# docs/adr/0018/0019 already hit (see e.g. src/sms/domains/classes/
# repository.py's identical comment). FakeSectionAssignmentRepository and
# FakeClassRepository below both define list_by_section_id() after their
# own list() methods.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.classes.models import Class
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.sections.exceptions import (
    SectionAssignmentNotFoundError,
    SectionFullError,
    SectionNotFoundError,
    StudentAlreadyAssignedError,
)
from sms.domains.sections.models import Section, SectionAssignment
from sms.domains.sections.service import SectionAssignmentService
from sms.domains.students.exceptions import StudentNotFoundError
from sms.domains.students.models import Student

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing assigned_at stamps, same pattern as
# tests/domains/enrollments/unit/test_service.py's identical _EPOCH (used
# there for Enrollment.enrolled_at, the closest analogue: another
# server_default=func.now()-only timestamp with no updated_at).
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeSectionAssignmentRepository(AbstractRepository[SectionAssignment]):
    """In-memory stand-in for SectionAssignmentRepository. add() mirrors
    uq_section_assignments_student_year (student_id, academic_year_id) the
    same "pre-check narrows the window, doesn't close it" way as every
    other domain's fake (see docs/adr/0004) — SectionAssignmentService.assign
    pre-checks too, but this keeps the fake faithful to what Postgres
    actually does if a race ever slips past that pre-check. commit=False
    support mirrors StudentRepository/TeacherRepository's identical
    parameter, needed for assign()'s atomic assignment+enrollment write."""

    def __init__(self) -> None:
        self._assignments: dict[UUID, SectionAssignment] = {}
        self._sequence = 0

    async def add(self, entity: SectionAssignment, *, commit: bool = True) -> SectionAssignment:
        for existing_id, existing in self._assignments.items():
            if existing_id == entity.id:
                continue
            if (
                existing.student_id == entity.student_id
                and existing.academic_year_id == entity.academic_year_id
            ):
                raise IntegrityError("duplicate (student, year)", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.assigned_at is None:
            self._sequence += 1
            entity.assigned_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._assignments[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> SectionAssignment | None:
        return self._assignments.get(entity_id)

    async def list(self) -> list[SectionAssignment]:
        return list(self._assignments.values())

    async def remove(self, entity: SectionAssignment) -> None:
        self._assignments.pop(entity.id, None)

    async def get_by_student_and_section(
        self, student_id: UUID, section_id: UUID
    ) -> SectionAssignment | None:
        for assignment in self._assignments.values():
            if assignment.student_id == student_id and assignment.section_id == section_id:
                return assignment
        return None

    async def get_by_student_and_year(
        self, student_id: UUID, academic_year_id: UUID
    ) -> SectionAssignment | None:
        for assignment in self._assignments.values():
            if (
                assignment.student_id == student_id
                and assignment.academic_year_id == academic_year_id
            ):
                return assignment
        return None

    async def count_by_section_id(self, section_id: UUID) -> int:
        return sum(1 for a in self._assignments.values() if a.section_id == section_id)

    async def list_by_section_id(self, section_id: UUID) -> list[SectionAssignment]:
        return [a for a in self._assignments.values() if a.section_id == section_id]


class FakeSectionRepository(AbstractRepository[Section]):
    """Minimal in-memory stand-in for SectionRepository. get_for_update()
    behaves identically to get() here — a single-threaded unit test has no
    concurrent transaction for a real row lock to matter against; the
    lock's actual concurrency-safety is code-review-verified, not something
    this fake needs to (or can) simulate. Same reasoning/shape as
    tests/domains/enrollments/unit/test_service.py's FakeClassRepository."""

    def __init__(self) -> None:
        self._sections: dict[UUID, Section] = {}

    async def add(self, entity: Section) -> Section:
        if entity.id is None:
            entity.id = uuid4()
        self._sections[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Section | None:
        return self._sections.get(entity_id)

    async def list(self) -> list[Section]:
        return list(self._sections.values())

    async def remove(self, entity: Section) -> None:
        self._sections.pop(entity.id, None)

    async def get_for_update(self, entity_id: UUID) -> Section | None:
        return self._sections.get(entity_id)


class FakeStudentRepository(AbstractRepository[Student]):
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


class FakeClassRepository(AbstractRepository[Class]):
    """Minimal in-memory stand-in for ClassRepository. list_by_section_id
    is what SectionAssignmentService.assign uses to find "every Class whose
    section_id == section.id" for the auto-enroll step."""

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

    async def list_by_section_id(self, section_id: UUID) -> list[Class]:
        return [c for c in self._classes.values() if c.section_id == section_id]


class FakeEnrollmentRepository(AbstractRepository[Enrollment]):
    """Minimal in-memory stand-in for EnrollmentRepository. add() supports
    commit=False for the atomic assign()+auto-enroll write; the assign()
    contract deliberately does NOT enforce per-class capacity here (that's
    the section's job) — count_active_by_class exists only in the real
    EnrollmentRepository for EnrollmentService.enroll's own capacity guard,
    not consulted by SectionAssignmentService at all."""

    def __init__(self) -> None:
        self._enrollments: dict[UUID, Enrollment] = {}

    async def add(self, entity: Enrollment, *, commit: bool = True) -> Enrollment:
        if entity.id is None:
            entity.id = uuid4()
        self._enrollments[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Enrollment | None:
        return self._enrollments.get(entity_id)

    async def list(self) -> list[Enrollment]:
        return list(self._enrollments.values())

    async def remove(self, entity: Enrollment) -> None:
        self._enrollments.pop(entity.id, None)

    async def get_by_student_and_class(
        self, student_id: UUID, class_id: UUID
    ) -> Enrollment | None:
        for enrollment in self._enrollments.values():
            if enrollment.student_id == student_id and enrollment.class_id == class_id:
                return enrollment
        return None


def make_section_instance(**overrides: object) -> Section:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "grade_level_id": uuid4(),
        "academic_year_id": uuid4(),
        "name": f"Section {uuid4().hex[:4]}",
        "capacity": 30,
        "class_teacher_id": None,
    }
    defaults.update(overrides)
    return Section(**defaults)


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
        "section_id": None,
    }
    defaults.update(overrides)
    return Class(**defaults)


@pytest.fixture
def assignment_repository() -> FakeSectionAssignmentRepository:
    return FakeSectionAssignmentRepository()


@pytest.fixture
def section_repository() -> FakeSectionRepository:
    return FakeSectionRepository()


@pytest.fixture
def student_repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def enrollment_repository() -> FakeEnrollmentRepository:
    return FakeEnrollmentRepository()


@pytest.fixture
def assignment_service(
    assignment_repository: FakeSectionAssignmentRepository,
    section_repository: FakeSectionRepository,
    student_repository: FakeStudentRepository,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
) -> SectionAssignmentService:
    return SectionAssignmentService(
        assignment_repository, section_repository, student_repository, class_repository, enrollment_repository
    )


@pytest.fixture
async def student(student_repository: FakeStudentRepository) -> Student:
    return await student_repository.add(make_student_instance())


@pytest.fixture
async def section(section_repository: FakeSectionRepository) -> Section:
    return await section_repository.add(make_section_instance())


# ---------------------------------------------------------------------------
# assign
# ---------------------------------------------------------------------------


async def test_assign_success(
    assignment_service: SectionAssignmentService, student: Student, section: Section
) -> None:
    assignment = await assignment_service.assign(student.id, section.id)

    assert assignment.id is not None
    assert assignment.student_id == student.id
    assert assignment.section_id == section.id
    assert assignment.academic_year_id == section.academic_year_id


async def test_assign_nonexistent_student_raises(
    assignment_service: SectionAssignmentService, section: Section
) -> None:
    with pytest.raises(StudentNotFoundError):
        await assignment_service.assign(uuid4(), section.id)


async def test_assign_nonexistent_section_raises(
    assignment_service: SectionAssignmentService, student: Student
) -> None:
    with pytest.raises(SectionNotFoundError):
        await assignment_service.assign(student.id, uuid4())


async def test_assign_already_assigned_same_year_raises(
    assignment_service: SectionAssignmentService,
    section_repository: FakeSectionRepository,
    student: Student,
    section: Section,
) -> None:
    other_section_same_year = await section_repository.add(
        make_section_instance(academic_year_id=section.academic_year_id)
    )
    await assignment_service.assign(student.id, section.id)

    with pytest.raises(StudentAlreadyAssignedError):
        await assignment_service.assign(student.id, other_section_same_year.id)


async def test_assign_same_student_different_academic_year_succeeds(
    assignment_service: SectionAssignmentService,
    section_repository: FakeSectionRepository,
    student: Student,
    section: Section,
) -> None:
    other_year_section = await section_repository.add(make_section_instance())
    assert other_year_section.academic_year_id != section.academic_year_id
    await assignment_service.assign(student.id, section.id)

    second = await assignment_service.assign(student.id, other_year_section.id)

    assert second.section_id == other_year_section.id
    assert second.academic_year_id == other_year_section.academic_year_id


async def test_assign_race_integrity_error_raises_already_assigned(
    assignment_service: SectionAssignmentService,
    assignment_repository: FakeSectionAssignmentRepository,
    student: Student,
    section: Section,
) -> None:
    # Simulates a duplicate slipping past the pre-check (a concurrent
    # request) — the fake's add() still enforces uq_section_assignments_
    # student_year, so the try/except IntegrityError branch is what must
    # catch this, not the pre-check.
    await assignment_repository.add(
        SectionAssignment(
            student_id=student.id, section_id=section.id, academic_year_id=section.academic_year_id
        )
    )

    with pytest.raises(StudentAlreadyAssignedError):
        await assignment_service.assign(student.id, section.id)


async def test_assign_section_at_capacity_raises(
    assignment_service: SectionAssignmentService,
    section_repository: FakeSectionRepository,
    student_repository: FakeStudentRepository,
) -> None:
    full_section = await section_repository.add(make_section_instance(capacity=1))
    first_student = await student_repository.add(make_student_instance())
    second_student = await student_repository.add(make_student_instance())
    await assignment_service.assign(first_student.id, full_section.id)

    with pytest.raises(SectionFullError):
        await assignment_service.assign(second_student.id, full_section.id)


async def test_assign_succeeds_up_to_exactly_capacity(
    assignment_service: SectionAssignmentService,
    section_repository: FakeSectionRepository,
    student_repository: FakeStudentRepository,
) -> None:
    two_seat_section = await section_repository.add(make_section_instance(capacity=2))
    first_student = await student_repository.add(make_student_instance())
    second_student = await student_repository.add(make_student_instance())

    first = await assignment_service.assign(first_student.id, two_seat_section.id)
    second = await assignment_service.assign(second_student.id, two_seat_section.id)

    assert first.id is not None
    assert second.id is not None


# ---------------------------------------------------------------------------
# assign — auto-enrollment
# ---------------------------------------------------------------------------


async def test_assign_auto_enrolls_into_every_attached_class(
    assignment_service: SectionAssignmentService,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    student: Student,
    section: Section,
) -> None:
    class_a = await class_repository.add(make_class_instance(section_id=section.id))
    class_b = await class_repository.add(make_class_instance(section_id=section.id))
    class_c = await class_repository.add(make_class_instance(section_id=section.id))

    await assignment_service.assign(student.id, section.id)

    enrolled_class_ids = {
        e.class_id for e in enrollment_repository._enrollments.values() if e.student_id == student.id
    }
    assert enrolled_class_ids == {class_a.id, class_b.id, class_c.id}
    assert all(
        e.status == EnrollmentStatus.ACTIVE for e in enrollment_repository._enrollments.values()
    )


async def test_assign_skips_class_student_already_enrolled_in(
    assignment_service: SectionAssignmentService,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    student: Student,
    section: Section,
) -> None:
    already_enrolled_class = await class_repository.add(make_class_instance(section_id=section.id))
    other_class = await class_repository.add(make_class_instance(section_id=section.id))
    pre_existing = await enrollment_repository.add(
        Enrollment(
            student_id=student.id, class_id=already_enrolled_class.id, status=EnrollmentStatus.ACTIVE
        )
    )

    await assignment_service.assign(student.id, section.id)

    matching_already_enrolled = [
        e
        for e in enrollment_repository._enrollments.values()
        if e.student_id == student.id and e.class_id == already_enrolled_class.id
    ]
    assert len(matching_already_enrolled) == 1
    assert matching_already_enrolled[0].id == pre_existing.id
    matching_other = [
        e
        for e in enrollment_repository._enrollments.values()
        if e.student_id == student.id and e.class_id == other_class.id
    ]
    assert len(matching_other) == 1


async def test_assign_class_with_smaller_capacity_than_section_still_auto_enrolls(
    assignment_service: SectionAssignmentService,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    section_repository: FakeSectionRepository,
    student_repository: FakeStudentRepository,
) -> None:
    # Per-class capacity is deliberately NOT enforced during auto-enroll —
    # the section's own capacity guard is what governs. A class with
    # capacity=1 that's already "full" (one active enrollment) must still
    # accept the auto-enrolled student.
    big_section = await section_repository.add(make_section_instance(capacity=10))
    tiny_class = await class_repository.add(make_class_instance(section_id=big_section.id, capacity=1))
    already_in_tiny_class = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        Enrollment(
            student_id=already_in_tiny_class.id, class_id=tiny_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    new_student = await student_repository.add(make_student_instance())

    await assignment_service.assign(new_student.id, big_section.id)

    matching = [
        e
        for e in enrollment_repository._enrollments.values()
        if e.student_id == new_student.id and e.class_id == tiny_class.id
    ]
    assert len(matching) == 1


async def test_assign_section_with_no_attached_classes_creates_zero_enrollments(
    assignment_service: SectionAssignmentService,
    enrollment_repository: FakeEnrollmentRepository,
    student: Student,
    section: Section,
) -> None:
    await assignment_service.assign(student.id, section.id)

    assert enrollment_repository._enrollments == {}


# ---------------------------------------------------------------------------
# unassign
# ---------------------------------------------------------------------------


async def test_unassign_success(
    assignment_service: SectionAssignmentService,
    assignment_repository: FakeSectionAssignmentRepository,
    student: Student,
    section: Section,
) -> None:
    created = await assignment_service.assign(student.id, section.id)

    await assignment_service.unassign(student.id, section.id)

    assert await assignment_repository.get(created.id) is None


async def test_unassign_leaves_enrollments_intact(
    assignment_service: SectionAssignmentService,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    student: Student,
    section: Section,
) -> None:
    await class_repository.add(make_class_instance(section_id=section.id))
    await assignment_service.assign(student.id, section.id)
    assert len(enrollment_repository._enrollments) == 1

    await assignment_service.unassign(student.id, section.id)

    assert len(enrollment_repository._enrollments) == 1


async def test_unassign_not_assigned_raises(
    assignment_service: SectionAssignmentService, student: Student, section: Section
) -> None:
    with pytest.raises(SectionAssignmentNotFoundError):
        await assignment_service.unassign(student.id, section.id)


# ---------------------------------------------------------------------------
# list_roster
# ---------------------------------------------------------------------------


async def test_list_roster_returns_section_assignments(
    assignment_service: SectionAssignmentService,
    student_repository: FakeStudentRepository,
    section: Section,
) -> None:
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    a = await assignment_service.assign(student_a.id, section.id)
    b = await assignment_service.assign(student_b.id, section.id)

    roster = await assignment_service.list_roster(section.id)

    assert {r.id for r in roster} == {a.id, b.id}


async def test_list_roster_empty_when_no_assignments(
    assignment_service: SectionAssignmentService, section: Section
) -> None:
    roster = await assignment_service.list_roster(section.id)

    assert roster == []
