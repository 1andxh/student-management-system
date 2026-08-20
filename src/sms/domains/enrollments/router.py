from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.classes.repository import ClassRepository
from sms.domains.enrollments.models import Enrollment
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.enrollments.schemas import EnrollmentCreate, EnrollmentRead
from sms.domains.enrollments.service import EnrollmentService
from sms.domains.students.repository import StudentRepository
from sms.domains.users.models import UserRole

router = APIRouter(prefix="/enrollments", tags=["enrollments"])

# Day-to-day academic record-keeping — same tier as Students, which
# teachers already manage directly (unlike Classes/Teachers/Users' stricter
# admin-only tier for structural/HR/account data).
_can_manage = require_role(UserRole.ADMIN, UserRole.TEACHER)


def get_enrollment_service(session: AsyncSession = Depends(get_db)) -> EnrollmentService:
    return EnrollmentService(
        EnrollmentRepository(session), ClassRepository(session), StudentRepository(session)
    )


@router.post(
    "",
    response_model=EnrollmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_can_manage)],
)
async def enroll(
    data: EnrollmentCreate, service: EnrollmentService = Depends(get_enrollment_service)
) -> Enrollment:
    return await service.enroll(data)


@router.get("", response_model=list[EnrollmentRead], dependencies=[Depends(get_current_user)])
async def list_enrollments(
    response: Response,
    student_id: UUID | None = None,
    class_id: UUID | None = None,
    pagination: Pagination = Depends(pagination_params),
    service: EnrollmentService = Depends(get_enrollment_service),
) -> list[Enrollment]:
    items, total = await service.list(
        limit=pagination.limit, offset=pagination.offset, student_id=student_id, class_id=class_id
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@router.get(
    "/{enrollment_id}", response_model=EnrollmentRead, dependencies=[Depends(get_current_user)]
)
async def get_enrollment(
    enrollment_id: UUID, service: EnrollmentService = Depends(get_enrollment_service)
) -> Enrollment:
    return await service.get(enrollment_id)


@router.patch(
    "/{enrollment_id}/drop",
    response_model=EnrollmentRead,
    dependencies=[Depends(_can_manage)],
)
async def drop_enrollment(
    enrollment_id: UUID, service: EnrollmentService = Depends(get_enrollment_service)
) -> Enrollment:
    return await service.drop(enrollment_id)
