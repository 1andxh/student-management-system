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
    ) -> tuple[list[Enrollment], int]:
        query = select(Enrollment).order_by(Enrollment.enrolled_at.desc())
        if student_id is not None:
            query = query.where(Enrollment.student_id == student_id)
        if class_id is not None:
            query = query.where(Enrollment.class_id == class_id)
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
