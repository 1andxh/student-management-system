from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.classes.exceptions import ClassNotFoundError, NotYourClassError
from sms.domains.classes.models import Class
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
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.users.models import User, UserRole


class EnrollmentService:
    """Depends on ClassRepository (classes domain), StudentRepository
    (students domain), and TeacherRepository (for the teacher-ownership
    check) — the same one-way fan-in shape ClassService itself already
    established (docs/adr/0016), extended with the same TEACHER
    class-ownership scoping AssessmentService/GradeService already use
    (docs/adr/0019), not a new pattern.

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
        teacher_repository: TeacherRepository,
    ) -> None:
        self._repository = repository
        self._class_repository = class_repository
        self._student_repository = student_repository
        self._teacher_repository = teacher_repository

    async def _get_my_teacher_id(self, current_user: User) -> UUID | None:
        my_teacher = await self._teacher_repository.get_by_user_id(current_user.id)
        return my_teacher.id if my_teacher is not None else None

    async def _check_owns_class(self, current_user: User, cls: Class) -> None:
        if current_user.role != UserRole.TEACHER:
            return
        my_teacher_id = await self._get_my_teacher_id(current_user)
        if my_teacher_id is None or cls.teacher_id != my_teacher_id:
            raise NotYourClassError()

    async def enroll(self, current_user: User, data: EnrollmentCreate) -> Enrollment:
        if await self._student_repository.get(data.student_id) is None:
            raise StudentNotFoundError()

        # Locks the Class row — held until this method's own add() commits
        # below. Nothing between here and there may commit on this session.
        cls = await self._class_repository.get_for_update(data.class_id)
        if cls is None:
            raise ClassNotFoundError()

        await self._check_owns_class(current_user, cls)

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

    async def get(self, current_user: User, enrollment_id: UUID) -> Enrollment:
        enrollment = await self._repository.get(enrollment_id)
        if enrollment is None:
            raise EnrollmentNotFoundError()
        if current_user.role == UserRole.TEACHER:
            # Fail closed if the class is unexpectedly missing — same
            # reasoning as Assessment/Grade's fail-closed fixes (docs/adr/0019).
            cls = await self._class_repository.get(enrollment.class_id)
            if cls is None:
                raise NotYourClassError()
            await self._check_owns_class(current_user, cls)
        return enrollment

    async def list(
        self,
        current_user: User,
        *,
        limit: int,
        offset: int,
        student_id: UUID | None = None,
        class_id: UUID | None = None,
    ) -> tuple[list[Enrollment], int]:
        if current_user.role == UserRole.TEACHER:
            my_teacher_id = await self._get_my_teacher_id(current_user)
            if my_teacher_id is None:
                return [], 0
            owned = await self._class_repository.list_by_teacher_id(my_teacher_id)
            owned_ids = {c.id for c in owned}
            if class_id is not None:
                if class_id not in owned_ids:
                    raise NotYourClassError()
                return await self._repository.list(
                    limit=limit, offset=offset, student_id=student_id, class_id=class_id
                )
            return await self._repository.list(
                limit=limit, offset=offset, student_id=student_id, class_ids=list(owned_ids)
            )
        return await self._repository.list(
            limit=limit, offset=offset, student_id=student_id, class_id=class_id
        )

    async def drop(self, current_user: User, enrollment_id: UUID) -> Enrollment:
        enrollment = await self.get(current_user, enrollment_id)
        if enrollment.status != EnrollmentStatus.ACTIVE:
            raise EnrollmentNotActiveError()
        enrollment.status = EnrollmentStatus.DROPPED
        return await self._repository.add(enrollment)
