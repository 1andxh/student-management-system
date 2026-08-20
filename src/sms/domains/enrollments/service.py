from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.classes.exceptions import ClassNotFoundError
from sms.domains.classes.repository import ClassRepository
from sms.domains.enrollments.exceptions import (
    ClassFullError,
    EnrollmentAlreadyExistsError,
    EnrollmentNotActiveError,
    EnrollmentNotFoundError,
)
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.enrollments.schemas import EnrollmentCreate
from sms.domains.students.exceptions import StudentNotFoundError
from sms.domains.students.repository import StudentRepository


class EnrollmentService:
    """Depends on ClassRepository (classes domain) and StudentRepository
    (students domain) — the same one-way fan-in shape ClassService itself
    already established (docs/adr/0016), not a new pattern.

    The capacity-race guard needs no shared-commit/Unit-of-Work machinery:
    it's one locking READ (ClassRepository.get_for_update) followed by one
    WRITE (this Enrollment insert), not two writes needing atomicity
    together like UserService's User+AuditLog case (docs/adr/0011). As
    long as nothing commits on this session between the lock and this
    service's own final commit, the lock holds. See docs/adr/0017."""

    def __init__(
        self,
        repository: EnrollmentRepository,
        class_repository: ClassRepository,
        student_repository: StudentRepository,
    ) -> None:
        self._repository = repository
        self._class_repository = class_repository
        self._student_repository = student_repository

    async def enroll(self, data: EnrollmentCreate) -> Enrollment:
        if await self._student_repository.get(data.student_id) is None:
            raise StudentNotFoundError()

        # Locks the Class row — held until this method's own add() commits
        # below. Nothing between here and there may commit on this session.
        cls = await self._class_repository.get_for_update(data.class_id)
        if cls is None:
            raise ClassNotFoundError()

        if (
            await self._repository.get_by_student_and_class(data.student_id, data.class_id)
            is not None
        ):
            raise EnrollmentAlreadyExistsError()

        active_count = await self._repository.count_active_by_class(data.class_id)
        if active_count >= cls.capacity:
            raise ClassFullError()

        enrollment = Enrollment(
            student_id=data.student_id, class_id=data.class_id, status=EnrollmentStatus.ACTIVE
        )
        try:
            return await self._repository.add(enrollment)
        except IntegrityError as exc:
            raise EnrollmentAlreadyExistsError() from exc

    async def get(self, enrollment_id: UUID) -> Enrollment:
        enrollment = await self._repository.get(enrollment_id)
        if enrollment is None:
            raise EnrollmentNotFoundError()
        return enrollment

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        student_id: UUID | None = None,
        class_id: UUID | None = None,
    ) -> tuple[list[Enrollment], int]:
        return await self._repository.list(
            limit=limit, offset=offset, student_id=student_id, class_id=class_id
        )

    async def drop(self, enrollment_id: UUID) -> Enrollment:
        enrollment = await self.get(enrollment_id)
        if enrollment.status != EnrollmentStatus.ACTIVE:
            raise EnrollmentNotActiveError()
        enrollment.status = EnrollmentStatus.DROPPED
        return await self._repository.add(enrollment)
