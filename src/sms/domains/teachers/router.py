from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.teachers.models import Teacher, TeacherChangeRequest
from sms.domains.teachers.repository import TeacherChangeRequestRepository, TeacherRepository
from sms.domains.teachers.schemas import (
    TeacherChangeRequestCreate,
    TeacherChangeRequestRead,
    TeacherCreate,
    TeacherRead,
    TeacherUpdate,
)
from sms.domains.teachers.service import TeacherChangeRequestService, TeacherService
from sms.domains.users.models import User, UserRole

router = APIRouter(prefix="/teachers", tags=["teachers"])

# Staff/HR data, not academic content — stricter than Students' admin+teacher
# tier, matching Users' precedent (see docs/adr/0010). A teacher can't edit
# their own or another teacher's HR record through this route.
_admin_only = require_role(UserRole.ADMIN)


def get_teacher_service(session: AsyncSession = Depends(get_db)) -> TeacherService:
    return TeacherService(TeacherRepository(session))


def get_change_request_service(
    session: AsyncSession = Depends(get_db),
) -> TeacherChangeRequestService:
    return TeacherChangeRequestService(
        TeacherChangeRequestRepository(session),
        TeacherRepository(session),
        TeacherService(TeacherRepository(session)),
    )


@router.post(
    "",
    response_model=TeacherRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_teacher(
    data: TeacherCreate, service: TeacherService = Depends(get_teacher_service)
) -> Teacher:
    return await service.create(data)


@router.get("", response_model=list[TeacherRead], dependencies=[Depends(get_current_user)])
async def list_teachers(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: TeacherService = Depends(get_teacher_service),
) -> list[Teacher]:
    items, total = await service.list(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


# Literal paths below (/me, /change-requests) are registered before
# /{teacher_id} deliberately — FastAPI matches routes in registration
# order, and a route declared after /{teacher_id} would have "me" or
# "change-requests" fail UUID parsing on that route instead of reaching
# these.


@router.get("/me", response_model=TeacherRead)
async def get_my_teacher(
    current_user: User = Depends(get_current_user),
    service: TeacherChangeRequestService = Depends(get_change_request_service),
) -> Teacher:
    return await service.get_my_teacher(current_user.id)


@router.post(
    "/me/change-requests",
    response_model=TeacherChangeRequestRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_my_change_request(
    data: TeacherChangeRequestCreate,
    current_user: User = Depends(get_current_user),
    service: TeacherChangeRequestService = Depends(get_change_request_service),
) -> TeacherChangeRequest:
    return await service.create(current_user.id, data)


@router.get(
    "/change-requests",
    response_model=list[TeacherChangeRequestRead],
    dependencies=[Depends(_admin_only)],
)
async def list_change_requests(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: TeacherChangeRequestService = Depends(get_change_request_service),
) -> list[TeacherChangeRequest]:
    items, total = await service.list_all(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@router.patch(
    "/change-requests/{request_id}/approve",
    response_model=TeacherChangeRequestRead,
    dependencies=[Depends(_admin_only)],
)
async def approve_change_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TeacherChangeRequestService = Depends(get_change_request_service),
) -> TeacherChangeRequest:
    return await service.approve(request_id, current_user.id)


@router.patch(
    "/change-requests/{request_id}/reject",
    response_model=TeacherChangeRequestRead,
    dependencies=[Depends(_admin_only)],
)
async def reject_change_request(
    request_id: UUID,
    current_user: User = Depends(get_current_user),
    service: TeacherChangeRequestService = Depends(get_change_request_service),
) -> TeacherChangeRequest:
    return await service.reject(request_id, current_user.id)


@router.get(
    "/{teacher_id}", response_model=TeacherRead, dependencies=[Depends(get_current_user)]
)
async def get_teacher(
    teacher_id: UUID, service: TeacherService = Depends(get_teacher_service)
) -> Teacher:
    return await service.get(teacher_id)


@router.patch("/{teacher_id}", response_model=TeacherRead, dependencies=[Depends(_admin_only)])
async def update_teacher(
    teacher_id: UUID,
    data: TeacherUpdate,
    service: TeacherService = Depends(get_teacher_service),
) -> Teacher:
    return await service.update(teacher_id, data)


@router.delete(
    "/{teacher_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_teacher(
    teacher_id: UUID, service: TeacherService = Depends(get_teacher_service)
) -> None:
    await service.delete(teacher_id)


@router.post(
    "/{teacher_id}/profile-picture",
    response_model=TeacherRead,
    dependencies=[Depends(_admin_only)],
)
async def upload_teacher_profile_picture(
    teacher_id: UUID,
    file: UploadFile = File(...),
    service: TeacherService = Depends(get_teacher_service),
) -> Teacher:
    return await service.upload_profile_picture(teacher_id, file)
