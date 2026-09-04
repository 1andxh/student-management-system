# list_by_section_id / list_by_grade_level_id (added below) would otherwise
# shadow the builtin `list` used in these classes' own `list()` method
# annotations if evaluated eagerly — the exact bug ADR 0018/0019 already hit
# twice. Lazy string annotations sidestep it regardless of method order.
from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.sections.models import GradeLevel, Section, SectionAssignment


class GradeLevelRepository(AbstractRepository[GradeLevel]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: GradeLevel, *, commit: bool = True) -> GradeLevel:
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

    async def get(self, entity_id: UUID) -> GradeLevel | None:
        return await self._session.get(GradeLevel, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[GradeLevel], int]:
        # Ordered by rank, not created_at desc like every other domain —
        # a grade-level list is inherently ordinal (Reception, Grade 1,
        # Grade 2, ...), and newest-first would be meaningless here.
        query = select(GradeLevel).order_by(GradeLevel.rank)
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: GradeLevel) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_name(self, name: str) -> GradeLevel | None:
        result = await self._session.execute(select(GradeLevel).where(GradeLevel.name == name))
        return result.scalar_one_or_none()

    async def get_by_rank(self, rank: int) -> GradeLevel | None:
        result = await self._session.execute(select(GradeLevel).where(GradeLevel.rank == rank))
        return result.scalar_one_or_none()


class SectionRepository(AbstractRepository[Section]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Section, *, commit: bool = True) -> Section:
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

    async def get(self, entity_id: UUID) -> Section | None:
        return await self._session.get(Section, entity_id)

    async def list(
        self,
        *,
        limit: int,
        offset: int,
        grade_level_id: UUID | None = None,
        academic_year_id: UUID | None = None,
    ) -> tuple[list[Section], int]:
        query = select(Section).order_by(Section.created_at.desc())
        if grade_level_id is not None:
            query = query.where(Section.grade_level_id == grade_level_id)
        if academic_year_id is not None:
            query = query.where(Section.academic_year_id == academic_year_id)
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: Section) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_name(
        self, grade_level_id: UUID, academic_year_id: UUID, name: str
    ) -> Section | None:
        result = await self._session.execute(
            select(Section).where(
                Section.grade_level_id == grade_level_id,
                Section.academic_year_id == academic_year_id,
                Section.name == name,
            )
        )
        return result.scalar_one_or_none()

    async def get_for_update(self, entity_id: UUID) -> Section | None:
        # Row lock held until the caller's own commit — the section-capacity
        # guard in SectionAssignmentService.assign reads the count under
        # this lock so two concurrent assignments can't both see room for
        # the last seat. Same pattern and reasoning as
        # ClassRepository.get_for_update (docs/adr/0017).
        # populate_existing matters: with_for_update always takes the DB
        # lock, but if this Section is already in the session's identity map
        # SQLAlchemy hands back the cached instance without refreshing it
        # from the freshly-locked row — so the capacity read could come from
        # a pre-lock snapshot. Not reachable on today's call paths, but it
        # reopens silently the moment anyone adds a Section read above the
        # lock (security-auditor finding).
        result = await self._session.execute(
            select(Section)
            .where(Section.id == entity_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()


class SectionAssignmentRepository(AbstractRepository[SectionAssignment]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self, entity: SectionAssignment, *, commit: bool = True
    ) -> SectionAssignment:
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

    async def get(self, entity_id: UUID) -> SectionAssignment | None:
        return await self._session.get(SectionAssignment, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[SectionAssignment], int]:
        query = select(SectionAssignment).order_by(SectionAssignment.assigned_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: SectionAssignment) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_student_and_year(
        self, student_id: UUID, academic_year_id: UUID
    ) -> SectionAssignment | None:
        result = await self._session.execute(
            select(SectionAssignment).where(
                SectionAssignment.student_id == student_id,
                SectionAssignment.academic_year_id == academic_year_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_by_student_and_section(
        self, student_id: UUID, section_id: UUID
    ) -> SectionAssignment | None:
        result = await self._session.execute(
            select(SectionAssignment).where(
                SectionAssignment.student_id == student_id,
                SectionAssignment.section_id == section_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_latest_by_student_id(self, student_id: UUID) -> SectionAssignment | None:
        """This student's most recent section assignment.

        "Most recent" stands in for "current" because the system has no
        notion of an active academic year — nothing marks one AcademicYear
        as the one in progress. Fine while assignments are created in
        chronological order, which a promotion/rollover stage would make
        explicit; worth revisiting then rather than inferring a current
        year from dates here.
        """
        result = await self._session.execute(
            select(SectionAssignment)
            .where(SectionAssignment.student_id == student_id)
            .order_by(SectionAssignment.assigned_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_by_section_id(self, section_id: UUID) -> list[SectionAssignment]:
        result = await self._session.execute(
            select(SectionAssignment)
            .where(SectionAssignment.section_id == section_id)
            .order_by(SectionAssignment.assigned_at)
        )
        return list(result.scalars().all())

    async def count_by_section_id(self, section_id: UUID) -> int:
        result = await self._session.execute(
            select(func.count()).where(SectionAssignment.section_id == section_id)
        )
        return result.scalar_one()
