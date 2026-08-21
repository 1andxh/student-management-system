from uuid import UUID

from fastapi import APIRouter, Depends, File, Response, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.students.models import Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import (
    StudentCreate,
    StudentCredentialsRead,
    StudentRead,
    StudentUpdate,
)
from sms.domains.students.service import StudentService
from sms.domains.users.models import User, UserRole
from sms.domains.users.repository import UserRepository

router = APIRouter(prefix="/students", tags=["students"])

# Any authenticated user can read; only admins/teachers can create, change,
# or remove student records.
_can_manage = require_role(UserRole.ADMIN, UserRole.TEACHER)
# Credential issuance and file uploads are stricter — same tier as Users'
# own credential-adjacent actions, not the plain academic-record tier above.
_admin_only = require_role(UserRole.ADMIN)


def get_student_service(session: AsyncSession = Depends(get_db)) -> StudentService:
    return StudentService(StudentRepository(session), UserRepository(session))


@router.post(
    "",
    response_model=StudentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_can_manage)],
)
async def create_student(
    data: StudentCreate, service: StudentService = Depends(get_student_service)
) -> Student:
    return await service.create(data)


@router.get("", response_model=list[StudentRead], dependencies=[Depends(get_current_user)])
async def list_students(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: StudentService = Depends(get_student_service),
) -> list[Student]:
    items, total = await service.list(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


# Literal paths below (/me) are registered before /{student_id} deliberately
# — FastAPI matches routes in registration order, and a route declared
# after /{student_id} would have "me" fail UUID parsing on that route
# instead of reaching this one (same rule already documented in
# domains/teachers/router.py).


@router.get("/me", response_model=StudentRead)
async def get_my_student(
    current_user: User = Depends(get_current_user),
    service: StudentService = Depends(get_student_service),
) -> Student:
    return await service.get_my_student(current_user.id)


@router.post(
    "/{student_id}/credentials",
    response_model=StudentCredentialsRead,
    dependencies=[Depends(_admin_only)],
)
async def generate_student_credentials(
    student_id: UUID, service: StudentService = Depends(get_student_service)
) -> StudentCredentialsRead:
    return await service.generate_pin(student_id)


@router.post(
    "/{student_id}/profile-picture",
    response_model=StudentRead,
    dependencies=[Depends(_admin_only)],
)
async def upload_student_profile_picture(
    student_id: UUID,
    file: UploadFile = File(...),
    service: StudentService = Depends(get_student_service),
) -> Student:
    return await service.upload_profile_picture(student_id, file)


@router.get(
    "/{student_id}", response_model=StudentRead, dependencies=[Depends(get_current_user)]
)
async def get_student(
    student_id: UUID, service: StudentService = Depends(get_student_service)
) -> Student:
    return await service.get(student_id)


@router.patch("/{student_id}", response_model=StudentRead, dependencies=[Depends(_can_manage)])
async def update_student(
    student_id: UUID,
    data: StudentUpdate,
    service: StudentService = Depends(get_student_service),
) -> Student:
    return await service.update(student_id, data)


@router.delete(
    "/{student_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_can_manage)]
)
async def delete_student(
    student_id: UUID, service: StudentService = Depends(get_student_service)
) -> None:
    await service.delete(student_id)
