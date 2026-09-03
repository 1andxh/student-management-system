# Prevents the "method named `list_*` shadows the builtin `list` for every
# later annotation in the same class body" gotcha — same root cause
# docs/adr/0018/0019 already hit (see e.g. src/sms/domains/classes/
# repository.py's identical comment). FakeSectionRepository defines
# list_student_ids_by_section() after its own list() method, so its
# `-> list[UUID]` annotation would otherwise be evaluated against a `list`
# name already shadowed by the method above it.
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.classes.exceptions import ClassNotFoundError
from sms.domains.classes.models import Class
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.sections.exceptions import (
    ClassAlreadyAttachedError,
    ClassNotAttachedError,
    ClassYearMismatchError,
    SectionNotFoundError,
)
from sms.domains.sections.models import GradeLevel, Section, SectionAssignment
from sms.domains.sections.schemas import SectionCreate
from sms.domains.sections.service import SectionService
from sms.domains.teachers.models import Teacher

# Arbitrary fixed epoch — only used as a base for the fakes' deterministic,
# monotonically increasing created_at stamps, same pattern as
# tests/domains/academic_years/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeSectionRepository(AbstractRepository[Section]):
    """In-memory stand-in for SectionRepository. add() mirrors
    uq_sections_grade_year_name (compound on grade_level_id +
    academic_year_id + name) the same "pre-check narrows the window,
    doesn't close it" way as every other domain's fake (see docs/adr/0004).

    commit()/rollback() are the shared-commit target for
    SectionService.attach_class's atomic Class.section_id write +
    Enrollment back-fill (self._repository.commit(), matching
    StudentService.generate_pin's identical "commit=False on each, one
    shared final commit()" shape) — reconciled against the real
    src/sms/domains/sections/service.py after the first red-state run
    confirmed SectionService actually takes a 7th constructor arg
    (assignment_repository: SectionAssignmentRepository) that the original
    settled contract text didn't list, and that the student-lookup for
    attach_class's back-fill goes through that repository's
    list_by_section_id(), not through SectionRepository itself as this
    file originally guessed."""

    def __init__(self) -> None:
        self._sections: dict[UUID, Section] = {}
        self._sequence = 0

    async def add(self, entity: Section, *, commit: bool = True) -> Section:
        for existing_id, existing in self._sections.items():
            if existing_id == entity.id:
                continue
            if (
                existing.grade_level_id == entity.grade_level_id
                and existing.academic_year_id == entity.academic_year_id
                and existing.name == entity.name
            ):
                raise IntegrityError("duplicate (grade_level, year, name)", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        if entity.updated_at is None:
            entity.updated_at = entity.created_at
        self._sections[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> Section | None:
        return self._sections.get(entity_id)

    async def get_for_update(self, entity_id: UUID) -> Section | None:
        # No real locking to model in-memory — this exists so the fake keeps
        # up with the real repository's interface, which attach_class and
        # assign both go through for their row lock.
        return self._sections.get(entity_id)

    async def list(
        self,
        *,
        limit: int = 50,
        offset: int = 0,
        grade_level_id: UUID | None = None,
        academic_year_id: UUID | None = None,
    ) -> tuple[list[Section], int]:
        results = list(self._sections.values())
        if grade_level_id is not None:
            results = [s for s in results if s.grade_level_id == grade_level_id]
        if academic_year_id is not None:
            results = [s for s in results if s.academic_year_id == academic_year_id]
        results.sort(key=lambda s: s.created_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def remove(self, entity: Section) -> None:
        self._sections.pop(entity.id, None)

    async def get_by_name(
        self, grade_level_id: UUID, academic_year_id: UUID, name: str
    ) -> Section | None:
        for section in self._sections.values():
            if (
                section.grade_level_id == grade_level_id
                and section.academic_year_id == academic_year_id
                and section.name == name
            ):
                return section
        return None


class FakeSectionAssignmentRepository(AbstractRepository[SectionAssignment]):
    """Minimal in-memory stand-in for SectionAssignmentRepository, just for
    the SectionService.attach_class back-fill path — list_by_section_id is
    the only method that service actually calls on it. Tests seed existing
    "this student is already in this section" state by calling add()
    directly (bypassing SectionAssignmentService entirely, which is
    exercised in its own test file)."""

    def __init__(self) -> None:
        self._assignments: dict[UUID, SectionAssignment] = {}

    async def add(self, entity: SectionAssignment) -> SectionAssignment:
        if entity.id is None:
            entity.id = uuid4()
        self._assignments[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> SectionAssignment | None:
        return self._assignments.get(entity_id)

    async def list(self) -> list[SectionAssignment]:
        return list(self._assignments.values())

    async def remove(self, entity: SectionAssignment) -> None:
        self._assignments.pop(entity.id, None)

    async def list_by_section_id(self, section_id: UUID) -> list[SectionAssignment]:
        return [a for a in self._assignments.values() if a.section_id == section_id]


class FakeGradeLevelRepository(AbstractRepository[GradeLevel]):
    def __init__(self) -> None:
        self._grade_levels: dict[UUID, GradeLevel] = {}

    async def add(self, entity: GradeLevel) -> GradeLevel:
        if entity.id is None:
            entity.id = uuid4()
        self._grade_levels[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> GradeLevel | None:
        return self._grade_levels.get(entity_id)

    async def list(self) -> list[GradeLevel]:
        return list(self._grade_levels.values())

    async def remove(self, entity: GradeLevel) -> None:
        self._grade_levels.pop(entity.id, None)


class FakeAcademicYearRepository(AbstractRepository[AcademicYear]):
    def __init__(self) -> None:
        self._years: dict[UUID, AcademicYear] = {}

    async def add(self, entity: AcademicYear) -> AcademicYear:
        if entity.id is None:
            entity.id = uuid4()
        self._years[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> AcademicYear | None:
        return self._years.get(entity_id)

    async def list(self) -> list[AcademicYear]:
        return list(self._years.values())

    async def remove(self, entity: AcademicYear) -> None:
        self._years.pop(entity.id, None)


class FakeTeacherRepository(AbstractRepository[Teacher]):
    def __init__(self) -> None:
        self._teachers: dict[UUID, Teacher] = {}

    async def add(self, entity: Teacher) -> Teacher:
        if entity.id is None:
            entity.id = uuid4()
        self._teachers[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Teacher | None:
        return self._teachers.get(entity_id)

    async def list(self) -> list[Teacher]:
        return list(self._teachers.values())

    async def remove(self, entity: Teacher) -> None:
        self._teachers.pop(entity.id, None)


class FakeClassRepository(AbstractRepository[Class]):
    """Minimal in-memory stand-in for ClassRepository. add() supports
    commit=False — SectionService.attach_class/detach_class write
    Class.section_id atomically alongside the Enrollment backfill, same
    "commit=False on each, one shared final commit()" shape as
    StudentService.generate_pin (src/sms/domains/students/service.py)."""

    def __init__(self) -> None:
        self._classes: dict[UUID, Class] = {}

    async def add(self, entity: Class, *, commit: bool = True) -> Class:
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


class FakeEnrollmentRepository(AbstractRepository[Enrollment]):
    """Minimal in-memory stand-in for EnrollmentRepository, for the
    attach_class backfill path. add() supports commit=False for the same
    reason as FakeClassRepository above."""

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


def make_grade_level_instance(**overrides: object) -> GradeLevel:
    defaults: dict[str, object] = {"id": uuid4(), "name": f"Grade {uuid4().hex[:4]}", "rank": 1}
    defaults.update(overrides)
    return GradeLevel(**defaults)


def make_academic_year_instance(**overrides: object) -> AcademicYear:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "name": f"Year {uuid4().hex[:8]}",
        "start_date": date(2024, 9, 1),
        "end_date": date(2025, 6, 30),
    }
    defaults.update(overrides)
    return AcademicYear(**defaults)


def make_teacher_instance(**overrides: object) -> Teacher:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": f"teacher{uuid4().hex[:8]}@example.com",
        "hire_date": date(2015, 6, 1),
    }
    defaults.update(overrides)
    return Teacher(**defaults)


class FakeTermRepository(AbstractRepository[Term]):
    """Only .get() is exercised — SectionService.attach_class walks
    Class.term_id -> Term.academic_year_id to reject attaching a class from
    a different academic year."""

    def __init__(self) -> None:
        self._terms: dict[UUID, Term] = {}

    async def add(self, entity: Term) -> Term:
        if entity.id is None:
            entity.id = uuid4()
        self._terms[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Term | None:
        return self._terms.get(entity_id)

    async def list(self) -> list[Term]:
        return list(self._terms.values())

    async def remove(self, entity: Term) -> None:
        self._terms.pop(entity.id, None)


def make_term_instance(academic_year_id: UUID, **overrides: object) -> Term:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "academic_year_id": academic_year_id,
        "name": f"Term {uuid4().hex[:4]}",
        "start_date": date(2024, 9, 1),
        "end_date": date(2024, 12, 20),
    }
    defaults.update(overrides)
    return Term(**defaults)


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


def make_section_create(grade_level_id: UUID, academic_year_id: UUID, **overrides: object) -> SectionCreate:
    defaults: dict[str, object] = {
        "grade_level_id": grade_level_id,
        "academic_year_id": academic_year_id,
        "name": "Section A",
        "capacity": 30,
    }
    defaults.update(overrides)
    return SectionCreate(**defaults)


@pytest.fixture
def section_repository() -> FakeSectionRepository:
    return FakeSectionRepository()


@pytest.fixture
def grade_level_repository() -> FakeGradeLevelRepository:
    return FakeGradeLevelRepository()


@pytest.fixture
def academic_year_repository() -> FakeAcademicYearRepository:
    return FakeAcademicYearRepository()


@pytest.fixture
def teacher_repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def enrollment_repository() -> FakeEnrollmentRepository:
    return FakeEnrollmentRepository()


@pytest.fixture
def assignment_repository() -> FakeSectionAssignmentRepository:
    return FakeSectionAssignmentRepository()


@pytest.fixture
def term_repository() -> FakeTermRepository:
    return FakeTermRepository()


@pytest.fixture
def section_service(
    section_repository: FakeSectionRepository,
    grade_level_repository: FakeGradeLevelRepository,
    academic_year_repository: FakeAcademicYearRepository,
    teacher_repository: FakeTeacherRepository,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
    term_repository: FakeTermRepository,
) -> SectionService:
    return SectionService(
        section_repository,
        grade_level_repository,
        academic_year_repository,
        teacher_repository,
        class_repository,
        enrollment_repository,
        assignment_repository,
        term_repository,
    )


@pytest.fixture
async def grade_level(grade_level_repository: FakeGradeLevelRepository) -> GradeLevel:
    return await grade_level_repository.add(make_grade_level_instance())


@pytest.fixture
async def academic_year(academic_year_repository: FakeAcademicYearRepository) -> AcademicYear:
    return await academic_year_repository.add(make_academic_year_instance())


@pytest.fixture
async def teacher(teacher_repository: FakeTeacherRepository) -> Teacher:
    return await teacher_repository.add(make_teacher_instance())


@pytest.fixture
async def term_in_year(
    term_repository: FakeTermRepository, academic_year: AcademicYear
) -> Term:
    """A Term inside the `academic_year` fixture's year — attach_class
    rejects a class whose term belongs to a different year, so every
    attachable class in these tests hangs off this."""
    return await term_repository.add(make_term_instance(academic_year.id))


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


async def test_attach_class_sets_section_id_on_class(
    section_service: SectionService,
    section_repository: FakeSectionRepository,
    class_repository: FakeClassRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))

    result = await section_service.attach_class(section.id, klass.id)

    assert result.id == section.id
    updated_class = await class_repository.get(klass.id)
    assert updated_class.section_id == section.id


async def test_attach_class_backfills_enrollments_for_existing_section_members(
    section_service: SectionService,
    section_repository: FakeSectionRepository,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    student_a, student_b = uuid4(), uuid4()
    await assignment_repository.add(
        SectionAssignment(student_id=student_a, section_id=section.id, academic_year_id=academic_year.id)
    )
    await assignment_repository.add(
        SectionAssignment(student_id=student_b, section_id=section.id, academic_year_id=academic_year.id)
    )
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))

    await section_service.attach_class(section.id, klass.id)

    created = list(enrollment_repository._enrollments.values())
    assert {e.student_id for e in created} == {student_a, student_b}
    assert all(e.class_id == klass.id for e in created)
    assert all(e.status == EnrollmentStatus.ACTIVE for e in created)


async def test_attach_class_skips_student_already_enrolled(
    section_service: SectionService,
    section_repository: FakeSectionRepository,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    already_enrolled_student = uuid4()
    await assignment_repository.add(
        SectionAssignment(
            student_id=already_enrolled_student, section_id=section.id, academic_year_id=academic_year.id
        )
    )
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))
    await enrollment_repository.add(
        Enrollment(
            student_id=already_enrolled_student, class_id=klass.id, status=EnrollmentStatus.ACTIVE
        )
    )

    await section_service.attach_class(section.id, klass.id)

    matching = [
        e
        for e in enrollment_repository._enrollments.values()
        if e.student_id == already_enrolled_student and e.class_id == klass.id
    ]
    assert len(matching) == 1


async def test_attach_class_is_idempotent(
    section_service: SectionService,
    section_repository: FakeSectionRepository,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    student = uuid4()
    await assignment_repository.add(
        SectionAssignment(student_id=student, section_id=section.id, academic_year_id=academic_year.id)
    )
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))

    await section_service.attach_class(section.id, klass.id)
    await section_service.attach_class(section.id, klass.id)

    matching = [
        e
        for e in enrollment_repository._enrollments.values()
        if e.student_id == student and e.class_id == klass.id
    ]
    assert len(matching) == 1


async def test_attach_class_no_section_members_creates_no_enrollments(
    section_service: SectionService,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))

    await section_service.attach_class(section.id, klass.id)

    assert enrollment_repository._enrollments == {}


async def test_attach_class_nonexistent_section_raises(
    section_service: SectionService, class_repository: FakeClassRepository
) -> None:
    klass = await class_repository.add(make_class_instance())

    with pytest.raises(SectionNotFoundError):
        await section_service.attach_class(uuid4(), klass.id)


async def test_attach_class_nonexistent_class_raises(
    section_service: SectionService, grade_level: GradeLevel, academic_year: AcademicYear
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))

    with pytest.raises(ClassNotFoundError):
        await section_service.attach_class(section.id, uuid4())


async def test_detach_class_clears_section_id(
    section_service: SectionService,
    class_repository: FakeClassRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))
    await section_service.attach_class(section.id, klass.id)

    result = await section_service.detach_class(section.id, klass.id)

    assert result.id == section.id
    updated_class = await class_repository.get(klass.id)
    assert updated_class.section_id is None


async def test_detach_class_leaves_enrollments_intact(
    section_service: SectionService,
    section_repository: FakeSectionRepository,
    class_repository: FakeClassRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    student = uuid4()
    await assignment_repository.add(
        SectionAssignment(student_id=student, section_id=section.id, academic_year_id=academic_year.id)
    )
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))
    await section_service.attach_class(section.id, klass.id)
    assert len(enrollment_repository._enrollments) == 1

    await section_service.detach_class(section.id, klass.id)

    assert len(enrollment_repository._enrollments) == 1


async def test_detach_class_nonexistent_section_raises(
    section_service: SectionService, class_repository: FakeClassRepository
) -> None:
    klass = await class_repository.add(make_class_instance())

    with pytest.raises(SectionNotFoundError):
        await section_service.detach_class(uuid4(), klass.id)


async def test_detach_class_nonexistent_class_raises(
    section_service: SectionService, grade_level: GradeLevel, academic_year: AcademicYear
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))

    with pytest.raises(ClassNotFoundError):
        await section_service.detach_class(section.id, uuid4())


# ---------------------------------------------------------------------------
# attach guards (security-auditor findings)
# ---------------------------------------------------------------------------


async def test_attach_class_from_different_academic_year_raises(
    section_service: SectionService,
    class_repository: FakeClassRepository,
    term_repository: FakeTermRepository,
    academic_year_repository: FakeAcademicYearRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
) -> None:
    # A Class carries no academic year of its own — it's reached via
    # Class.term_id -> Term.academic_year_id. Attaching one from another
    # year would auto-enrol the whole roster into it, handing that class's
    # teacher gradebook access over an unrelated cohort.
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    other_year = await academic_year_repository.add(make_academic_year_instance())
    foreign_term = await term_repository.add(make_term_instance(other_year.id))
    klass = await class_repository.add(make_class_instance(term_id=foreign_term.id))

    with pytest.raises(ClassYearMismatchError):
        await section_service.attach_class(section.id, klass.id)


async def test_attach_class_already_attached_to_another_section_raises(
    section_service: SectionService,
    class_repository: FakeClassRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    # Silently re-pointing would orphan the first section's enrolments and
    # stack both rosters onto one class — unbounded overshoot of the
    # per-class capacity that EnrollmentService.enroll locks to protect.
    section_a = await section_service.create(
        make_section_create(grade_level.id, academic_year.id, name="A")
    )
    section_b = await section_service.create(
        make_section_create(grade_level.id, academic_year.id, name="B")
    )
    klass = await class_repository.add(make_class_instance(term_id=term_in_year.id))
    await section_service.attach_class(section_a.id, klass.id)

    with pytest.raises(ClassAlreadyAttachedError):
        await section_service.attach_class(section_b.id, klass.id)


async def test_detach_class_not_attached_to_this_section_raises(
    section_service: SectionService,
    class_repository: FakeClassRepository,
    grade_level: GradeLevel,
    academic_year: AcademicYear,
    term_in_year: Term,
) -> None:
    section = await section_service.create(make_section_create(grade_level.id, academic_year.id))
    unattached = await class_repository.add(make_class_instance(term_id=term_in_year.id))

    with pytest.raises(ClassNotAttachedError):
        await section_service.detach_class(section.id, unattached.id)
