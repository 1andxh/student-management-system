# list_by_* methods below would otherwise shadow the builtin `list` used in
# these classes' own list() annotations if evaluated eagerly — the bug ADR
# 0018/0019 already hit three times. Lazy string annotations sidestep it.
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.timetable.models import DayOfWeek, Period, ScheduleSlot


class PeriodRepository(AbstractRepository[Period]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Period, *, commit: bool = True) -> Period:
        self._session.add(entity)
        try:
            if commit:
                await self._session.commit()
            else:
                await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def get(self, entity_id: UUID) -> Period | None:
        return await self._session.get(Period, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[Period], int]:
        # Chronological, not newest-first — a bell schedule's natural order
        # is the order the bells ring in.
        query = select(Period).order_by(Period.start_time)
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Period) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_name(self, name: str) -> Period | None:
        result = await self._session.execute(select(Period).where(Period.name == name))
        return result.scalar_one_or_none()

    async def get_for_update(self, entity_id: UUID) -> Period | None:
        # The conflict checks in ScheduleSlotService.create read every other
        # slot in this (day, period) and then insert. Serialising those
        # callers on the period row stops two concurrent inserts from both
        # seeing a free slot. populate_existing for the same
        # identity-map-staleness reason as SectionRepository.get_for_update
        # (docs/adr/0024).
        result = await self._session.execute(
            select(Period)
            .where(Period.id == entity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()


class ScheduleSlotRepository(AbstractRepository[ScheduleSlot]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: ScheduleSlot, *, commit: bool = True) -> ScheduleSlot:
        self._session.add(entity)
        try:
            if commit:
                await self._session.commit()
            else:
                await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> ScheduleSlot | None:
        return await self._session.get(ScheduleSlot, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[ScheduleSlot], int]:
        query = select(ScheduleSlot).order_by(ScheduleSlot.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: ScheduleSlot) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_class_day_period(
        self, class_id: UUID, day_of_week: DayOfWeek, period_id: UUID
    ) -> ScheduleSlot | None:
        result = await self._session.execute(
            select(ScheduleSlot).where(
                ScheduleSlot.class_id == class_id,
                ScheduleSlot.day_of_week == day_of_week,
                ScheduleSlot.period_id == period_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_day_and_period(
        self, day_of_week: DayOfWeek, period_id: UUID
    ) -> list[ScheduleSlot]:
        """Every slot competing for this (day, period) — the candidate set
        the three conflict rules are evaluated against."""
        result = await self._session.execute(
            select(ScheduleSlot).where(
                ScheduleSlot.day_of_week == day_of_week,
                ScheduleSlot.period_id == period_id,
            )
        )
        return list(result.scalars().all())

    async def list_filtered(
        self,
        *,
        class_ids: list[UUID] | None = None,
        day_of_week: DayOfWeek | None = None,
    ) -> list[ScheduleSlot]:
        """Not paginated — a timetable is bounded by the school week, so
        there's nothing to page through. Deliberately takes class_ids rather
        than teacher/section filters: resolving those to a set of classes is
        the service's job, which keeps this repository from reaching into
        the classes domain."""
        query = select(ScheduleSlot)
        if class_ids is not None:
            if not class_ids:
                return []
            query = query.where(ScheduleSlot.class_id.in_(class_ids))
        if day_of_week is not None:
            query = query.where(ScheduleSlot.day_of_week == day_of_week)
        result = await self._session.execute(query)
        return list(result.scalars().all())
