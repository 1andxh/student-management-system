from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.academic_years.exceptions import TermNotFoundError
from sms.domains.academic_years.repository import TermRepository
from sms.domains.classes.exceptions import (
    ClassNotFoundError,
    SubjectAlreadyExistsError,
    SubjectNotFoundError,
)
from sms.domains.classes.models import Class, Subject
from sms.domains.classes.repository import ClassRepository, SubjectRepository
from sms.domains.classes.schemas import ClassCreate, ClassUpdate, SubjectCreate, SubjectUpdate
from sms.domains.teachers.exceptions import TeacherNotFoundError
from sms.domains.teachers.repository import TeacherRepository


class SubjectService:
    def __init__(self, repository: SubjectRepository) -> None:
        self._repository = repository

    async def create(self, data: SubjectCreate) -> Subject:
        if await self._repository.get_by_code(data.code) is not None:
            raise SubjectAlreadyExistsError()

        subject = Subject(name=data.name, code=data.code)
        try:
            return await self._repository.add(subject)
        except IntegrityError as exc:
            raise SubjectAlreadyExistsError() from exc

    async def get(self, subject_id: UUID) -> Subject:
        subject = await self._repository.get(subject_id)
        if subject is None:
            raise SubjectNotFoundError()
        return subject

    async def list(self, *, limit: int, offset: int) -> tuple[list[Subject], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, subject_id: UUID, data: SubjectUpdate) -> Subject:
        subject = await self.get(subject_id)
        updates = data.model_dump(exclude_unset=True)

        new_code = updates.get("code")
        if new_code is not None and new_code != subject.code:
            existing = await self._repository.get_by_code(new_code)
            if existing is not None and existing.id != subject_id:
                raise SubjectAlreadyExistsError()

        for field, value in updates.items():
            setattr(subject, field, value)
        try:
            return await self._repository.add(subject)
        except IntegrityError as exc:
            raise SubjectAlreadyExistsError() from exc

    async def delete(self, subject_id: UUID) -> None:
        subject = await self.get(subject_id)
        await self._repository.remove(subject)


class ClassService:
    """Depends on TeacherRepository (teachers domain) and TermRepository
    (academic_years domain) alongside its own SubjectRepository — a
    one-way fan-in, not a cycle (neither teachers nor academic_years
    depends back on classes), so this doesn't violate the dependency-free-
    core pattern used elsewhere (that's about avoiding circular
    references, not about a service never touching another domain's
    repository). See docs/adr/0016."""

    def __init__(
        self,
        repository: ClassRepository,
        subject_repository: SubjectRepository,
        term_repository: TermRepository,
        teacher_repository: TeacherRepository,
    ) -> None:
        self._repository = repository
        self._subject_repository = subject_repository
        self._term_repository = term_repository
        self._teacher_repository = teacher_repository

    async def _validate_references(
        self,
        *,
        subject_id: UUID | None = None,
        term_id: UUID | None = None,
        teacher_id: UUID | None = None,
    ) -> None:
        if subject_id is not None and await self._subject_repository.get(subject_id) is None:
            raise SubjectNotFoundError()
        if term_id is not None and await self._term_repository.get(term_id) is None:
            raise TermNotFoundError()
        if teacher_id is not None and await self._teacher_repository.get(teacher_id) is None:
            raise TeacherNotFoundError()

    async def create(self, data: ClassCreate) -> Class:
        await self._validate_references(
            subject_id=data.subject_id, term_id=data.term_id, teacher_id=data.teacher_id
        )

        # No try/except IntegrityError here, deliberately — Class has no
        # uniqueness constraint (nothing to translate a duplicate into),
        # capacity is already Pydantic-validated (Field(gt=0)), and the FK
        # existence checks above already ran. See docs/adr/0016.
        cls = Class(
            subject_id=data.subject_id,
            term_id=data.term_id,
            teacher_id=data.teacher_id,
            capacity=data.capacity,
            room=data.room,
        )
        return await self._repository.add(cls)

    async def get(self, class_id: UUID) -> Class:
        cls = await self._repository.get(class_id)
        if cls is None:
            raise ClassNotFoundError()
        return cls

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        term_id: UUID | None = None,
        subject_id: UUID | None = None,
        teacher_id: UUID | None = None,
    ) -> tuple[list[Class], int]:
        return await self._repository.list(
            limit=limit,
            offset=offset,
            term_id=term_id,
            subject_id=subject_id,
            teacher_id=teacher_id,
        )

    async def update(self, class_id: UUID, data: ClassUpdate) -> Class:
        cls = await self.get(class_id)
        updates = data.model_dump(exclude_unset=True)

        await self._validate_references(
            subject_id=updates.get("subject_id"),
            term_id=updates.get("term_id"),
            teacher_id=updates.get("teacher_id"),
        )

        for field, value in updates.items():
            setattr(cls, field, value)
        return await self._repository.add(cls)

    async def delete(self, class_id: UUID) -> None:
        cls = await self.get(class_id)
        await self._repository.remove(cls)
