from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.classes.exceptions import ClassNotFoundError, NotYourClassError
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
from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing enrolled_at stamps, same pattern as
# tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeEnrollmentRepository(AbstractRepository[Enrollment]):
    """In-memory stand-in for EnrollmentRepository. add() mirrors
    uq_enrollments_student_class the same "pre-check narrows the window,
    doesn't close it" way as every other domain's fake (see docs/adr/0004) —
    it's the IntegrityError EnrollmentService.enroll's try/except is meant
    to catch when the pre-check misses a race. list()'s class_ids filter
    mirrors AssessmentRepository/GradeRepository's class_id/class_ids split
    (tests/domains/assessments/unit/test_service.py) — class_id (singular)
    is the pre-existing explicit filter, class_ids (plural) is the new
    TEACHER-ownership scoping filter. list() otherwise mirrors the real
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
        class_ids: list[UUID] | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Enrollment], int]:
        results = list(self._enrollments.values())
        if student_id is not None:
            results = [e for e in results if e.student_id == student_id]
        if class_id is not None:
            results = [e for e in results if e.class_id == class_id]
        if class_ids is not None:
            results = [e for e in results if e.class_id in class_ids]
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
    this fake needs to (or can) simulate. list_by_teacher_id() is the new
    TEACHER-ownership scoping lookup, mirroring
    tests/domains/assessments/unit/test_service.py's identical fake."""

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
    # this same class body. See the identical comment in
    # tests/domains/assessments/unit/test_service.py's FakeClassRepository.
    async def list_by_teacher_id(self, teacher_id: UUID) -> list[Class]:
        return [c for c in self._classes.values() if c.teacher_id == teacher_id]

    async def list(self) -> list[Class]:
        return list(self._classes.values())

    async def remove(self, entity: Class) -> None:
        self._classes.pop(entity.id, None)

    async def get_for_update(self, entity_id: UUID) -> Class | None:
        return self._classes.get(entity_id)


class FakeStudentRepository(AbstractRepository[Student]):
    """Minimal in-memory stand-in for StudentRepository. EnrollmentService
    calls .get() on it (existence check) and .get_by_user_id() (the STUDENT
    self-scoping helper) — same shape/reasoning as
    tests/domains/assessments/unit/test_service.py's identical fake."""

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
    exercised directly by EnrollmentService's new _get_my_teacher_id-style
    ownership helper — same shape/reasoning as
    tests/domains/assessments/unit/test_service.py's identical fake."""

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
def teacher_repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def enrollment_service(
    enrollment_repository: FakeEnrollmentRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    teacher_repository: FakeTeacherRepository,
) -> EnrollmentService:
    return EnrollmentService(
        enrollment_repository, class_repository, student_repository, teacher_repository
    )


@pytest.fixture
async def student(student_repository: FakeStudentRepository) -> Student:
    return await student_repository.add(make_student_instance())


@pytest.fixture
async def klass(class_repository: FakeClassRepository) -> Class:
    return await class_repository.add(make_class_instance(capacity=30))


@pytest.fixture
def admin_user() -> User:
    return make_user_instance(role=UserRole.ADMIN)


@pytest.fixture
def make_teacher_user(teacher_repository: FakeTeacherRepository):
    """Factory: create a TEACHER-role User linked to a new Teacher record
    via user_id. Returns (user, teacher) — the caller assigns
    Class.teacher_id = teacher.id itself when it needs a class this teacher
    owns, or uses an unrelated class/teacher_id for the not-owned case.
    Mirrors tests/domains/assessments/unit/test_service.py's identical
    fixture."""

    async def _make() -> tuple[User, Teacher]:
        user = make_user_instance(role=UserRole.TEACHER)
        teacher = await teacher_repository.add(make_teacher_instance(user_id=user.id))
        return user, teacher

    return _make


@pytest.fixture
def make_student_user(student_repository: FakeStudentRepository):
    """Factory: create a STUDENT-role User linked to a new Student record
    via user_id. Returns (user, student) — the STUDENT-side mirror of
    make_teacher_user above, for the self-scoping tests."""

    async def _make() -> tuple[User, Student]:
        user = make_user_instance(role=UserRole.STUDENT)
        student = await student_repository.add(make_student_instance(user_id=user.id))
        return user, student

    return _make


# ---------------------------------------------------------------------------
# enroll
# ---------------------------------------------------------------------------


async def test_enroll_success(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    enrollment = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    assert enrollment.id is not None
    assert enrollment.student_id == student.id
    assert enrollment.class_id == klass.id
    assert enrollment.status == EnrollmentStatus.ACTIVE


async def test_enroll_nonexistent_student_raises(
    enrollment_service: EnrollmentService, admin_user: User, klass: Class
) -> None:
    with pytest.raises(StudentNotFoundError):
        await enrollment_service.enroll(
            admin_user, EnrollmentCreate(student_id=uuid4(), class_id=klass.id)
        )


async def test_enroll_nonexistent_class_raises(
    enrollment_service: EnrollmentService, admin_user: User, student: Student
) -> None:
    with pytest.raises(ClassNotFoundError):
        await enrollment_service.enroll(
            admin_user, EnrollmentCreate(student_id=student.id, class_id=uuid4())
        )


async def test_enroll_already_enrolled_raises(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    with pytest.raises(EnrollmentAlreadyExistsError):
        await enrollment_service.enroll(
            admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
        )


async def test_enroll_class_at_capacity_raises(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    full_class = await class_repository.add(make_class_instance(capacity=1))
    first_student = await student_repository.add(make_student_instance())
    second_student = await student_repository.add(make_student_instance())

    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=first_student.id, class_id=full_class.id)
    )

    with pytest.raises(ClassFullError):
        await enrollment_service.enroll(
            admin_user, EnrollmentCreate(student_id=second_student.id, class_id=full_class.id)
        )


async def test_enroll_succeeds_up_to_exactly_capacity(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    two_seat_class = await class_repository.add(make_class_instance(capacity=2))
    first_student = await student_repository.add(make_student_instance())
    second_student = await student_repository.add(make_student_instance())

    first = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=first_student.id, class_id=two_seat_class.id)
    )
    second = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=second_student.id, class_id=two_seat_class.id)
    )

    assert first.status == EnrollmentStatus.ACTIVE
    assert second.status == EnrollmentStatus.ACTIVE


async def test_enroll_as_teacher_who_owns_class_succeeds(
    enrollment_service: EnrollmentService,
    class_repository: FakeClassRepository,
    student: Student,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))

    enrollment = await enrollment_service.enroll(
        teacher_user, EnrollmentCreate(student_id=student.id, class_id=owned_class.id)
    )

    assert enrollment.class_id == owned_class.id


async def test_enroll_as_teacher_not_owning_class_raises_not_your_class(
    enrollment_service: EnrollmentService, student: Student, klass: Class, make_teacher_user
) -> None:
    # `klass` is owned by an unrelated random teacher_id, not this teacher.
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await enrollment_service.enroll(
            teacher_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
        )


async def test_enroll_as_teacher_with_no_linked_teacher_record_raises_not_your_class(
    enrollment_service: EnrollmentService, student: Student, klass: Class
) -> None:
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)  # no linked Teacher record

    with pytest.raises(NotYourClassError):
        await enrollment_service.enroll(
            orphan_teacher_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
        )


async def test_enroll_as_admin_succeeds_regardless_of_ownership(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student: Student,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))

    enrollment = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=someone_elses_class.id)
    )

    assert enrollment.class_id == someone_elses_class.id


# ---------------------------------------------------------------------------
# get
# ---------------------------------------------------------------------------


async def test_get_success(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    fetched = await enrollment_service.get(admin_user, created.id)

    assert fetched.id == created.id


async def test_get_missing_raises(enrollment_service: EnrollmentService, admin_user: User) -> None:
    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.get(admin_user, uuid4())


async def test_get_as_teacher_who_owns_class_succeeds(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student: Student,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=owned_class.id)
    )

    fetched = await enrollment_service.get(teacher_user, created.id)

    assert fetched.id == created.id


async def test_get_as_teacher_not_owning_class_raises_not_your_class(
    enrollment_service: EnrollmentService,
    admin_user: User,
    student: Student,
    klass: Class,
    make_teacher_user,
) -> None:
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await enrollment_service.get(teacher_user, created.id)


async def test_get_as_teacher_with_no_linked_teacher_record_raises_not_your_class(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)

    with pytest.raises(NotYourClassError):
        await enrollment_service.get(orphan_teacher_user, created.id)


async def test_get_as_admin_succeeds_regardless_of_ownership(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student: Student,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=someone_elses_class.id)
    )

    fetched = await enrollment_service.get(admin_user, created.id)

    assert fetched.id == created.id


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


async def test_list_no_filters_returns_everything(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_b.id, class_id=class_b.id)
    )

    enrollments, total = await enrollment_service.list(admin_user, limit=50, offset=0)

    assert len(enrollments) == 2
    assert total == 2


async def test_list_pagination_smoke(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    for _ in range(3):
        klass = await class_repository.add(make_class_instance(capacity=10))
        student = await student_repository.add(make_student_instance())
        await enrollment_service.enroll(
            admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
        )

    page, total = await enrollment_service.list(admin_user, limit=2, offset=0)

    assert len(page) == 2
    assert total == 3


async def test_list_filtered_by_student_id(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_b.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_b.id, class_id=class_a.id)
    )

    enrollments, total = await enrollment_service.list(
        admin_user, student_id=student_a.id, limit=50, offset=0
    )

    assert len(enrollments) == 2
    assert total == 2
    assert {e.class_id for e in enrollments} == {class_a.id, class_b.id}


async def test_list_filtered_by_class_id(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_b.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_b.id)
    )

    enrollments, total = await enrollment_service.list(
        admin_user, class_id=class_a.id, limit=50, offset=0
    )

    assert len(enrollments) == 2
    assert total == 2
    assert {e.student_id for e in enrollments} == {student_a.id, student_b.id}


async def test_list_filtered_by_both(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
) -> None:
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    target = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=class_b.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_b.id, class_id=class_a.id)
    )

    enrollments, total = await enrollment_service.list(
        admin_user, student_id=student_a.id, class_id=class_a.id, limit=50, offset=0
    )

    assert len(enrollments) == 1
    assert total == 1
    assert enrollments[0].id == target.id


async def test_list_as_teacher_omitted_class_id_restricted_to_own_classes(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    other_class = await class_repository.add(make_class_instance())
    owned_student = await student_repository.add(make_student_instance())
    other_student = await student_repository.add(make_student_instance())
    owned_enrollment = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=owned_student.id, class_id=owned_class.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=other_student.id, class_id=other_class.id)
    )

    enrollments, total = await enrollment_service.list(teacher_user, limit=50, offset=0)

    assert total == 1
    assert [e.id for e in enrollments] == [owned_enrollment.id]


async def test_list_as_teacher_explicit_owned_class_id_succeeds(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    other_owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    student_a = await student_repository.add(make_student_instance())
    student_b = await student_repository.add(make_student_instance())
    target = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_a.id, class_id=owned_class.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student_b.id, class_id=other_owned_class.id)
    )

    enrollments, total = await enrollment_service.list(
        teacher_user, class_id=owned_class.id, limit=50, offset=0
    )

    assert total == 1
    assert [e.id for e in enrollments] == [target.id]


async def test_list_as_teacher_explicit_not_owned_class_id_raises_not_your_class(
    enrollment_service: EnrollmentService, klass: Class, make_teacher_user
) -> None:
    # `klass` (owned by an unrelated random teacher_id) is passed explicitly
    # as the class_id filter — an explicit request for a class this teacher
    # doesn't teach must be rejected outright, not silently ignored/filtered
    # (same interaction Assessment/GradeService already established).
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await enrollment_service.list(teacher_user, class_id=klass.id, limit=50, offset=0)


async def test_list_as_teacher_with_no_linked_teacher_record_returns_empty(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    orphan_teacher_user = make_user_instance(role=UserRole.TEACHER)

    enrollments, total = await enrollment_service.list(orphan_teacher_user, limit=50, offset=0)

    assert enrollments == []
    assert total == 0


async def test_list_as_teacher_owning_zero_classes_returns_empty_not_error(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class, make_teacher_user
) -> None:
    # A linked Teacher record that simply doesn't teach anything yet — must
    # behave the same as the no-linked-record case (empty list), not raise.
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    teacher_user, _teacher = await make_teacher_user()

    enrollments, total = await enrollment_service.list(teacher_user, limit=50, offset=0)

    assert enrollments == []
    assert total == 0


# ---------------------------------------------------------------------------
# STUDENT self-scoping (list + get)
# ---------------------------------------------------------------------------


async def test_list_as_student_returns_only_own_enrollments(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    make_student_user,
) -> None:
    # A STUDENT sees only their own enrollments — never a classmate's.
    # Same self-scoping shape GradeService already applies (docs/adr/0018).
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_user, my_student = await make_student_user()
    other_student = await student_repository.add(make_student_instance())
    mine = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=my_student.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=other_student.id, class_id=class_b.id)
    )

    enrollments, total = await enrollment_service.list(student_user, limit=50, offset=0)

    assert total == 1
    assert [e.id for e in enrollments] == [mine.id]


async def test_list_as_student_ignores_explicit_other_student_id_filter(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    make_student_user,
) -> None:
    # Passing someone else's student_id must not widen the scope — the
    # caller's own id overrides whatever was supplied.
    class_a = await class_repository.add(make_class_instance(capacity=10))
    student_user, my_student = await make_student_user()
    other_student = await student_repository.add(make_student_instance())
    mine = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=my_student.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=other_student.id, class_id=class_a.id)
    )

    enrollments, total = await enrollment_service.list(
        student_user, limit=50, offset=0, student_id=other_student.id
    )

    assert total == 1
    assert [e.id for e in enrollments] == [mine.id]


async def test_list_as_student_can_still_filter_own_by_class_id(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    make_student_user,
) -> None:
    # Narrowing within their own scope still works — the override only
    # pins student_id, it doesn't discard class_id.
    class_a = await class_repository.add(make_class_instance(capacity=10))
    class_b = await class_repository.add(make_class_instance(capacity=10))
    student_user, my_student = await make_student_user()
    in_a = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=my_student.id, class_id=class_a.id)
    )
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=my_student.id, class_id=class_b.id)
    )

    enrollments, total = await enrollment_service.list(
        student_user, limit=50, offset=0, class_id=class_a.id
    )

    assert total == 1
    assert [e.id for e in enrollments] == [in_a.id]


async def test_list_as_student_with_no_linked_record_returns_empty(
    enrollment_service: EnrollmentService,
    admin_user: User,
    student: Student,
    klass: Class,
) -> None:
    # No linked Student record → owns nothing, same "empty scope, not an
    # error" precedent as the no-linked-Teacher case.
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    orphan_student_user = make_user_instance(role=UserRole.STUDENT)

    enrollments, total = await enrollment_service.list(orphan_student_user, limit=50, offset=0)

    assert enrollments == []
    assert total == 0


async def test_get_as_student_own_enrollment_succeeds(
    enrollment_service: EnrollmentService,
    admin_user: User,
    klass: Class,
    make_student_user,
) -> None:
    student_user, my_student = await make_student_user()
    mine = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=my_student.id, class_id=klass.id)
    )

    fetched = await enrollment_service.get(student_user, mine.id)

    assert fetched.id == mine.id


async def test_get_as_student_other_students_enrollment_raises_not_found(
    enrollment_service: EnrollmentService,
    admin_user: User,
    student: Student,
    klass: Class,
    make_student_user,
) -> None:
    # 404, not 403 — a classmate's enrollment must be indistinguishable
    # from one that doesn't exist, so the error itself can't confirm it's
    # real (docs/adr/0018's reasoning, applied here).
    theirs = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    student_user, _my_student = await make_student_user()

    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.get(student_user, theirs.id)


async def test_get_as_student_with_no_linked_record_raises_not_found(
    enrollment_service: EnrollmentService,
    admin_user: User,
    student: Student,
    klass: Class,
) -> None:
    theirs = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    orphan_student_user = make_user_instance(role=UserRole.STUDENT)

    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.get(orphan_student_user, theirs.id)


async def test_get_as_student_nonexistent_id_raises_not_found(
    enrollment_service: EnrollmentService, make_student_user
) -> None:
    # The third of get()'s three STUDENT failure branches — a plain
    # nonexistent id. Must be indistinguishable from "exists but isn't
    # yours" (above) and "no linked record" (above): same exception, same
    # message, same number of DB round-trips.
    student_user, _my_student = await make_student_user()

    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.get(student_user, uuid4())


async def test_list_as_student_filtering_by_unenrolled_class_returns_empty(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    make_student_user,
) -> None:
    # A STUDENT asking about a class they aren't in gets an empty list, not
    # NotYourClassError — that 403 belongs to the TEACHER branch only.
    # Guards against a future reordering of the role branches in list().
    my_class = await class_repository.add(make_class_instance(capacity=10))
    other_class = await class_repository.add(make_class_instance(capacity=10))
    student_user, my_student = await make_student_user()
    await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=my_student.id, class_id=my_class.id)
    )

    enrollments, total = await enrollment_service.list(
        student_user, limit=50, offset=0, class_id=other_class.id
    )

    assert enrollments == []
    assert total == 0


# ---------------------------------------------------------------------------
# drop
# ---------------------------------------------------------------------------


async def test_drop_success(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )

    dropped = await enrollment_service.drop(admin_user, created.id)

    assert dropped.id == created.id
    assert dropped.status == EnrollmentStatus.DROPPED


async def test_drop_already_dropped_raises(
    enrollment_service: EnrollmentService, admin_user: User, student: Student, klass: Class
) -> None:
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    await enrollment_service.drop(admin_user, created.id)

    with pytest.raises(EnrollmentNotActiveError):
        await enrollment_service.drop(admin_user, created.id)


async def test_drop_missing_raises(enrollment_service: EnrollmentService, admin_user: User) -> None:
    with pytest.raises(EnrollmentNotFoundError):
        await enrollment_service.drop(admin_user, uuid4())


async def test_drop_as_teacher_who_owns_class_succeeds(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student: Student,
    make_teacher_user,
) -> None:
    teacher_user, teacher = await make_teacher_user()
    owned_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=owned_class.id)
    )

    dropped = await enrollment_service.drop(teacher_user, created.id)

    assert dropped.status == EnrollmentStatus.DROPPED


async def test_drop_as_teacher_not_owning_class_raises_not_your_class(
    enrollment_service: EnrollmentService,
    admin_user: User,
    student: Student,
    klass: Class,
    make_teacher_user,
) -> None:
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=klass.id)
    )
    teacher_user, _teacher = await make_teacher_user()

    with pytest.raises(NotYourClassError):
        await enrollment_service.drop(teacher_user, created.id)


async def test_drop_as_admin_succeeds_regardless_of_ownership(
    enrollment_service: EnrollmentService,
    admin_user: User,
    class_repository: FakeClassRepository,
    student: Student,
    make_teacher_user,
) -> None:
    _teacher_user, teacher = await make_teacher_user()
    someone_elses_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    created = await enrollment_service.enroll(
        admin_user, EnrollmentCreate(student_id=student.id, class_id=someone_elses_class.id)
    )

    dropped = await enrollment_service.drop(admin_user, created.id)

    assert dropped.status == EnrollmentStatus.DROPPED
