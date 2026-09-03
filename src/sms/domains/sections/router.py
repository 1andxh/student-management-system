from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.academic_years.repository import AcademicYearRepository, TermRepository
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.classes.repository import ClassRepository
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.sections.models import GradeLevel, Section, SectionAssignment
from sms.domains.sections.repository import (
    GradeLevelRepository,
    SectionAssignmentRepository,
    SectionRepository,
)
from sms.domains.sections.schemas import (
    GradeLevelCreate,
    GradeLevelRead,
    GradeLevelUpdate,
    SectionAssignmentRead,
    SectionCreate,
    SectionRead,
    SectionUpdate,
)
from sms.domains.sections.service import (
    GradeLevelService,
    SectionAssignmentService,
    SectionService,
)
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.users.models import UserRole

grade_levels_router = APIRouter(prefix="/grade-levels", tags=["grade-levels"])
sections_router = APIRouter(prefix="/sections", tags=["sections"])

# Structural academic data — same admin-only mutation tier as
# Subjects/Classes/Terms (docs/adr/0016), not the admin+teacher tier used
# for day-to-day records like Students and Enrollments.
_admin_only = require_role(UserRole.ADMIN)
# Reserved for the section roster specifically — see the route below for
# why that one read is not open to every authenticated user.
_admin_or_teacher = require_role(UserRole.ADMIN, UserRole.TEACHER)


def get_grade_level_service(session: AsyncSession = Depends(get_db)) -> GradeLevelService:
    return GradeLevelService(GradeLevelRepository(session))


def get_section_service(session: AsyncSession = Depends(get_db)) -> SectionService:
    return SectionService(
        SectionRepository(session),
        GradeLevelRepository(session),
        AcademicYearRepository(session),
        TeacherRepository(session),
        ClassRepository(session),
        EnrollmentRepository(session),
        SectionAssignmentRepository(session),
        TermRepository(session),
    )


def get_section_assignment_service(
    session: AsyncSession = Depends(get_db),
) -> SectionAssignmentService:
    return SectionAssignmentService(
        SectionAssignmentRepository(session),
        SectionRepository(session),
        StudentRepository(session),
        ClassRepository(session),
        EnrollmentRepository(session),
    )


@grade_levels_router.post(
    "",
    response_model=GradeLevelRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_grade_level(
    data: GradeLevelCreate, service: GradeLevelService = Depends(get_grade_level_service)
) -> GradeLevel:
    return await service.create(data)


@grade_levels_router.get(
    "", response_model=list[GradeLevelRead], dependencies=[Depends(get_current_user)]
)
async def list_grade_levels(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: GradeLevelService = Depends(get_grade_level_service),
) -> list[GradeLevel]:
    items, total = await service.list(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@grade_levels_router.get(
    "/{grade_level_id}", response_model=GradeLevelRead, dependencies=[Depends(get_current_user)]
)
async def get_grade_level(
    grade_level_id: UUID, service: GradeLevelService = Depends(get_grade_level_service)
) -> GradeLevel:
    return await service.get(grade_level_id)


@grade_levels_router.patch(
    "/{grade_level_id}", response_model=GradeLevelRead, dependencies=[Depends(_admin_only)]
)
async def update_grade_level(
    grade_level_id: UUID,
    data: GradeLevelUpdate,
    service: GradeLevelService = Depends(get_grade_level_service),
) -> GradeLevel:
    return await service.update(grade_level_id, data)


@grade_levels_router.delete(
    "/{grade_level_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_only)],
)
async def delete_grade_level(
    grade_level_id: UUID, service: GradeLevelService = Depends(get_grade_level_service)
) -> None:
    await service.delete(grade_level_id)


@sections_router.post(
    "",
    response_model=SectionRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_section(
    data: SectionCreate, service: SectionService = Depends(get_section_service)
) -> Section:
    return await service.create(data)


@sections_router.get(
    "", response_model=list[SectionRead], dependencies=[Depends(get_current_user)]
)
async def list_sections(
    response: Response,
    grade_level_id: UUID | None = None,
    academic_year_id: UUID | None = None,
    pagination: Pagination = Depends(pagination_params),
    service: SectionService = Depends(get_section_service),
) -> list[Section]:
    items, total = await service.list(
        limit=pagination.limit,
        offset=pagination.offset,
        grade_level_id=grade_level_id,
        academic_year_id=academic_year_id,
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@sections_router.get(
    "/{section_id}", response_model=SectionRead, dependencies=[Depends(get_current_user)]
)
async def get_section(
    section_id: UUID, service: SectionService = Depends(get_section_service)
) -> Section:
    return await service.get(section_id)


@sections_router.patch(
    "/{section_id}", response_model=SectionRead, dependencies=[Depends(_admin_only)]
)
async def update_section(
    section_id: UUID,
    data: SectionUpdate,
    service: SectionService = Depends(get_section_service),
) -> Section:
    return await service.update(section_id, data)


@sections_router.delete(
    "/{section_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_section(
    section_id: UUID, service: SectionService = Depends(get_section_service)
) -> None:
    await service.delete(section_id)


@sections_router.get(
    "/{section_id}/students",
    response_model=list[SectionAssignmentRead],
    # ADMIN+TEACHER, deliberately not every authenticated user — same tier
    # and same reasoning as GET /classes/{id}/gradebook (docs/adr/0022).
    # Left open, this reconstructs by join exactly what docs/adr/0023 closed:
    # the roster gives a STUDENT every classmate's student_id, ClassRead
    # exposes section_id, and section assignment auto-enrols the whole roster
    # into every attached class — so roster + /classes rebuilds the
    # student->classes mapping that EnrollmentService.list refuses to serve
    # a STUDENT directly (security-auditor finding).
    dependencies=[Depends(_admin_or_teacher)],
)
async def list_section_roster(
    section_id: UUID,
    service: SectionAssignmentService = Depends(get_section_assignment_service),
) -> list[SectionAssignment]:
    return await service.list_roster(section_id)


@sections_router.post(
    "/{section_id}/students/{student_id}",
    response_model=SectionAssignmentRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def assign_student_to_section(
    section_id: UUID,
    student_id: UUID,
    service: SectionAssignmentService = Depends(get_section_assignment_service),
) -> SectionAssignment:
    return await service.assign(student_id, section_id)


@sections_router.delete(
    "/{section_id}/students/{student_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_only)],
)
async def unassign_student_from_section(
    section_id: UUID,
    student_id: UUID,
    service: SectionAssignmentService = Depends(get_section_assignment_service),
) -> None:
    await service.unassign(student_id, section_id)


@sections_router.post(
    "/{section_id}/classes/{class_id}",
    response_model=SectionRead,
    dependencies=[Depends(_admin_only)],
)
async def attach_class_to_section(
    section_id: UUID,
    class_id: UUID,
    service: SectionService = Depends(get_section_service),
) -> Section:
    return await service.attach_class(section_id, class_id)


@sections_router.delete(
    "/{section_id}/classes/{class_id}",
    response_model=SectionRead,
    dependencies=[Depends(_admin_only)],
)
async def detach_class_from_section(
    section_id: UUID,
    class_id: UUID,
    service: SectionService = Depends(get_section_service),
) -> Section:
    return await service.detach_class(section_id, class_id)
