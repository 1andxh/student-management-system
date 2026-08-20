from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.academic_years.repository import AcademicYearRepository, TermRepository
from sms.domains.academic_years.schemas import (
    AcademicYearCreate,
    AcademicYearRead,
    AcademicYearUpdate,
    TermCreate,
    TermRead,
    TermUpdate,
)
from sms.domains.academic_years.service import AcademicYearService, TermService
from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.users.models import UserRole

academic_years_router = APIRouter(prefix="/academic-years", tags=["academic-years"])
terms_router = APIRouter(prefix="/terms", tags=["terms"])

_admin_only = require_role(UserRole.ADMIN)


def get_academic_year_service(session: AsyncSession = Depends(get_db)) -> AcademicYearService:
    return AcademicYearService(AcademicYearRepository(session))


def get_term_service(session: AsyncSession = Depends(get_db)) -> TermService:
    return TermService(TermRepository(session), AcademicYearRepository(session))


@academic_years_router.post(
    "",
    response_model=AcademicYearRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_academic_year(
    data: AcademicYearCreate, service: AcademicYearService = Depends(get_academic_year_service)
) -> AcademicYear:
    return await service.create(data)


@academic_years_router.get(
    "", response_model=list[AcademicYearRead], dependencies=[Depends(get_current_user)]
)
async def list_academic_years(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: AcademicYearService = Depends(get_academic_year_service),
) -> list[AcademicYear]:
    items, total = await service.list(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items


@academic_years_router.get(
    "/{year_id}", response_model=AcademicYearRead, dependencies=[Depends(get_current_user)]
)
async def get_academic_year(
    year_id: UUID, service: AcademicYearService = Depends(get_academic_year_service)
) -> AcademicYear:
    return await service.get(year_id)


@academic_years_router.patch(
    "/{year_id}", response_model=AcademicYearRead, dependencies=[Depends(_admin_only)]
)
async def update_academic_year(
    year_id: UUID,
    data: AcademicYearUpdate,
    service: AcademicYearService = Depends(get_academic_year_service),
) -> AcademicYear:
    return await service.update(year_id, data)


@academic_years_router.delete(
    "/{year_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_academic_year(
    year_id: UUID, service: AcademicYearService = Depends(get_academic_year_service)
) -> None:
    await service.delete(year_id)


@terms_router.post(
    "",
    response_model=TermRead,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(_admin_only)],
)
async def create_term(
    data: TermCreate, service: TermService = Depends(get_term_service)
) -> Term:
    return await service.create(data)


@terms_router.get("", response_model=list[TermRead], dependencies=[Depends(get_current_user)])
async def list_terms(
    response: Response,
    academic_year_id: UUID | None = None,
    pagination: Pagination = Depends(pagination_params),
    service: TermService = Depends(get_term_service),
) -> list[Term]:
    items, total = await service.list(
        limit=pagination.limit, offset=pagination.offset, academic_year_id=academic_year_id
    )
    response.headers["X-Total-Count"] = str(total)
    return items


@terms_router.get(
    "/{term_id}", response_model=TermRead, dependencies=[Depends(get_current_user)]
)
async def get_term(
    term_id: UUID, service: TermService = Depends(get_term_service)
) -> Term:
    return await service.get(term_id)


@terms_router.patch("/{term_id}", response_model=TermRead, dependencies=[Depends(_admin_only)])
async def update_term(
    term_id: UUID, data: TermUpdate, service: TermService = Depends(get_term_service)
) -> Term:
    return await service.update(term_id, data)


@terms_router.delete(
    "/{term_id}", status_code=status.HTTP_204_NO_CONTENT, dependencies=[Depends(_admin_only)]
)
async def delete_term(
    term_id: UUID, service: TermService = Depends(get_term_service)
) -> None:
    await service.delete(term_id)
