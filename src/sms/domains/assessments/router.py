from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.assessments.models import Assessment, Grade
from sms.domains.assessments.repository import AssessmentRepository, GradeRepository
from sms.domains.assessments.schemas import (
    AssessmentCreate,
    AssessmentRead,
    AssessmentUpdate,
    GradeCreate,
    GradeRead,
    GradeUpdate,
)
from sms.domains.assessments.service import AssessmentService, GradeService
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.classes.repository import ClassRepository
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.users.models import User, UserRole

assessments_router = APIRouter(prefix="/assessments", tags=["assessments"])
grades_router = APIRouter(prefix="/grades", tags=["grades"])

_can_manage = require_role(UserRole.ADMIN, UserRole.TEACHER)


def get_assessment_service(session: AsyncSession = Depends(get_db)) -> AssessmentService:
    return AssessmentService(
        AssessmentRepository(session), ClassRepository(session), TeacherRepository(session)
    )


def get_grade_service(session: AsyncSession = Depends(get_db)) -> GradeService:
    return GradeService(
        GradeRepository(session),
        AssessmentRepository(session),
        StudentRepository(session),
        EnrollmentRepository(session),
        ClassRepository(session),
        TeacherRepository(session),
    )


@assessments_router.post(
    "",
    response_model=AssessmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_can_manage)],
)
async def create_assessment(
    data: AssessmentCreate,
    current_user: User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> Assessment:
    return await service.create(current_user, data)


@assessments_router.get("", response_model=list[AssessmentRead])
async def list_assessments(
    response: Response,
    class_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    pagination: Pagination = Depends(pagination_params),
    service: AssessmentService = Depends(get_assessment_service),
) -> list[Assessment]:
    items, total = await service.list(
        current_user, limit=pagination.limit, offset=pagination.offset, class_id=class_id
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@assessments_router.get("/{assessment_id}", response_model=AssessmentRead)
async def get_assessment(
    assessment_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> Assessment:
    return await service.get(current_user, assessment_id)


@assessments_router.patch(
    "/{assessment_id}", response_model=AssessmentRead, dependencies=[Depends(_can_manage)]
)
async def update_assessment(
    assessment_id: UUID,
    data: AssessmentUpdate,
    current_user: User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> Assessment:
    return await service.update(current_user, assessment_id, data)


@assessments_router.delete(
    "/{assessment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_can_manage)],
)
async def delete_assessment(
    assessment_id: UUID,
    current_user: User = Depends(get_current_user),
    service: AssessmentService = Depends(get_assessment_service),
) -> None:
    await service.delete(current_user, assessment_id)


@grades_router.post(
    "",
    response_model=GradeRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_can_manage)],
)
async def create_grade(
    data: GradeCreate,
    current_user: User = Depends(get_current_user),
    service: GradeService = Depends(get_grade_service),
) -> Grade:
    return await service.create(current_user, data)


@grades_router.get("", response_model=list[GradeRead])
async def list_grades(
    response: Response,
    class_id: UUID | None = None,
    student_id: UUID | None = None,
    assessment_id: UUID | None = None,
    current_user: User = Depends(get_current_user),
    pagination: Pagination = Depends(pagination_params),
    service: GradeService = Depends(get_grade_service),
) -> list[Grade]:
    items, total = await service.list(
        current_user,
        limit=pagination.limit,
        offset=pagination.offset,
        class_id=class_id,
        student_id=student_id,
        assessment_id=assessment_id,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@grades_router.get("/{grade_id}", response_model=GradeRead)
async def get_grade(
    grade_id: UUID,
    current_user: User = Depends(get_current_user),
    service: GradeService = Depends(get_grade_service),
) -> Grade:
    return await service.get(current_user, grade_id)


@grades_router.patch(
    "/{grade_id}", response_model=GradeRead, dependencies=[Depends(_can_manage)]
)
async def update_grade(
    grade_id: UUID,
    data: GradeUpdate,
    current_user: User = Depends(get_current_user),
    service: GradeService = Depends(get_grade_service),
) -> Grade:
    return await service.update(current_user, grade_id, data)
