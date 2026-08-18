from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.db.session import get_db
from sms.domains.students.models import Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import StudentCreate, StudentRead, StudentUpdate
from sms.domains.students.service import StudentService

router = APIRouter(prefix="/students", tags=["students"])


def get_student_service(session: AsyncSession = Depends(get_db)) -> StudentService:
    return StudentService(StudentRepository(session))


@router.post("", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    data: StudentCreate, service: StudentService = Depends(get_student_service)
) -> Student:
    return await service.create(data)


@router.get("", response_model=list[StudentRead])
async def list_students(service: StudentService = Depends(get_student_service)) -> list[Student]:
    return await service.list()


@router.get("/{student_id}", response_model=StudentRead)
async def get_student(
    student_id: UUID, service: StudentService = Depends(get_student_service)
) -> Student:
    return await service.get(student_id)


@router.patch("/{student_id}", response_model=StudentRead)
async def update_student(
    student_id: UUID,
    data: StudentUpdate,
    service: StudentService = Depends(get_student_service),
) -> Student:
    return await service.update(student_id, data)


@router.delete("/{student_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_student(
    student_id: UUID, service: StudentService = Depends(get_student_service)
) -> None:
    await service.delete(student_id)
