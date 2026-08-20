from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.academic_years.models import AcademicYear, Term


class AcademicYearRepository(AbstractRepository[AcademicYear]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: AcademicYear) -> AcademicYear:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> AcademicYear | None:
        return await self._session.get(AcademicYear, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[AcademicYear], int]:
        query = select(AcademicYear).order_by(AcademicYear.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: AcademicYear) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_name(self, name: str) -> AcademicYear | None:
        result = await self._session.execute(select(AcademicYear).where(AcademicYear.name == name))
        return result.scalar_one_or_none()


class TermRepository(AbstractRepository[Term]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Term) -> Term:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Term | None:
        return await self._session.get(Term, entity_id)

    async def list(
        self, *, limit: int, offset: int, academic_year_id: UUID | None = None
    ) -> tuple[list[Term], int]:
        query = select(Term).order_by(Term.created_at.desc())
        if academic_year_id is not None:
            query = query.where(Term.academic_year_id == academic_year_id)
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Term) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_year_and_name(self, academic_year_id: UUID, name: str) -> Term | None:
        result = await self._session.execute(
            select(Term).where(
                Term.academic_year_id == academic_year_id,
                Term.name == name,
            )
        )
        return result.scalar_one_or_none()
