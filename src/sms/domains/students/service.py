from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.students.exceptions import StudentAlreadyExistsError, StudentNotFoundError
from sms.domains.students.models import EnrollmentStatus, Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import StudentCreate, StudentUpdate


class StudentService:
    def __init__(self, repository: StudentRepository) -> None:
        self._repository = repository

    async def create(self, data: StudentCreate) -> Student:
        if await self._repository.get_by_email(data.email) is not None:
            raise StudentAlreadyExistsError()
        if await self._repository.get_by_student_number(data.student_number) is not None:
            raise StudentAlreadyExistsError()
        if (
            data.user_id is not None
            and await self._repository.get_by_user_id(data.user_id) is not None
        ):
            raise StudentAlreadyExistsError()

        student = Student(
            student_number=data.student_number,
            first_name=data.first_name,
            last_name=data.last_name,
            date_of_birth=data.date_of_birth,
            email=data.email,
            guardian_name=data.guardian_name,
            guardian_phone=data.guardian_phone,
            enrollment_status=EnrollmentStatus.ACTIVE,
            user_id=data.user_id,
        )
        try:
            return await self._repository.add(student)
        except IntegrityError as exc:
            # The pre-checks above narrow the window but don't close it — a
            # concurrent request can still slip past both and hit the unique
            # constraint at commit time. That constraint is the actual
            # guard; this just translates its failure into the same domain
            # error instead of letting it surface as a raw 500.
            raise StudentAlreadyExistsError() from exc

    async def get(self, student_id: UUID) -> Student:
        student = await self._repository.get(student_id)
        if student is None:
            raise StudentNotFoundError()
        return student

    async def list(self, *, limit: int, offset: int) -> tuple[list[Student], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, student_id: UUID, data: StudentUpdate) -> Student:
        student = await self.get(student_id)
        updates = data.model_dump(exclude_unset=True)

        # Pre-checks for every uniqueness field, not just the one this
        # stage is adding (user_id) — matching the fix already established
        # for Teacher (docs/adr/0014): the DB constraint alone isn't
        # exercised by the in-memory unit-test fake, only by a real DB.
        new_email = updates.get("email")
        if new_email is not None and new_email != student.email:
            existing = await self._repository.get_by_email(new_email)
            if existing is not None and existing.id != student_id:
                raise StudentAlreadyExistsError()

        new_number = updates.get("student_number")
        if new_number is not None and new_number != student.student_number:
            existing = await self._repository.get_by_student_number(new_number)
            if existing is not None and existing.id != student_id:
                raise StudentAlreadyExistsError()

        new_user_id = updates.get("user_id")
        if new_user_id is not None and new_user_id != student.user_id:
            existing = await self._repository.get_by_user_id(new_user_id)
            if existing is not None and existing.id != student_id:
                raise StudentAlreadyExistsError()

        for field, value in updates.items():
            setattr(student, field, value)
        try:
            return await self._repository.add(student)
        except IntegrityError as exc:
            raise StudentAlreadyExistsError() from exc

    async def delete(self, student_id: UUID) -> None:
        student = await self.get(student_id)
        await self._repository.remove(student)
