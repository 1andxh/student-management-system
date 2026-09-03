from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.academic_years.exceptions import TermNotFoundError
from sms.domains.academic_years.models import Term
from sms.domains.classes.exceptions import (
    ClassNotFoundError,
    SubjectAlreadyExistsError,
    SubjectNotFoundError,
)
from sms.domains.classes.models import Class, Subject
from sms.domains.classes.schemas import ClassCreate, ClassUpdate, SubjectCreate, SubjectUpdate
from sms.domains.classes.service import ClassService, SubjectService
from sms.domains.teachers.exceptions import TeacherNotFoundError
from sms.domains.teachers.models import Teacher

# Arbitrary fixed epoch — only used as a base for the fakes' deterministic,
# monotonically increasing created_at stamps, same pattern as
# tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeSubjectRepository(AbstractRepository[Subject]):
    """In-memory stand-in for SubjectRepository, mirroring
    uq_subjects_code the same "pre-check narrows the window, doesn't close
    it" way as every other domain's fake (see docs/adr/0004)."""

    def __init__(self) -> None:
        self._subjects: dict[UUID, Subject] = {}
        self._sequence = 0

    async def add(self, entity: Subject) -> Subject:
        for existing_id, existing in self._subjects.items():
            if existing_id == entity.id:
                continue
            if existing.code == entity.code:
                raise IntegrityError("duplicate code", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._subjects[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Subject | None:
        return self._subjects.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Subject], int]:
        all_subjects = sorted(self._subjects.values(), key=lambda s: s.created_at, reverse=True)
        return all_subjects[offset : offset + limit], len(all_subjects)

    async def remove(self, entity: Subject) -> None:
        self._subjects.pop(entity.id, None)

    async def get_by_code(self, code: str) -> Subject | None:
        for subject in self._subjects.values():
            if subject.code == code:
                return subject
        return None


class FakeClassRepository(AbstractRepository[Class]):
    """In-memory stand-in for ClassRepository. Unlike every other fake in
    this codebase, add() has no uniqueness check to enforce — Class
    deliberately has no "duplicate" concept (see contract notes on
    __table_args__)."""

    def __init__(self) -> None:
        self._classes: dict[UUID, Class] = {}
        self._sequence = 0

    async def add(self, entity: Class) -> Class:
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._classes[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Class | None:
        return self._classes.get(entity_id)

    async def list(
        self,
        *,
        term_id: UUID | None = None,
        subject_id: UUID | None = None,
        teacher_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Class], int]:
        results = list(self._classes.values())
        if term_id is not None:
            results = [c for c in results if c.term_id == term_id]
        if subject_id is not None:
            results = [c for c in results if c.subject_id == subject_id]
        if teacher_id is not None:
            results = [c for c in results if c.teacher_id == teacher_id]
        results.sort(key=lambda c: c.created_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def remove(self, entity: Class) -> None:
        self._classes.pop(entity.id, None)


class FakeTermRepository(AbstractRepository[Term]):
    """Minimal in-memory stand-in for TermRepository — ClassService only
    ever calls .get() on it (existence check), so add()/list()/remove()
    exist solely to satisfy AbstractRepository."""

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


class FakeTeacherRepository(AbstractRepository[Teacher]):
    """Minimal in-memory stand-in for TeacherRepository — ClassService only
    ever calls .get() on it (existence check)."""

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


def make_subject_create(**overrides: object) -> SubjectCreate:
    defaults: dict[str, object] = {"name": "Mathematics", "code": "MATH101"}
    defaults.update(overrides)
    return SubjectCreate(**defaults)


def make_class_create(
    subject_id: UUID, term_id: UUID, teacher_id: UUID, **overrides: object
) -> ClassCreate:
    defaults: dict[str, object] = {
        "subject_id": subject_id,
        "term_id": term_id,
        "teacher_id": teacher_id,
        "capacity": 30,
        "room": "Room 101",
    }
    defaults.update(overrides)
    return ClassCreate(**defaults)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def subject_repository() -> FakeSubjectRepository:
    return FakeSubjectRepository()


@pytest.fixture
def subject_service(subject_repository: FakeSubjectRepository) -> SubjectService:
    return SubjectService(subject_repository)


@pytest.fixture
def term_repository() -> FakeTermRepository:
    return FakeTermRepository()


@pytest.fixture
def teacher_repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def class_service(
    class_repository: FakeClassRepository,
    subject_repository: FakeSubjectRepository,
    term_repository: FakeTermRepository,
    teacher_repository: FakeTeacherRepository,
) -> ClassService:
    return ClassService(
        class_repository, subject_repository, term_repository, teacher_repository
    )


@pytest.fixture
async def subject(subject_service: SubjectService) -> Subject:
    return await subject_service.create(make_subject_create())


@pytest.fixture
async def term(term_repository: FakeTermRepository) -> Term:
    new_term = Term(
        id=uuid4(),
        academic_year_id=uuid4(),
        name="Term 1",
        start_date=date(2024, 9, 1),
        end_date=date(2024, 12, 20),
    )
    return await term_repository.add(new_term)


@pytest.fixture
async def teacher(teacher_repository: FakeTeacherRepository) -> Teacher:
    new_teacher = Teacher(
        id=uuid4(),
        first_name="Grace",
        last_name="Hopper",
        email="grace@example.com",
        hire_date=date(2015, 6, 1),
    )
    return await teacher_repository.add(new_teacher)


# ---------------------------------------------------------------------------
# SubjectService
# ---------------------------------------------------------------------------


async def test_update_class_nonexistent_teacher_raises(
    class_service: ClassService, subject: Subject, term: Term, teacher: Teacher
) -> None:
    created = await class_service.create(make_class_create(subject.id, term.id, teacher.id))

    with pytest.raises(TeacherNotFoundError):
        await class_service.update(created.id, ClassUpdate(teacher_id=uuid4()))


async def test_update_class_nonexistent_subject_raises(
    class_service: ClassService, subject: Subject, term: Term, teacher: Teacher
) -> None:
    created = await class_service.create(make_class_create(subject.id, term.id, teacher.id))

    with pytest.raises(SubjectNotFoundError):
        await class_service.update(created.id, ClassUpdate(subject_id=uuid4()))


