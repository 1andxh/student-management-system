from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.academic_years.repository import TermRepository
from sms.domains.assessments.repository import AssessmentRepository, GradeRepository
from sms.domains.assessments.schemas import ClassGradebookRead
from sms.domains.assessments.service import GradeService
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.classes.models import Class, Subject
from sms.domains.classes.repository import ClassRepository, SubjectRepository
from sms.domains.classes.schemas import (
    ClassCreate,
    ClassRead,
    ClassUpdate,
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
)
from sms.domains.classes.service import ClassService, SubjectService
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.users.models import User, UserRole

subjects_router = APIRouter(prefix="/subjects", tags=["subjects"])
classes_router = APIRouter(prefix="/classes", tags=["classes"])

_admin_only = require_role(UserRole.ADMIN)
_admin_or_teacher = require_role(UserRole.ADMIN, UserRole.TEACHER)


def get_subject_service(session: AsyncSession = Depends(get_db)) -> SubjectService:
    return SubjectService(SubjectRepository(session))


def get_class_service(session: AsyncSession = Depends(get_db)) -> ClassService:
    return ClassService(
        ClassRepository(session),
        SubjectRepository(session),
        TermRepository(session),
        TeacherRepository(session),
    )


def get_grade_service(session: AsyncSession = Depends(get_db)) -> GradeService:
    # Duplicated wiring rather than imported from assessments/router.py —
    # matches this codebase's existing convention of every router file
    # building its own get_X_service providers instead of cross-importing
    # them.
    return GradeService(
        GradeRepository(session),
        AssessmentRepository(session),
        StudentRepository(session),
        EnrollmentRepository(session),
        ClassRepository(session),
        TeacherRepository(session),
    )


@subjects_router.post(
    "",
    response_model=SubjectRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_subject(
    data: SubjectCreate, service: SubjectService = Depends(get_subject_service)
) -> Subject:
    return await service.create(data)


@subjects_router.get(
    "", response_model=list[SubjectRead], dependencies=[Depends(get_current_user)]
)
async def list_subjects(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: SubjectService = Depends(get_subject_service),
) -> list[Subject]:
    items, total = await service.list(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@subjects_router.get(
    "/{subject_id}", response_model=SubjectRead, dependencies=[Depends(get_current_user)]
)
async def get_subject(
    subject_id: UUID, service: SubjectService = Depends(get_subject_service)
) -> Subject:
    return await service.get(subject_id)


@subjects_router.patch(
    "/{subject_id}", response_model=SubjectRead, dependencies=[Depends(_admin_only)]
)
async def update_subject(
    subject_id: UUID,
    data: SubjectUpdate,
    service: SubjectService = Depends(get_subject_service),
) -> Subject:
    return await service.update(subject_id, data)


@subjects_router.delete(
    "/{subject_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_subject(
    subject_id: UUID, service: SubjectService = Depends(get_subject_service)
) -> None:
    await service.delete(subject_id)


@classes_router.post(
    "",
    response_model=ClassRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_class(
    data: ClassCreate, service: ClassService = Depends(get_class_service)
) -> Class:
    return await service.create(data)


@classes_router.get("", response_model=list[ClassRead], dependencies=[Depends(get_current_user)])
async def list_classes(
    response: Response,
    term_id: UUID | None = None,
    subject_id: UUID | None = None,
    teacher_id: UUID | None = None,
    section_id: UUID | None = None,
    pagination: Pagination = Depends(pagination_params),
    service: ClassService = Depends(get_class_service),
) -> list[Class]:
    items, total = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        term_id=term_id,
        subject_id=subject_id,
        teacher_id=teacher_id,
        section_id=section_id,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@classes_router.get(
    "/{class_id}", response_model=ClassRead, dependencies=[Depends(get_current_user)]
)
async def get_class(
    class_id: UUID, service: ClassService = Depends(get_class_service)
) -> Class:
    return await service.get(class_id)


@classes_router.patch(
    "/{class_id}", response_model=ClassRead, dependencies=[Depends(_admin_only)]
)
async def update_class(
    class_id: UUID, data: ClassUpdate, service: ClassService = Depends(get_class_service)
) -> Class:
    return await service.update(class_id, data)


@classes_router.delete(
    "/{class_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_class(
    class_id: UUID, service: ClassService = Depends(get_class_service)
) -> None:
    await service.delete(class_id)


@classes_router.get(
    "/{class_id}/gradebook",
    response_model=ClassGradebookRead,
    dependencies=[Depends(_admin_or_teacher)],
)
async def get_class_gradebook(
    class_id: UUID,
    current_user: User = Depends(get_current_user),
    service: GradeService = Depends(get_grade_service),
) -> ClassGradebookRead:
    return await service.get_class_gradebook(current_user, class_id)
