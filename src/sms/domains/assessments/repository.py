from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.assessments.models import Assessment, Grade


class AssessmentRepository(AbstractRepository[Assessment]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Assessment) -> Assessment:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Assessment | None:
        return await self._session.get(Assessment, entity_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        class_id: UUID | None = None,
        class_ids: list[UUID] | None = None,
    ) -> tuple[list[Assessment], int]:
        query = select(Assessment).order_by(Assessment.created_at.desc())
        if class_id is not None:
            query = query.where(Assessment.class_id == class_id)
        elif class_ids is not None:
            query = query.where(Assessment.class_id.in_(class_ids))
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Assessment) -> None:
        await self._session.delete(entity)
        await self._session.commit()


class GradeRepository(AbstractRepository[Grade]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Grade) -> Grade:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Grade | None:
        return await self._session.get(Grade, entity_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        class_id: UUID | None = None,
        class_ids: list[UUID] | None = None,
        student_id: UUID | None = None,
        assessment_id: UUID | None = None,
    ) -> tuple[list[Grade], int]:
        query = select(Grade).order_by(Grade.graded_at.desc())
        if class_id is not None or class_ids is not None:
            # Grade has no class_id column directly — join through
            # Assessment, the only place that relationship is recorded.
            query = query.join(Assessment, Grade.assessment_id == Assessment.id)
            if class_id is not None:
                query = query.where(Assessment.class_id == class_id)
            else:
                query = query.where(Assessment.class_id.in_(class_ids))
        if student_id is not None:
            query = query.where(Grade.student_id == student_id)
        if assessment_id is not None:
            query = query.where(Grade.assessment_id == assessment_id)
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Grade) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_assessment_and_student(
        self, assessment_id: UUID, student_id: UUID
    ) -> Grade | None:
        result = await self._session.execute(
            select(Grade).where(
                Grade.assessment_id == assessment_id,
                Grade.student_id == student_id,
            )
        )
        return result.scalar_one_or_none()
