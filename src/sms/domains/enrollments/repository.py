# list_by_class_id (added below) would otherwise shadow the builtin `list`
# used in this same class's own `list()` method's `-> list[Enrollment]`
# annotation if it were evaluated eagerly — the exact bug ADR 0018/0019 hit
# twice already. Lazy string annotations sidestep it regardless of method
# order.
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus


class EnrollmentRepository(AbstractRepository[Enrollment]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Enrollment) -> Enrollment:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Enrollment | None:
        return await self._session.get(Enrollment, entity_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        student_id: UUID | None = None,
        class_id: UUID | None = None,
        class_ids: list[UUID] | None = None,
    ) -> tuple[list[Enrollment], int]:
        query = select(Enrollment).order_by(Enrollment.enrolled_at.desc())
        if student_id is not None:
            query = query.where(Enrollment.student_id == student_id)
        if class_id is not None:
            query = query.where(Enrollment.class_id == class_id)
        elif class_ids is not None:
            query = query.where(Enrollment.class_id.in_(class_ids))
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Enrollment) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_student_and_class(
        self, student_id: UUID, class_id: UUID
    ) -> Enrollment | None:
        result = await self._session.execute(
            select(Enrollment).where(
                Enrollment.student_id == student_id,
                Enrollment.class_id == class_id,
            )
        )
        return result.scalar_one_or_none()

    async def count_active_by_class(self, class_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(
                Enrollment.class_id == class_id,
                Enrollment.status == EnrollmentStatus.ACTIVE,
            )
        )
        return result.scalar_one()

    async def list_by_class_id(
        self, class_id: UUID, *, status: EnrollmentStatus | None = None
    ) -> list[Enrollment]:
        query = select(Enrollment).where(Enrollment.class_id == class_id)
        if status is not None:
            query = query.where(Enrollment.status == status)
        result = await self._session.execute(query)
        return list(result.scalars().all())
