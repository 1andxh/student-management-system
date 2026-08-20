from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.users.models import UserRole
from sms.domains.students.models import Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import StudentCreate, StudentRead, StudentUpdate
from sms.domains.students.service import StudentService

router = APIRouter(prefix="/students", tags=["students"])

# Any authenticated user can read; only admins/teachers can create, change,
# or remove student records.
_can_manage = require_role(UserRole.ADMIN, UserRole.TEACHER)


def get_student_service(session: AsyncSession = Depends(get_db)) -> StudentService:
    return StudentService(StudentRepository(session))


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
