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

        student = Student(
            student_number=data.student_number,
            first_name=data.first_name,
            last_name=data.last_name,
            date_of_birth=data.date_of_birth,
            email=data.email,
            guardian_name=data.guardian_name,
            guardian_phone=data.guardian_phone,
            enrollment_status=EnrollmentStatus.ACTIVE,
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

    async def list(self) -> list[Student]:
        return await self._repository.list()

    async def update(self, student_id: UUID, data: StudentUpdate) -> Student:
        student = await self.get(student_id)
        updates = data.model_dump(exclude_unset=True)
        for field, value in updates.items():
            setattr(student, field, value)
        try:
            return await self._repository.add(student)
        except IntegrityError as exc:
            raise StudentAlreadyExistsError() from exc

    async def delete(self, student_id: UUID) -> None:
        student = await self.get(student_id)
        await self._repository.remove(student)
