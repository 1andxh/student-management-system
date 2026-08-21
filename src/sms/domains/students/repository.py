from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.students.models import Student


class StudentRepository(AbstractRepository[Student]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Student, *, commit: bool = True) -> Student:
        self._session.add(entity)
        try:
            if commit:
                await self._session.commit()
            else:
                # Flush, not commit — used when this write must land
                # atomically together with another repository's write (see
                # StudentService.generate_pin, same commit=False/final-
                # shared-commit pattern as UserRepository.add).
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

    async def get(self, entity_id: UUID) -> Student | None:
        return await self._session.get(Student, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[Student], int]:
        query = select(Student).order_by(Student.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

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

    async def get_by_user_id(self, user_id: UUID) -> Student | None:
        result = await self._session.execute(select(Student).where(Student.user_id == user_id))
        return result.scalar_one_or_none()

    async def next_student_number_seq(self) -> int:
        result = await self._session.execute(text("SELECT nextval('student_number_seq')"))
        return result.scalar_one()
