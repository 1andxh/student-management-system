from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.classes.repository import ClassRepository
from sms.domains.sections.repository import SectionAssignmentRepository
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.timetable.models import DayOfWeek, Period, ScheduleSlot
from sms.domains.timetable.repository import PeriodRepository, ScheduleSlotRepository
from sms.domains.timetable.schemas import (
    PeriodCreate,
    PeriodRead,
    PeriodUpdate,
    ScheduleSlotCreate,
    ScheduleSlotRead,
)
from sms.domains.timetable.service import PeriodService, ScheduleSlotService
from sms.domains.users.models import User, UserRole

periods_router = APIRouter(prefix="/periods", tags=["periods"])
timetable_router = APIRouter(prefix="/timetable", tags=["timetable"])

# Structural academic data — same admin-only mutation tier as
# Classes/Sections/Terms (docs/adr/0016).
_admin_only = require_role(UserRole.ADMIN)


def get_period_service(session: AsyncSession = Depends(get_db)) -> PeriodService:
    return PeriodService(PeriodRepository(session))


def get_slot_service(session: AsyncSession = Depends(get_db)) -> ScheduleSlotService:
    return ScheduleSlotService(
        ScheduleSlotRepository(session),
        PeriodRepository(session),
        ClassRepository(session),
        TeacherRepository(session),
        StudentRepository(session),
        SectionAssignmentRepository(session),
    )


@periods_router.post(
    "",
    response_model=PeriodRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_period(
    data: PeriodCreate, service: PeriodService = Depends(get_period_service)
) -> Period:
    return await service.create(data)


@periods_router.get(
    "", response_model=list[PeriodRead], dependencies=[Depends(get_current_user)]
)
async def list_periods(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: PeriodService = Depends(get_period_service),
) -> list[Period]:
    items, total = await service.list(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@periods_router.get(
    "/{period_id}", response_model=PeriodRead, dependencies=[Depends(get_current_user)]
)
async def get_period(
    period_id: UUID, service: PeriodService = Depends(get_period_service)
) -> Period:
    return await service.get(period_id)


@periods_router.patch(
    "/{period_id}", response_model=PeriodRead, dependencies=[Depends(_admin_only)]
)
async def update_period(
    period_id: UUID,
    data: PeriodUpdate,
    service: PeriodService = Depends(get_period_service),
) -> Period:
    return await service.update(period_id, data)


@periods_router.delete(
    "/{period_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_period(
    period_id: UUID, service: PeriodService = Depends(get_period_service)
) -> None:
    await service.delete(period_id)


# Literal paths before any /{param} route on this router — same
# registration-order rule documented in domains/teachers/router.py.


@timetable_router.get("/me", response_model=list[ScheduleSlotRead])
async def get_my_timetable(
    current_user: User = Depends(get_current_user),
    service: ScheduleSlotService = Depends(get_slot_service),
) -> list[ScheduleSlot]:
    return await service.list_my_timetable(current_user)


@timetable_router.get(
    "", response_model=list[ScheduleSlotRead], dependencies=[Depends(get_current_user)]
)
async def list_timetable(
    class_id: UUID | None = None,
    teacher_id: UUID | None = None,
    section_id: UUID | None = None,
    day_of_week: DayOfWeek | None = None,
    service: ScheduleSlotService = Depends(get_slot_service),
) -> list[ScheduleSlot]:
    # No pagination: a timetable is bounded by the school week, so there is
    # nothing to page through — the one list endpoint here that deliberately
    # departs from docs/adr/0020's convention.
    return await service.list(
        class_id=class_id,
        teacher_id=teacher_id,
        section_id=section_id,
        day_of_week=day_of_week,
    )


@timetable_router.post(
    "/slots",
    response_model=ScheduleSlotRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_slot(
    data: ScheduleSlotCreate, service: ScheduleSlotService = Depends(get_slot_service)
) -> ScheduleSlot:
    return await service.create(data)


@timetable_router.delete(
    "/slots/{slot_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_admin_only)],
)
async def delete_slot(
    slot_id: UUID, service: ScheduleSlotService = Depends(get_slot_service)
) -> None:
    await service.delete(slot_id)
