# Prevents the "method named `list` shadows the builtin `list` for every
# later annotation in the same class body" gotcha — same root cause as the
# date/date_type collision (docs/adr/0018), now hit at the method level
# (list_by_teacher_id's `-> list[Class]` below). Annotations become lazy
# strings, evaluated never at class-body-execution time, so this can't
# recur in this file regardless of method order.
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.classes.models import Class, Subject


class SubjectRepository(AbstractRepository[Subject]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Subject) -> Subject:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Subject | None:
        return await self._session.get(Subject, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[Subject], int]:
        query = select(Subject).order_by(Subject.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Subject) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_code(self, code: str) -> Subject | None:
        result = await self._session.execute(select(Subject).where(Subject.code == code))
        return result.scalar_one_or_none()


class ClassRepository(AbstractRepository[Class]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Class, *, commit: bool = True) -> Class:
        self._session.add(entity)
        try:
            if commit:
                await self._session.commit()
            else:
                # Flush, not commit — used when this write must land
                # atomically alongside others on the same session, e.g.
                # SectionService.attach_class setting section_id and
                # back-filling Enrollment rows in one transaction.
                await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Class | None:
        return await self._session.get(Class, entity_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        term_id: UUID | None = None,
        subject_id: UUID | None = None,
        teacher_id: UUID | None = None,
    ) -> tuple[list[Class], int]:
        query = select(Class).order_by(Class.created_at.desc())
        if term_id is not None:
            query = query.where(Class.term_id == term_id)
        if subject_id is not None:
            query = query.where(Class.subject_id == subject_id)
        if teacher_id is not None:
            query = query.where(Class.teacher_id == teacher_id)
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Class) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def list_by_teacher_id(self, teacher_id: UUID) -> list[Class]:
        result = await self._session.execute(select(Class).where(Class.teacher_id == teacher_id))
        return list(result.scalars().all())

    async def list_by_section_id(self, section_id: UUID) -> list[Class]:
        result = await self._session.execute(select(Class).where(Class.section_id == section_id))
        return list(result.scalars().all())

    async def get_for_update(self, entity_id: UUID) -> Class | None:
        # Row lock held until the caller's own commit — the capacity-race
        # guard in EnrollmentService.enroll() depends on nothing else
        # committing on this session between this read and that commit,
        # same invariant as UserRepository.count_active_super_admins()
        # (docs/adr/0011). See docs/adr/0017.
        # populate_existing: the lock is always taken, but a Class already in
        # the session's identity map would otherwise be returned unrefreshed,
        # so the capacity read could predate the lock. Same hardening applied
        # to SectionRepository.get_for_update.
        result = await self._session.execute(
            select(Class)
            .where(Class.id == entity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()
