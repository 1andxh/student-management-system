from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.repository import AbstractRepository
from sms.domains.students.models import Student


class StudentRepository(AbstractRepository[Student]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Student) -> Student:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Student | None:
        return await self._session.get(Student, entity_id)

    async def list(self) -> list[Student]:
        result = await self._session.execute(select(Student))
        return list(result.scalars().all())

    async def remove(self, entity: Student) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_email(self, email: str) -> Student | None:
        result = await self._session.execute(select(Student).where(Student.email == email))
        return result.scalar_one_or_none()

    async def get_by_student_number(self, student_number: str) -> Student | None:
        result = await self._session.execute(
            select(Student).where(Student.student_number == student_number)
        )
        return result.scalar_one_or_none()
