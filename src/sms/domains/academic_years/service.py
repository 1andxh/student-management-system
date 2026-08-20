from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.academic_years.exceptions import (
    AcademicYearAlreadyExistsError,
    AcademicYearNotFoundError,
    TermAlreadyExistsError,
    TermNotFoundError,
    TermOutsideAcademicYearError,
)
from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.academic_years.repository import AcademicYearRepository, TermRepository
from sms.domains.academic_years.schemas import (
    AcademicYearCreate,
    AcademicYearUpdate,
    TermCreate,
    TermUpdate,
)


class AcademicYearService:
    def __init__(self, repository: AcademicYearRepository) -> None:
        self._repository = repository

    async def create(self, data: AcademicYearCreate) -> AcademicYear:
        if await self._repository.get_by_name(data.name) is not None:
            raise AcademicYearAlreadyExistsError()

        year = AcademicYear(name=data.name, start_date=data.start_date, end_date=data.end_date)
        try:
            return await self._repository.add(year)
        except IntegrityError as exc:
            raise AcademicYearAlreadyExistsError() from exc

    async def get(self, year_id: UUID) -> AcademicYear:
        year = await self._repository.get(year_id)
        if year is None:
            raise AcademicYearNotFoundError()
        return year

    async def list(self, *, limit: int, offset: int) -> tuple[list[AcademicYear], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, year_id: UUID, data: AcademicYearUpdate) -> AcademicYear:
        year = await self.get(year_id)
        updates = data.model_dump(exclude_unset=True)

        new_name = updates.get("name")
        if new_name is not None and new_name != year.name:
            existing = await self._repository.get_by_name(new_name)
            if existing is not None and existing.id != year_id:
                raise AcademicYearAlreadyExistsError()

        for field, value in updates.items():
            setattr(year, field, value)
        try:
            return await self._repository.add(year)
        except IntegrityError as exc:
            raise AcademicYearAlreadyExistsError() from exc

    async def delete(self, year_id: UUID) -> None:
        year = await self.get(year_id)
        await self._repository.remove(year)


class TermService:
    def __init__(
        self, repository: TermRepository, academic_year_repository: AcademicYearRepository
    ) -> None:
        self._repository = repository
        self._academic_year_repository = academic_year_repository

    async def _validate_within_year(self, academic_year_id: UUID, start_date, end_date) -> None:
        year = await self._academic_year_repository.get(academic_year_id)
        if year is None:
            raise AcademicYearNotFoundError()
        if start_date < year.start_date or end_date > year.end_date:
            raise TermOutsideAcademicYearError()

    async def create(self, data: TermCreate) -> Term:
        await self._validate_within_year(data.academic_year_id, data.start_date, data.end_date)
        if (
            await self._repository.get_by_year_and_name(data.academic_year_id, data.name)
            is not None
        ):
            raise TermAlreadyExistsError()

        term = Term(
            academic_year_id=data.academic_year_id,
            name=data.name,
            start_date=data.start_date,
            end_date=data.end_date,
        )
        try:
            return await self._repository.add(term)
        except IntegrityError as exc:
            raise TermAlreadyExistsError() from exc

    async def get(self, term_id: UUID) -> Term:
        term = await self._repository.get(term_id)
        if term is None:
            raise TermNotFoundError()
        return term

    async def list(
        self, *, limit: int, offset: int, academic_year_id: UUID | None = None
    ) -> tuple[list[Term], int]:
        return await self._repository.list(
            limit=limit, offset=offset, academic_year_id=academic_year_id
        )

    async def update(self, term_id: UUID, data: TermUpdate) -> Term:
        term = await self.get(term_id)
        updates = data.model_dump(exclude_unset=True)

        if "start_date" in updates or "end_date" in updates:
            new_start = updates.get("start_date", term.start_date)
            new_end = updates.get("end_date", term.end_date)
            await self._validate_within_year(term.academic_year_id, new_start, new_end)

        new_name = updates.get("name")
        if new_name is not None and new_name != term.name:
            existing = await self._repository.get_by_year_and_name(
                term.academic_year_id, new_name
            )
            if existing is not None and existing.id != term_id:
                raise TermAlreadyExistsError()

        for field, value in updates.items():
            setattr(term, field, value)
        try:
            return await self._repository.add(term)
        except IntegrityError as exc:
            raise TermAlreadyExistsError() from exc

    async def delete(self, term_id: UUID) -> None:
        term = await self.get(term_id)
        await self._repository.remove(term)
