from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.assessments.exceptions import (
    AssessmentNotFoundError,
    GradeAlreadyExistsError,
    GradeNotFoundError,
    ScoreExceedsMaxScoreError,
    StudentNotEnrolledError,
)
from sms.domains.assessments.models import Assessment, AssessmentType, Grade
from sms.domains.assessments.schemas import (
    AssessmentCreate,
    AssessmentUpdate,
    GradeCreate,
    GradeUpdate,
)
from sms.domains.assessments.service import AssessmentService, GradeService
from sms.domains.classes.exceptions import ClassNotFoundError, NotYourClassError
from sms.domains.classes.models import Class
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.students.exceptions import StudentNotFoundError
from sms.domains.students.models import Student
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole

# ---------------------------------------------------------------------------
# fake repositories
# ---------------------------------------------------------------------------

# Arbitrary fixed epoch — only used as a base for the fakes' deterministic,
# monotonically increasing created_at/graded_at stamps, same pattern as
# tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeAssessmentRepository(AbstractRepository[Assessment]):
    """In-memory stand-in for AssessmentRepository. Assessment has no
    uniqueness concept (same as Class, docs/adr/0016) so add() never raises
    for a duplicate — nothing here mirrors an IntegrityError path.

    list()'s class_ids filter mirrors the real repository's
    Assessment.class_id.in_(class_ids) filter — used by AssessmentService to
    scope a TEACHER caller to only the classes they own. class_id (singular)
    is the new explicit GET /assessments?class_id= filter — mirrors
    GradeRepository.list()'s existing class_id/class_ids split. list()
    returns (items, total), sorted newest-first by created_at, matching the
    shared pagination contract."""

    def __init__(self) -> None:
        self._assessments: dict[UUID, Assessment] = {}
        self._sequence = 0

    async def add(self, entity: Assessment) -> Assessment:
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._assessments[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Assessment | None:
        return self._assessments.get(entity_id)

    async def list(
        self,
        *,
        class_id: UUID | None = None,
        class_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Assessment], int]:
        results = list(self._assessments.values())
        if class_id is not None:
            results = [a for a in results if a.class_id == class_id]
        if class_ids is not None:
            results = [a for a in results if a.class_id in class_ids]
        results.sort(key=lambda a: a.created_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def remove(self, entity: Assessment) -> None:
        self._assessments.pop(entity.id, None)


class FakeGradeRepository(AbstractRepository[Grade]):
    """In-memory stand-in for GradeRepository. add() mirrors
    uq_grades_assessment_student the same "pre-check narrows the window,
    doesn't close it" way as every other domain's fake (see docs/adr/0004) —
    it's the IntegrityError GradeService.create's try/except is meant to
    catch when the pre-check misses a race. list()'s class_id/class_ids
    filters need a join to Assessment (Grade has no class_id column of its
    own), so this fake is constructed with a reference to the assessment
    repository to do that lookup, matching the real repository's join.
    class_id (singular) is the pre-existing ADMIN/explicit filter;
    class_ids (plural, new) is the TEACHER-ownership scoping filter."""

    def __init__(self, assessment_repository: FakeAssessmentRepository) -> None:
        self._grades: dict[UUID, Grade] = {}
        self._assessment_repository = assessment_repository
        self._sequence = 0

    async def add(self, entity: Grade) -> Grade:
        for existing_id, existing in self._grades.items():
            if existing_id == entity.id:
                continue
            if (
                existing.assessment_id == entity.assessment_id
                and existing.student_id == entity.student_id
            ):
                raise IntegrityError("duplicate grade", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.graded_at is None:
            self._sequence += 1
            entity.graded_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._grades[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Grade | None:
        return self._grades.get(entity_id)

    async def list(
        self,
        *,
        class_id: UUID | None = None,
        class_ids: list[UUID] | None = None,
        student_id: UUID | None = None,
        assessment_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Grade], int]:
        results = list(self._grades.values())
        if assessment_id is not None:
            results = [g for g in results if g.assessment_id == assessment_id]
        if student_id is not None:
            results = [g for g in results if g.student_id == student_id]
        if class_id is not None:
            all_assessments, _ = await self._assessment_repository.list(limit=1_000_000, offset=0)
            matching_assessment_ids = {a.id for a in all_assessments if a.class_id == class_id}
            results = [g for g in results if g.assessment_id in matching_assessment_ids]
        if class_ids is not None:
            all_assessments, _ = await self._assessment_repository.list(limit=1_000_000, offset=0)
            matching_assessment_ids = {
                a.id for a in all_assessments if a.class_id in class_ids
            }
            results = [g for g in results if g.assessment_id in matching_assessment_ids]
        results.sort(key=lambda g: g.graded_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def remove(self, entity: Grade) -> None:
        self._grades.pop(entity.id, None)

    async def get_by_assessment_and_student(
        self, assessment_id: UUID, student_id: UUID
    ) -> Grade | None:
        for grade in self._grades.values():
            if grade.assessment_id == assessment_id and grade.student_id == student_id:
                return grade
        return None


class FakeClassRepository(AbstractRepository[Class]):
    """Minimal in-memory stand-in for ClassRepository — AssessmentService
    and GradeService call .get() (existence check) and, now,
    .list_by_teacher_id() (TEACHER-ownership scoping), same shape as
    enrollments' unit-test fake plus the new teacher-scoping method."""

    def __init__(self) -> None:
        self._classes: dict[UUID, Class] = {}

    async def add(self, entity: Class) -> Class:
        if entity.id is None:
            entity.id = uuid4()
        self._classes[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Class | None:
        return self._classes.get(entity_id)

    # Deliberately defined before `list` below — a method named `list`
    # shadows the builtin `list` for any annotation evaluated afterwards in
    # this same class body (annotations are evaluated eagerly against the
    # class namespace being built, not deferred), so `list[Class]` here
    # would otherwise try to subscript the *method* named list, not the
    # builtin type, and raise TypeError at class-definition time.
    async def list_by_teacher_id(self, teacher_id: UUID) -> list[Class]:
        return [c for c in self._classes.values() if c.teacher_id == teacher_id]

    async def list(self) -> list[Class]:
        return list(self._classes.values())

    async def remove(self, entity: Class) -> None:
        self._classes.pop(entity.id, None)


class FakeStudentRepository(AbstractRepository[Student]):
    """Minimal in-memory stand-in for StudentRepository. get_by_user_id is
    exercised directly by GradeService._get_my_student_id's self-scoping
    logic — the reason this fake exists distinct from a bare dict."""

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

    async def get_by_user_id(self, user_id: UUID) -> Student | None:
        for student in self._students.values():
            if student.user_id == user_id:
                return student
        return None


class FakeTeacherRepository(AbstractRepository[Teacher]):
    """Minimal in-memory stand-in for TeacherRepository. get_by_user_id is
    exercised directly by AssessmentService/GradeService's new
    _get_my_teacher_id helper — same shape/reasoning as
    FakeStudentRepository above."""

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

    async def get_by_user_id(self, user_id: UUID) -> Teacher | None:
        for teacher in self._teachers.values():
            if teacher.user_id == user_id:
                return teacher
        return None


class FakeEnrollmentRepository(AbstractRepository[Enrollment]):
    """Minimal in-memory stand-in for EnrollmentRepository — GradeService
    only ever calls get_by_student_and_class on it."""

    def __init__(self) -> None:
        self._enrollments: dict[UUID, Enrollment] = {}

    async def add(self, entity: Enrollment) -> Enrollment:
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


# ---------------------------------------------------------------------------
# instance builders
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


def make_student_instance(**overrides: object) -> Student:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "user_id": None,
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


def make_teacher_instance(**overrides: object) -> Teacher:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "user_id": None,
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": f"teacher{uuid4().hex[:8]}@example.com",
        "hire_date": date(2015, 6, 1),
    }
    defaults.update(overrides)
    return Teacher(**defaults)


def make_assessment_instance(**overrides: object) -> Assessment:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "class_id": uuid4(),
        "name": "Midterm Exam",
        "type": AssessmentType.EXAM,
        "max_score": Decimal("100.00"),
        "date": date(2024, 10, 15),
    }
    defaults.update(overrides)
    return Assessment(**defaults)


def make_enrollment_instance(**overrides: object) -> Enrollment:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "student_id": uuid4(),
        "class_id": uuid4(),
        "status": EnrollmentStatus.ACTIVE,
    }
    defaults.update(overrides)
    return Enrollment(**defaults)


def make_user_instance(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "email": f"{uuid4().hex[:8]}@example.com",
        "hashed_password": "not-a-real-hash",
        "role": UserRole.ADMIN,
        "is_active": True,
    }
    defaults.update(overrides)
    return User(**defaults)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def assessment_repository() -> FakeAssessmentRepository:
    return FakeAssessmentRepository()


@pytest.fixture
def grade_repository(assessment_repository: FakeAssessmentRepository) -> FakeGradeRepository:
    return FakeGradeRepository(assessment_repository)


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def student_repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def teacher_repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def enrollment_repository() -> FakeEnrollmentRepository:
    return FakeEnrollmentRepository()


@pytest.fixture
def assessment_service(
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    teacher_repository: FakeTeacherRepository,
) -> AssessmentService:
    return AssessmentService(
        repository=assessment_repository,
        class_repository=class_repository,
        teacher_repository=teacher_repository,
    )


@pytest.fixture
def grade_service(
    grade_repository: FakeGradeRepository,
    assessment_repository: FakeAssessmentRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    class_repository: FakeClassRepository,
    teacher_repository: FakeTeacherRepository,
) -> GradeService:
    return GradeService(
        repository=grade_repository,
        assessment_repository=assessment_repository,
        student_repository=student_repository,
        enrollment_repository=enrollment_repository,
        class_repository=class_repository,
        teacher_repository=teacher_repository,
    )


@pytest.fixture
async def klass(class_repository: FakeClassRepository) -> Class:
    return await class_repository.add(make_class_instance())


@pytest.fixture
async def assessment(
    assessment_repository: FakeAssessmentRepository, klass: Class
) -> Assessment:
    return await assessment_repository.add(
        make_assessment_instance(class_id=klass.id, max_score=Decimal("100.00"))
    )


@pytest.fixture
async def student(student_repository: FakeStudentRepository) -> Student:
    return await student_repository.add(make_student_instance())


@pytest.fixture
async def active_enrollment(
    enrollment_repository: FakeEnrollmentRepository, student: Student, klass: Class
) -> Enrollment:
    return await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=klass.id, status=EnrollmentStatus.ACTIVE
        )
    )


@pytest.fixture
def admin_user() -> User:
    return make_user_instance(role=UserRole.ADMIN)


@pytest.fixture
def make_teacher_user(teacher_repository: FakeTeacherRepository):
    """Factory: create a TEACHER-role User linked to a new Teacher record
    via user_id (mirrors the Student user-linking pattern the STUDENT
    self-view tests already use). Returns (user, teacher) — the caller
    creates and assigns Class.teacher_id = teacher.id itself when it needs a
    class this teacher owns, or uses an unrelated class/teacher_id for the
    not-owned case."""

    async def _make() -> tuple[User, Teacher]:
        user = make_user_instance(role=UserRole.TEACHER)
        teacher = await teacher_repository.add(make_teacher_instance(user_id=user.id))
        return user, teacher

    return _make


# ---------------------------------------------------------------------------
# AssessmentService.create
# ---------------------------------------------------------------------------


async def test_create_assessment_success(
    assessment_service: AssessmentService, admin_user: User, klass: Class
) -> None:
    data = AssessmentCreate(
        class_id=klass.id,
        name="Midterm Exam",
        type=AssessmentType.EXAM,
        max_score=Decimal("100.00"),
        date=date(2024, 10, 15),
    )

    created = await assessment_service.create(admin_user, data)

    assert created.id is not None
    assert created.class_id == klass.id
    assert created.name == "Midterm Exam"
    assert created.type == AssessmentType.EXAM
    assert created.max_score == Decimal("100.00")
    assert created.date == date(2024, 10, 15)


async def test_create_assessment_nonexistent_class_raises(
    assessment_service: AssessmentService, admin_user: User
) -> None:
    data = AssessmentCreate(
        class_id=uuid4(),
        name="Pop Quiz",
        type=AssessmentType.QUIZ,
        max_score=Decimal("20.00"),
        date=date(2024, 9, 1),
    )

    with pytest.raises(ClassNotFoundError):
        await assessment_service.create(admin_user, data)


async def test_create_assessment_as_teacher_who_owns_class_succeeds(
    assessment_service: AssessmentService,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    data = AssessmentCreate(
        class_id=owned_class.id,
        name="Quiz 1",
        type=AssessmentType.QUIZ,
        max_score=Decimal("20.00"),
        date=date(2024, 9, 1),
    )

    created = await assessment_service.create(teacher_user, data)

    assert created.class_id == owned_class.id


async def test_create_assessment_as_teacher_not_owning_class_raises_not_your_class(
    assessment_service: AssessmentService, klass: Class, make_teacher_user
) -> None:
    teacher_user, _teacher = await make_teacher_user()
    # `klass` is owned by an unrelated random teacher_id, not this teacher.
    data = AssessmentCreate(
        class_id=klass.id,
        name="Quiz 1",
        type=AssessmentType.QUIZ,
        max_score=Decimal("20.00"),
        date=date(2024, 9, 1),
    )

    with pytest.raises(NotYourClassError):
        await assessment_service.create(teacher_user, data)


async def test_create_assessment_as_teacher_with_no_linked_teacher_record_raises_not_your_class(
    assessment_service: AssessmentService, klass: Class
) -> None:
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)  # no linked Teacher record
    data = AssessmentCreate(
        class_id=klass.id,
        name="Quiz 1",
        type=AssessmentType.QUIZ,
        max_score=Decimal("20.00"),
        date=date(2024, 9, 1),
    )

    with pytest.raises(NotYourClassError):
        await assessment_service.create(orphan_teacher_user, data)


async def test_create_assessment_as_admin_succeeds_regardless_of_ownership(
    assessment_service: AssessmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    _teacher_user, other_teacher = await make_teacher_user()
    other_teachers_class = await class_repository.add(
        make_class_instance(teacher_id=other_teacher.id)
    )
    data = AssessmentCreate(
        class_id=other_teachers_class.id,
        name="Final Exam",
        type=AssessmentType.EXAM,
        max_score=Decimal("100.00"),
        date=date(2024, 12, 1),
    )

    created = await assessment_service.create(admin_user, data)

    assert created.class_id == other_teachers_class.id


# ---------------------------------------------------------------------------
# AssessmentService.get
# ---------------------------------------------------------------------------


async def test_get_assessment_success(
    assessment_service: AssessmentService, admin_user: User, assessment: Assessment
) -> None:
    fetched = await assessment_service.get(admin_user, assessment.id)

    assert fetched.id == assessment.id


async def test_get_assessment_missing_raises(
    assessment_service: AssessmentService, admin_user: User
) -> None:
    with pytest.raises(AssessmentNotFoundError):
        await assessment_service.get(admin_user, uuid4())


async def test_get_assessment_as_teacher_who_owns_class_succeeds(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id)
    )

    fetched = await assessment_service.get(teacher_user, owned_assessment.id)

    assert fetched.id == owned_assessment.id


async def test_get_assessment_as_teacher_not_owning_class_raises_not_your_class(
    assessment_service: AssessmentService, assessment: Assessment, make_teacher_user
) -> None:
    # `assessment` belongs to `klass`, owned by an unrelated random
    # teacher_id, not this teacher.
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await assessment_service.get(teacher_user, assessment.id)


async def test_get_assessment_as_teacher_with_no_linked_teacher_record_raises_not_your_class(
    assessment_service: AssessmentService, assessment: Assessment
) -> None:
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)

    with pytest.raises(NotYourClassError):
        await assessment_service.get(orphan_teacher_user, assessment.id)


async def test_get_assessment_as_admin_succeeds_regardless_of_ownership(
    assessment_service: AssessmentService, admin_user: User, assessment: Assessment
) -> None:
    fetched = await assessment_service.get(admin_user, assessment.id)

    assert fetched.id == assessment.id


# ---------------------------------------------------------------------------
# AssessmentService.list
# ---------------------------------------------------------------------------


async def test_list_assessments_returns_everything(
    assessment_service: AssessmentService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    klass: Class,
) -> None:
    await assessment_repository.add(make_assessment_instance(class_id=klass.id, name="A"))
    await assessment_repository.add(make_assessment_instance(class_id=klass.id, name="B"))

    assessments, total = await assessment_service.list(admin_user, limit=50, offset=0)

    assert len(assessments) == 2
    assert total == 2


async def test_list_assessments_pagination_slices_and_reports_total(
    assessment_service: AssessmentService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    klass: Class,
) -> None:
    for i in range(5):
        await assessment_repository.add(make_assessment_instance(class_id=klass.id, name=f"A{i}"))

    page, total = await assessment_service.list(admin_user, limit=2, offset=0)

    assert len(page) == 2
    assert total == 5


async def test_list_assessments_newest_first_ordering(
    assessment_service: AssessmentService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    klass: Class,
) -> None:
    first = await assessment_repository.add(make_assessment_instance(class_id=klass.id, name="First"))
    second = await assessment_repository.add(make_assessment_instance(class_id=klass.id, name="Second"))

    page, total = await assessment_service.list(admin_user, limit=50, offset=0)

    assert total == 2
    assert [a.id for a in page] == [second.id, first.id]


async def test_list_assessments_filtered_by_class_id_as_admin(
    assessment_service: AssessmentService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance())
    class_b = await class_repository.add(make_class_instance())
    match = await assessment_repository.add(make_assessment_instance(class_id=class_a.id))
    await assessment_repository.add(make_assessment_instance(class_id=class_b.id))

    filtered, total = await assessment_service.list(
        admin_user, class_id=class_a.id, limit=50, offset=0
    )

    assert total == 1
    assert [a.id for a in filtered] == [match.id]


async def test_list_assessments_as_teacher_returns_only_own_classes(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    other_class = await class_repository.add(make_class_instance())
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id)
    )
    await assessment_repository.add(make_assessment_instance(class_id=other_class.id))

    assessments, total = await assessment_service.list(teacher_user, limit=50, offset=0)

    assert total == 1
    assert [a.id for a in assessments] == [owned_assessment.id]


async def test_list_assessments_as_teacher_explicit_owned_class_id_succeeds(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    other_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id)
    )
    await assessment_repository.add(make_assessment_instance(class_id=other_class.id))

    filtered, total = await assessment_service.list(
        teacher_user, class_id=owned_class.id, limit=50, offset=0
    )

    assert total == 1
    assert [a.id for a in filtered] == [owned_assessment.id]


async def test_list_assessments_as_teacher_explicit_not_owned_class_id_raises_not_your_class(
    assessment_service: AssessmentService, klass: Class, make_teacher_user
) -> None:
    # `klass` (owned by an unrelated random teacher_id) is passed explicitly
    # as the class_id filter — an explicit request for a class this teacher
    # doesn't teach must be rejected outright, not silently ignored/filtered
    # (same interaction GradeService.list() already established).
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await assessment_service.list(teacher_user, class_id=klass.id, limit=50, offset=0)


async def test_list_assessments_as_teacher_with_no_linked_teacher_record_returns_empty(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    klass: Class,
) -> None:
    await assessment_repository.add(make_assessment_instance(class_id=klass.id))
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)

    assessments, total = await assessment_service.list(orphan_teacher_user, limit=50, offset=0)

    assert assessments == []
    assert total == 0


# ---------------------------------------------------------------------------
# AssessmentService.update
# ---------------------------------------------------------------------------


async def test_update_assessment_success(
    assessment_service: AssessmentService, admin_user: User, assessment: Assessment
) -> None:
    updated = await assessment_service.update(
        admin_user, assessment.id, AssessmentUpdate(name="Final Exam", max_score=Decimal("150.00"))
    )

    assert updated.id == assessment.id
    assert updated.name == "Final Exam"
    assert updated.max_score == Decimal("150.00")


async def test_update_assessment_nonexistent_class_raises(
    assessment_service: AssessmentService, admin_user: User, assessment: Assessment
) -> None:
    with pytest.raises(ClassNotFoundError):
        await assessment_service.update(
            admin_user, assessment.id, AssessmentUpdate(class_id=uuid4())
        )


async def test_update_assessment_missing_raises(
    assessment_service: AssessmentService, admin_user: User
) -> None:
    with pytest.raises(AssessmentNotFoundError):
        await assessment_service.update(admin_user, uuid4(), AssessmentUpdate(name="Nobody"))


async def test_update_assessment_as_teacher_who_owns_class_succeeds(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id)
    )

    updated = await assessment_service.update(
        teacher_user, owned_assessment.id, AssessmentUpdate(name="Retake")
    )

    assert updated.name == "Retake"


async def test_update_assessment_as_teacher_not_owning_current_class_raises_not_your_class(
    assessment_service: AssessmentService, assessment: Assessment, make_teacher_user
) -> None:
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await assessment_service.update(
            teacher_user, assessment.id, AssessmentUpdate(name="Retake")
        )


async def test_update_assessment_as_teacher_reassigning_to_unowned_class_raises_not_your_class(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id)
    )
    unowned_class = await class_repository.add(make_class_instance())

    with pytest.raises(NotYourClassError):
        await assessment_service.update(
            teacher_user, owned_assessment.id, AssessmentUpdate(class_id=unowned_class.id)
        )


async def test_update_assessment_as_admin_succeeds_regardless_of_ownership(
    assessment_service: AssessmentService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    someone_elses_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=someone_elses_class.id)
    )

    updated = await assessment_service.update(
        admin_user, someone_elses_assessment.id, AssessmentUpdate(name="Retake")
    )

    assert updated.name == "Retake"


# ---------------------------------------------------------------------------
# AssessmentService.delete
# ---------------------------------------------------------------------------


async def test_delete_assessment_success(
    assessment_service: AssessmentService, admin_user: User, assessment: Assessment
) -> None:
    await assessment_service.delete(admin_user, assessment.id)

    with pytest.raises(AssessmentNotFoundError):
        await assessment_service.get(admin_user, assessment.id)


async def test_delete_assessment_missing_raises(
    assessment_service: AssessmentService, admin_user: User
) -> None:
    with pytest.raises(AssessmentNotFoundError):
        await assessment_service.delete(admin_user, uuid4())


async def test_delete_assessment_as_teacher_who_owns_class_succeeds(
    assessment_service: AssessmentService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id)
    )

    await assessment_service.delete(teacher_user, owned_assessment.id)

    with pytest.raises(AssessmentNotFoundError):
        await assessment_service.get(teacher_user, owned_assessment.id)


async def test_delete_assessment_as_teacher_not_owning_class_raises_not_your_class(
    assessment_service: AssessmentService, assessment: Assessment, make_teacher_user
) -> None:
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await assessment_service.delete(teacher_user, assessment.id)


async def test_delete_assessment_as_admin_succeeds_regardless_of_ownership(
    assessment_service: AssessmentService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    someone_elses_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=someone_elses_class.id)
    )

    await assessment_service.delete(admin_user, someone_elses_assessment.id)

    with pytest.raises(AssessmentNotFoundError):
        await assessment_service.get(admin_user, someone_elses_assessment.id)


# ---------------------------------------------------------------------------
# GradeService.create
# ---------------------------------------------------------------------------


async def test_create_grade_success(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    data = GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("85.00"))

    grade = await grade_service.create(admin_user, data)

    assert grade.id is not None
    assert grade.assessment_id == assessment.id
    assert grade.student_id == student.id
    assert grade.score == Decimal("85.00")


async def test_create_grade_nonexistent_assessment_raises(
    grade_service: GradeService, admin_user: User, student: Student
) -> None:
    data = GradeCreate(assessment_id=uuid4(), student_id=student.id, score=Decimal("10.00"))

    with pytest.raises(AssessmentNotFoundError):
        await grade_service.create(admin_user, data)


async def test_create_grade_nonexistent_student_raises(
    grade_service: GradeService, admin_user: User, assessment: Assessment
) -> None:
    data = GradeCreate(assessment_id=assessment.id, student_id=uuid4(), score=Decimal("10.00"))

    with pytest.raises(StudentNotFoundError):
        await grade_service.create(admin_user, data)


async def test_create_grade_score_exceeds_max_score_raises(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    data = GradeCreate(
        assessment_id=assessment.id, student_id=student.id, score=assessment.max_score + Decimal("1")
    )

    with pytest.raises(ScoreExceedsMaxScoreError):
        await grade_service.create(admin_user, data)


async def test_create_grade_student_not_enrolled_raises(
    grade_service: GradeService, admin_user: User, assessment: Assessment, student: Student
) -> None:
    # deliberately no enrollment created for this student/class pair
    data = GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00"))

    with pytest.raises(StudentNotEnrolledError):
        await grade_service.create(admin_user, data)


async def test_create_grade_student_enrollment_dropped_raises(
    grade_service: GradeService,
    admin_user: User,
    enrollment_repository: FakeEnrollmentRepository,
    assessment: Assessment,
    student: Student,
    klass: Class,
) -> None:
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=klass.id, status=EnrollmentStatus.DROPPED
        )
    )
    data = GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00"))

    with pytest.raises(StudentNotEnrolledError):
        await grade_service.create(admin_user, data)


async def test_create_grade_duplicate_raises(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    data = GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00"))
    await grade_service.create(admin_user, data)

    with pytest.raises(GradeAlreadyExistsError):
        await grade_service.create(admin_user, data)


async def test_create_grade_as_teacher_who_owns_class_succeeds(
    grade_service: GradeService,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id, max_score=Decimal("100.00"))
    )
    student = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=owned_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    data = GradeCreate(assessment_id=owned_assessment.id, student_id=student.id, score=Decimal("70.00"))

    grade = await grade_service.create(teacher_user, data)

    assert grade.student_id == student.id


async def test_create_grade_as_teacher_not_owning_class_raises_not_your_class(
    grade_service: GradeService,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
    make_teacher_user,
) -> None:
    teacher_user, _teacher = await make_teacher_user()
    data = GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("70.00"))

    with pytest.raises(NotYourClassError):
        await grade_service.create(teacher_user, data)


async def test_create_grade_as_teacher_with_no_linked_teacher_record_raises_not_your_class(
    grade_service: GradeService, assessment: Assessment, student: Student, active_enrollment: Enrollment
) -> None:
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)
    data = GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("70.00"))

    with pytest.raises(NotYourClassError):
        await grade_service.create(orphan_teacher_user, data)


async def test_create_grade_as_admin_succeeds_regardless_of_ownership(
    grade_service: GradeService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    someone_elses_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=someone_elses_class.id, max_score=Decimal("100.00"))
    )
    student = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=someone_elses_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    data = GradeCreate(
        assessment_id=someone_elses_assessment.id, student_id=student.id, score=Decimal("70.00")
    )

    grade = await grade_service.create(admin_user, data)

    assert grade.student_id == student.id


# ---------------------------------------------------------------------------
# GradeService.get
# ---------------------------------------------------------------------------


async def test_get_grade_as_admin_returns_any_students_grade(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("60.00"))
    )

    fetched = await grade_service.get(admin_user, grade.id)

    assert fetched.id == grade.id


async def test_get_grade_as_teacher_who_owns_class_returns_grade(
    grade_service: GradeService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    make_teacher_user,
) -> None:
    # Fixed version of the pre-restriction test (formerly
    # test_get_grade_as_teacher_returns_any_students_grade) — under the new
    # ownership restriction a TEACHER can only view grades for classes they
    # actually teach, so this now sets up an owned class rather than
    # asserting unrestricted access.
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id, max_score=Decimal("100.00"))
    )
    student = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=owned_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    grade = await grade_service.create(
        admin_user,
        GradeCreate(assessment_id=owned_assessment.id, student_id=student.id, score=Decimal("60.00")),
    )

    fetched = await grade_service.get(teacher_user, grade.id)

    assert fetched.id == grade.id


async def test_get_grade_as_teacher_not_owning_class_raises_not_your_class(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
    make_teacher_user,
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("60.00"))
    )
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await grade_service.get(teacher_user, grade.id)


async def test_get_grade_as_teacher_with_no_linked_teacher_record_raises_not_your_class(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("60.00"))
    )
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)

    with pytest.raises(NotYourClassError):
        await grade_service.get(orphan_teacher_user, grade.id)


async def test_get_grade_missing_raises(grade_service: GradeService) -> None:
    admin = make_user_instance(role=UserRole.ADMIN)

    with pytest.raises(GradeNotFoundError):
        await grade_service.get(admin, uuid4())


async def test_get_grade_as_owning_student_returns_own_grade(
    grade_service: GradeService,
    admin_user: User,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assessment: Assessment,
    klass: Class,
) -> None:
    user = make_user_instance(role=UserRole.STUDENT)
    linked_student = await student_repository.add(make_student_instance(user_id=user.id))
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=linked_student.id, class_id=klass.id, status=EnrollmentStatus.ACTIVE
        )
    )
    grade = await grade_service.create(
        admin_user,
        GradeCreate(
            assessment_id=assessment.id, student_id=linked_student.id, score=Decimal("60.00")
        ),
    )

    fetched = await grade_service.get(user, grade.id)

    assert fetched.id == grade.id


async def test_get_grade_as_different_student_raises_not_found(
    grade_service: GradeService,
    admin_user: User,
    student_repository: FakeStudentRepository,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    # `student` (via `active_enrollment`) owns the grade; `other_user` is a
    # *different* linked Student altogether — must be hidden as a 404, not
    # a 403 (deliberately doesn't reveal the grade exists at all).
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("60.00"))
    )
    other_user = make_user_instance(role=UserRole.STUDENT)
    await student_repository.add(make_student_instance(user_id=other_user.id))

    with pytest.raises(GradeNotFoundError):
        await grade_service.get(other_user, grade.id)


async def test_get_grade_as_student_with_no_linked_record_raises_not_found(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("60.00"))
    )
    orphan_user = make_user_instance(role=UserRole.STUDENT)  # no linked Student record at all

    with pytest.raises(GradeNotFoundError):
        await grade_service.get(orphan_user, grade.id)


# ---------------------------------------------------------------------------
# GradeService.list
# ---------------------------------------------------------------------------


async def test_list_grades_as_admin_returns_everything_matching_filters(
    grade_service: GradeService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    klass: Class,
    assessment: Assessment,
) -> None:
    other_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=klass.id, max_score=Decimal("100.00"))
    )
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    for s in (student_a, student_b):
        await enrollment_repository.add(
            make_enrollment_instance(
                student_id=s.id, class_id=klass.id, status=EnrollmentStatus.ACTIVE
            )
        )
    grade_a = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student_a.id, score=Decimal("50.00"))
    )
    await grade_service.create(
        admin_user,
        GradeCreate(
            assessment_id=other_assessment.id, student_id=student_a.id, score=Decimal("70.00")
        ),
    )
    await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student_b.id, score=Decimal("90.00"))
    )

    all_grades, all_total = await grade_service.list(admin_user, limit=50, offset=0)
    assert len(all_grades) == 3
    assert all_total == 3

    by_assessment, by_assessment_total = await grade_service.list(
        admin_user, assessment_id=assessment.id, limit=50, offset=0
    )
    assert len(by_assessment) == 2
    assert by_assessment_total == 2
    assert {g.assessment_id for g in by_assessment} == {assessment.id}
    assert grade_a.id in {g.id for g in by_assessment}

    by_class, by_class_total = await grade_service.list(
        admin_user, class_id=klass.id, limit=50, offset=0
    )
    assert len(by_class) == 3
    assert by_class_total == 3

    by_student, by_student_total = await grade_service.list(
        admin_user, student_id=student_a.id, limit=50, offset=0
    )
    assert len(by_student) == 2
    assert by_student_total == 2
    assert {g.student_id for g in by_student} == {student_a.id}


async def test_list_grades_pagination_slices_and_reports_total(
    grade_service: GradeService,
    admin_user: User,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assessment: Assessment,
    klass: Class,
) -> None:
    for i in range(5):
        student = await student_repository.add(make_student_instance())
        await enrollment_repository.add(
            make_enrollment_instance(
                student_id=student.id, class_id=klass.id, status=EnrollmentStatus.ACTIVE
            )
        )
        await grade_service.create(
            admin_user,
            GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00")),
        )

    page, total = await grade_service.list(admin_user, limit=2, offset=0)

    assert len(page) == 2
    assert total == 5


async def test_list_grades_newest_first_ordering(
    grade_service: GradeService,
    admin_user: User,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assessment: Assessment,
    klass: Class,
) -> None:
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    for s in (student_a, student_b):
        await enrollment_repository.add(
            make_enrollment_instance(
                student_id=s.id, class_id=klass.id, status=EnrollmentStatus.ACTIVE
            )
        )
    first = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student_a.id, score=Decimal("50.00"))
    )
    second = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student_b.id, score=Decimal("60.00"))
    )

    page, total = await grade_service.list(admin_user, limit=50, offset=0)

    assert total == 2
    assert [g.id for g in page] == [second.id, first.id]


async def test_list_grades_as_student_returns_only_own_ignoring_student_id_filter(
    grade_service: GradeService,
    admin_user: User,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    assessment: Assessment,
    klass: Class,
) -> None:
    user = make_user_instance(role=UserRole.STUDENT)
    own_student = await student_repository.add(make_student_instance(user_id=user.id))
    other_student = await student_repository.add(make_student_instance())
    for s in (own_student, other_student):
        await enrollment_repository.add(
            make_enrollment_instance(
                student_id=s.id, class_id=klass.id, status=EnrollmentStatus.ACTIVE
            )
        )
    own_grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=own_student.id, score=Decimal("55.00"))
    )
    await grade_service.create(
        admin_user,
        GradeCreate(
            assessment_id=assessment.id, student_id=other_student.id, score=Decimal("65.00")
        ),
    )

    # Passes someone else's student_id explicitly — the service must
    # override it with the caller's own linked student id, not honor it.
    results, total = await grade_service.list(
        user, student_id=other_student.id, limit=50, offset=0
    )

    assert len(results) == 1
    assert total == 1
    assert results[0].id == own_grade.id


async def test_list_grades_as_student_with_no_linked_record_returns_empty(
    grade_service: GradeService,
) -> None:
    orphan_user = make_user_instance(role=UserRole.STUDENT)

    results, total = await grade_service.list(orphan_user, limit=50, offset=0)

    assert results == []
    assert total == 0


async def test_list_grades_as_teacher_returns_only_own_classes_grades(
    grade_service: GradeService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    other_class = await class_repository.add(make_class_instance())
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id, max_score=Decimal("100.00"))
    )
    other_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=other_class.id, max_score=Decimal("100.00"))
    )
    owned_student = await student_repository.add(make_student_instance())
    other_student = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=owned_student.id, class_id=owned_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=other_student.id, class_id=other_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    owned_grade = await grade_service.create(
        admin_user,
        GradeCreate(
            assessment_id=owned_assessment.id, student_id=owned_student.id, score=Decimal("50.00")
        ),
    )
    await grade_service.create(
        admin_user,
        GradeCreate(
            assessment_id=other_assessment.id, student_id=other_student.id, score=Decimal("60.00")
        ),
    )

    results, total = await grade_service.list(teacher_user, limit=50, offset=0)

    assert [g.id for g in results] == [owned_grade.id]
    assert total == 1


async def test_list_grades_as_teacher_with_no_linked_teacher_record_returns_empty(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
) -> None:
    await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("60.00"))
    )
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)

    results, total = await grade_service.list(orphan_teacher_user, limit=50, offset=0)

    assert results == []
    assert total == 0


async def test_list_grades_as_teacher_explicit_class_id_not_owned_raises_not_your_class(
    grade_service: GradeService, klass: Class, make_teacher_user
) -> None:
    # `klass` (owned by an unrelated random teacher_id) is passed explicitly
    # as the class_id filter — an explicit request for a class this teacher
    # doesn't teach must be rejected outright, not silently ignored/filtered.
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await grade_service.list(teacher_user, class_id=klass.id, limit=50, offset=0)


# ---------------------------------------------------------------------------
# GradeService.update
# ---------------------------------------------------------------------------


async def test_update_grade_success(
    grade_service: GradeService, admin_user: User, assessment: Assessment, student: Student, active_enrollment: Enrollment
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00"))
    )

    updated = await grade_service.update(admin_user, grade.id, GradeUpdate(score=Decimal("75.00")))

    assert updated.id == grade.id
    assert updated.score == Decimal("75.00")


async def test_update_grade_score_exceeds_max_score_raises(
    grade_service: GradeService, admin_user: User, assessment: Assessment, student: Student, active_enrollment: Enrollment
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00"))
    )

    with pytest.raises(ScoreExceedsMaxScoreError):
        await grade_service.update(
            admin_user, grade.id, GradeUpdate(score=assessment.max_score + Decimal("1"))
        )


async def test_update_grade_missing_raises(grade_service: GradeService, admin_user: User) -> None:
    with pytest.raises(GradeNotFoundError):
        await grade_service.update(admin_user, uuid4(), GradeUpdate(score=Decimal("10.00")))


async def test_update_grade_as_teacher_who_owns_class_succeeds(
    grade_service: GradeService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    owned_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=owned_class.id, max_score=Decimal("100.00"))
    )
    student = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=owned_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    grade = await grade_service.create(
        admin_user,
        GradeCreate(assessment_id=owned_assessment.id, student_id=student.id, score=Decimal("50.00")),
    )

    updated = await grade_service.update(teacher_user, grade.id, GradeUpdate(score=Decimal("80.00")))

    assert updated.score == Decimal("80.00")


async def test_update_grade_as_teacher_not_owning_class_raises_not_your_class(
    grade_service: GradeService,
    admin_user: User,
    assessment: Assessment,
    student: Student,
    active_enrollment: Enrollment,
    make_teacher_user,
) -> None:
    grade = await grade_service.create(
        admin_user, GradeCreate(assessment_id=assessment.id, student_id=student.id, score=Decimal("50.00"))
    )
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await grade_service.update(teacher_user, grade.id, GradeUpdate(score=Decimal("80.00")))


async def test_update_grade_as_admin_succeeds_regardless_of_ownership(
    grade_service: GradeService,
    admin_user: User,
    assessment_repository: FakeAssessmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    enrollment_repository: FakeEnrollmentRepository,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    someone_elses_assessment = await assessment_repository.add(
        make_assessment_instance(class_id=someone_elses_class.id, max_score=Decimal("100.00"))
    )
    student = await student_repository.add(make_student_instance())
    await enrollment_repository.add(
        make_enrollment_instance(
            student_id=student.id, class_id=someone_elses_class.id, status=EnrollmentStatus.ACTIVE
        )
    )
    grade = await grade_service.create(
        admin_user,
        GradeCreate(
            assessment_id=someone_elses_assessment.id, student_id=student.id, score=Decimal("50.00")
        ),
    )

    updated = await grade_service.update(admin_user, grade.id, GradeUpdate(score=Decimal("80.00")))

    assert updated.score == Decimal("80.00")
