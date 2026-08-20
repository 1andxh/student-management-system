from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.assessments.exceptions import (
    AssessmentNotFoundError,
    GradeAlreadyExistsError,
    GradeNotFoundError,
    ScoreExceedsMaxScoreError,
    StudentNotEnrolledError,
)
from sms.domains.assessments.models import Assessment, Grade
from sms.domains.assessments.repository import AssessmentRepository, GradeRepository
from sms.domains.assessments.schemas import AssessmentCreate, AssessmentUpdate, GradeCreate, GradeUpdate
from sms.domains.classes.exceptions import ClassNotFoundError, NotYourClassError
from sms.domains.classes.models import Class
from sms.domains.classes.repository import ClassRepository
from sms.domains.enrollments.models import EnrollmentStatus
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.students.exceptions import StudentNotFoundError
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.users.models import User, UserRole


class AssessmentService:
    """A TEACHER caller is restricted to classes they teach (Class.teacher_id
    matches their own linked Teacher.id) — ADMIN/SUPER_ADMIN are
    unrestricted. 403 (NotYourClassError), not 404: unlike Grade's
    student-vs-student scoping, Class existence is already visible to any
    authenticated user via GET /classes, so there's nothing to hide. See
    docs/adr/0019."""

    def __init__(
        self,
        repository: AssessmentRepository,
        class_repository: ClassRepository,
        teacher_repository: TeacherRepository,
    ) -> None:
        self._repository = repository
        self._class_repository = class_repository
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

    async def create(self, current_user: User, data: AssessmentCreate) -> Assessment:
        cls = await self._class_repository.get(data.class_id)
        if cls is None:
            raise ClassNotFoundError()
        await self._check_owns_class(current_user, cls)

        # No IntegrityError wrapping, deliberately — same reasoning as
        # ClassService.create() (docs/adr/0016): no uniqueness concept for
        # Assessment, and max_score is already Pydantic-validated.
        assessment = Assessment(
            class_id=data.class_id,
            name=data.name,
            type=data.type,
            max_score=data.max_score,
            date=data.date,
        )
        return await self._repository.add(assessment)

    async def get(self, current_user: User, assessment_id: UUID) -> Assessment:
        assessment = await self._repository.get(assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()
        if current_user.role == UserRole.TEACHER:
            # Fail closed, not open, if the class is unexpectedly missing —
            # ON DELETE RESTRICT makes this state impossible today, but the
            # check shouldn't silently no-op if that guarantee ever changes
            # (security-auditor finding, docs/adr/0019).
            cls = await self._class_repository.get(assessment.class_id)
            if cls is None:
                raise NotYourClassError()
            await self._check_owns_class(current_user, cls)
        return assessment

    async def list(
        self, current_user: User, *, limit: int, offset: int, class_id: UUID | None = None
    ) -> tuple[list[Assessment], int]:
        if current_user.role == UserRole.TEACHER:
            my_teacher_id = await self._get_my_teacher_id(current_user)
            if my_teacher_id is None:
                return [], 0
            owned = await self._class_repository.list_by_teacher_id(my_teacher_id)
            owned_ids = {c.id for c in owned}
            if class_id is not None:
                if class_id not in owned_ids:
                    raise NotYourClassError()
                return await self._repository.list(limit=limit, offset=offset, class_id=class_id)
            return await self._repository.list(
                limit=limit, offset=offset, class_ids=list(owned_ids)
            )
        return await self._repository.list(limit=limit, offset=offset, class_id=class_id)

    async def update(
        self, current_user: User, assessment_id: UUID, data: AssessmentUpdate
    ) -> Assessment:
        assessment = await self._repository.get(assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        current_class = await self._class_repository.get(assessment.class_id)
        if current_class is None:
            raise NotYourClassError()
        await self._check_owns_class(current_user, current_class)

        updates = data.model_dump(exclude_unset=True)
        if "class_id" in updates:
            new_class = await self._class_repository.get(updates["class_id"])
            if new_class is None:
                raise ClassNotFoundError()
            await self._check_owns_class(current_user, new_class)

        for field, value in updates.items():
            setattr(assessment, field, value)
        return await self._repository.add(assessment)

    async def delete(self, current_user: User, assessment_id: UUID) -> None:
        assessment = await self._repository.get(assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        cls = await self._class_repository.get(assessment.class_id)
        if cls is None:
            raise NotYourClassError()
        await self._check_owns_class(current_user, cls)

        await self._repository.remove(assessment)


class GradeService:
    """Depends on AssessmentRepository (own domain), StudentRepository
    (students), EnrollmentRepository (enrollments), ClassRepository and
    TeacherRepository (for the teacher-ownership check) — the same
    one-way fan-in shape ClassService/EnrollmentService already
    established (docs/adr/0016, 0017). See docs/adr/0018 for the STUDENT
    self-view scoping reasoning (404, not 403, for a grade that isn't
    theirs) and docs/adr/0019 for the parallel TEACHER class-ownership
    scoping (403, not 404 — Class/Assessment existence isn't hidden from
    an authenticated user the way another student's grade is)."""

    def __init__(
        self,
        repository: GradeRepository,
        assessment_repository: AssessmentRepository,
        student_repository: StudentRepository,
        enrollment_repository: EnrollmentRepository,
        class_repository: ClassRepository,
        teacher_repository: TeacherRepository,
    ) -> None:
        self._repository = repository
        self._assessment_repository = assessment_repository
        self._student_repository = student_repository
        self._enrollment_repository = enrollment_repository
        self._class_repository = class_repository
        self._teacher_repository = teacher_repository

    async def _get_my_student_id(self, current_user: User) -> UUID | None:
        my_student = await self._student_repository.get_by_user_id(current_user.id)
        return my_student.id if my_student is not None else None

    async def _get_my_teacher_id(self, current_user: User) -> UUID | None:
        my_teacher = await self._teacher_repository.get_by_user_id(current_user.id)
        return my_teacher.id if my_teacher is not None else None

    async def _check_owns_assessments_class(self, current_user: User, assessment: Assessment) -> None:
        if current_user.role != UserRole.TEACHER:
            return
        my_teacher_id = await self._get_my_teacher_id(current_user)
        cls = await self._class_repository.get(assessment.class_id)
        if my_teacher_id is None or cls is None or cls.teacher_id != my_teacher_id:
            raise NotYourClassError()

    async def create(self, current_user: User, data: GradeCreate) -> Grade:
        assessment = await self._assessment_repository.get(data.assessment_id)
        if assessment is None:
            raise AssessmentNotFoundError()

        await self._check_owns_assessments_class(current_user, assessment)

        if await self._student_repository.get(data.student_id) is None:
            raise StudentNotFoundError()
        if data.score > assessment.max_score:
            raise ScoreExceedsMaxScoreError()

        enrollment = await self._enrollment_repository.get_by_student_and_class(
            data.student_id, assessment.class_id
        )
        if enrollment is None or enrollment.status != EnrollmentStatus.ACTIVE:
            raise StudentNotEnrolledError()

        if (
            await self._repository.get_by_assessment_and_student(
                data.assessment_id, data.student_id
            )
            is not None
        ):
            raise GradeAlreadyExistsError()

        grade = Grade(
            assessment_id=data.assessment_id, student_id=data.student_id, score=data.score
        )
        try:
            return await self._repository.add(grade)
        except IntegrityError as exc:
            raise GradeAlreadyExistsError() from exc

    async def get(self, current_user: User, grade_id: UUID) -> Grade:
        # my_student_id is resolved before checking whether the grade
        # exists, and both failure branches below do the same amount of
        # work — a nonexistent grade and someone else's grade must look
        # identical from the outside, not just in the response body but in
        # how long the request takes to answer (security-auditor finding,
        # docs/adr/0018).
        my_student_id: UUID | None = None
        if current_user.role == UserRole.STUDENT:
            my_student_id = await self._get_my_student_id(current_user)

        grade = await self._repository.get(grade_id)

        if current_user.role == UserRole.STUDENT:
            if grade is None or my_student_id is None or grade.student_id != my_student_id:
                raise GradeNotFoundError()
            return grade

        if grade is None:
            raise GradeNotFoundError()

        if current_user.role == UserRole.TEACHER:
            # Fail closed if the assessment is unexpectedly missing — same
            # reasoning as AssessmentService's fail-closed fix above
            # (security-auditor finding, docs/adr/0019).
            assessment = await self._assessment_repository.get(grade.assessment_id)
            if assessment is None:
                raise NotYourClassError()
            await self._check_owns_assessments_class(current_user, assessment)

        return grade

    async def list(
        self,
        current_user: User,
        *,
        limit: int,
        offset: int,
        class_id: UUID | None = None,
        student_id: UUID | None = None,
        assessment_id: UUID | None = None,
    ) -> tuple[list[Grade], int]:
        if current_user.role == UserRole.STUDENT:
            my_student_id = await self._get_my_student_id(current_user)
            if my_student_id is None:
                return [], 0
            return await self._repository.list(
                limit=limit,
                offset=offset,
                class_id=class_id,
                student_id=my_student_id,
                assessment_id=assessment_id,
            )

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
                    limit=limit,
                    offset=offset,
                    class_id=class_id,
                    student_id=student_id,
                    assessment_id=assessment_id,
                )
            return await self._repository.list(
                limit=limit,
                offset=offset,
                class_ids=list(owned_ids),
                student_id=student_id,
                assessment_id=assessment_id,
            )

        return await self._repository.list(
            limit=limit,
            offset=offset,
            class_id=class_id,
            student_id=student_id,
            assessment_id=assessment_id,
        )

    async def update(self, current_user: User, grade_id: UUID, data: GradeUpdate) -> Grade:
        grade = await self._repository.get(grade_id)
        if grade is None:
            raise GradeNotFoundError()

        # Fail closed if the assessment is unexpectedly missing — same
        # reasoning as the other fail-closed fixes in this file
        # (security-auditor finding, docs/adr/0019). This also used to
        # silently skip the max_score re-validation in the same branch,
        # not just the ownership check — both matter, neither should be
        # reachable-but-skipped.
        assessment = await self._assessment_repository.get(grade.assessment_id)
        if assessment is None:
            raise NotYourClassError()
        await self._check_owns_assessments_class(current_user, assessment)
        if data.score > assessment.max_score:
            raise ScoreExceedsMaxScoreError()

        grade.score = data.score
        return await self._repository.add(grade)
