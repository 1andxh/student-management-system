from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.teachers.models import ChangeRequestStatus, Teacher, TeacherChangeRequest


class TeacherRepository(AbstractRepository[Teacher]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Teacher) -> Teacher:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Teacher | None:
        return await self._session.get(Teacher, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[Teacher], int]:
        query = select(Teacher).order_by(Teacher.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Teacher) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_email(self, email: str) -> Teacher | None:
        result = await self._session.execute(select(Teacher).where(Teacher.email == email))
        return result.scalar_one_or_none()

    async def get_by_user_id(self, user_id: UUID) -> Teacher | None:
        result = await self._session.execute(select(Teacher).where(Teacher.user_id == user_id))
        return result.scalar_one_or_none()


class TeacherChangeRequestRepository(AbstractRepository[TeacherChangeRequest]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: TeacherChangeRequest) -> TeacherChangeRequest:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> TeacherChangeRequest | None:
        return await self._session.get(TeacherChangeRequest, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[TeacherChangeRequest], int]:
        query = select(TeacherChangeRequest).order_by(TeacherChangeRequest.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: TeacherChangeRequest) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_pending_by_teacher_id(self, teacher_id: UUID) -> TeacherChangeRequest | None:
        result = await self._session.execute(
            select(TeacherChangeRequest).where(
                TeacherChangeRequest.teacher_id == teacher_id,
                TeacherChangeRequest.status == ChangeRequestStatus.PENDING,
            )
        )
        return result.scalar_one_or_none()
