from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.academic_years.exceptions import (
    AcademicYearAlreadyExistsError,
    AcademicYearNotFoundError,
    TermAlreadyExistsError,
    TermNotFoundError,
    TermOutsideAcademicYearError,
)
from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.academic_years.schemas import (
    AcademicYearCreate,
    AcademicYearUpdate,
    TermCreate,
    TermUpdate,
)
from sms.domains.academic_years.service import AcademicYearService, TermService

# Arbitrary fixed epoch — only used as a base for the fakes' deterministic,
# monotonically increasing created_at stamps, same pattern as
# tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeAcademicYearRepository(AbstractRepository[AcademicYear]):
    """In-memory stand-in for AcademicYearRepository, backed by a plain
    dict. Mirrors uq_academic_years_name the same "pre-check narrows the
    window, doesn't close it" way as every other domain's fake (see
    docs/adr/0004) — AcademicYearService pre-checks too, but this keeps the
    fake faithful to what Postgres actually does if a race ever slips past
    that pre-check."""

    def __init__(self) -> None:
        self._years: dict[UUID, AcademicYear] = {}
        self._sequence = 0

    async def add(self, entity: AcademicYear) -> AcademicYear:
        for existing_id, existing in self._years.items():
            if existing_id == entity.id:
                continue
            if existing.name == entity.name:
                raise IntegrityError("duplicate name", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._years[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> AcademicYear | None:
        return self._years.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[AcademicYear], int]:
        all_years = sorted(self._years.values(), key=lambda y: y.created_at, reverse=True)
        return all_years[offset : offset + limit], len(all_years)

    async def remove(self, entity: AcademicYear) -> None:
        self._years.pop(entity.id, None)

    async def get_by_name(self, name: str) -> AcademicYear | None:
        for year in self._years.values():
            if year.name == name:
                return year
        return None


class FakeTermRepository(AbstractRepository[Term]):
    """In-memory stand-in for TermRepository, mirroring
    uq_terms_year_name (composite on academic_year_id + name)."""

    def __init__(self) -> None:
        self._terms: dict[UUID, Term] = {}
        self._sequence = 0

    async def add(self, entity: Term) -> Term:
        for existing_id, existing in self._terms.items():
            if existing_id == entity.id:
                continue
            if (
                existing.academic_year_id == entity.academic_year_id
                and existing.name == entity.name
            ):
                raise IntegrityError("duplicate (year, name)", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._terms[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Term | None:
        return self._terms.get(entity_id)

    async def list(
        self,
        *,
        academic_year_id: UUID | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[Term], int]:
        results = list(self._terms.values())
        if academic_year_id is not None:
            results = [t for t in results if t.academic_year_id == academic_year_id]
        results.sort(key=lambda t: t.created_at, reverse=True)
        return results[offset : offset + limit], len(results)

    async def remove(self, entity: Term) -> None:
        self._terms.pop(entity.id, None)

    async def get_by_year_and_name(self, academic_year_id: UUID, name: str) -> Term | None:
        for term in self._terms.values():
            if term.academic_year_id == academic_year_id and term.name == name:
                return term
        return None


def make_academic_year_create(**overrides: object) -> AcademicYearCreate:
    defaults: dict[str, object] = {
        "name": "2024-2025",
        "start_date": date(2024, 9, 1),
        "end_date": date(2025, 6, 30),
    }
    defaults.update(overrides)
    return AcademicYearCreate(**defaults)


def make_term_create(academic_year_id: UUID, **overrides: object) -> TermCreate:
    defaults: dict[str, object] = {
        "academic_year_id": academic_year_id,
        "name": "Term 1",
        "start_date": date(2024, 9, 1),
        "end_date": date(2024, 12, 20),
    }
    defaults.update(overrides)
    return TermCreate(**defaults)


@pytest.fixture
def year_repository() -> FakeAcademicYearRepository:
    return FakeAcademicYearRepository()


@pytest.fixture
def year_service(year_repository: FakeAcademicYearRepository) -> AcademicYearService:
    return AcademicYearService(year_repository)


@pytest.fixture
def term_repository() -> FakeTermRepository:
    return FakeTermRepository()


@pytest.fixture
def term_service(
    term_repository: FakeTermRepository, year_repository: FakeAcademicYearRepository
) -> TermService:
    return TermService(term_repository, year_repository)


@pytest.fixture
async def academic_year(year_service: AcademicYearService) -> AcademicYear:
    return await year_service.create(make_academic_year_create())


# ---------------------------------------------------------------------------
# AcademicYearService
# ---------------------------------------------------------------------------


async def test_create_dates_before_year_start_raises(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    data = make_term_create(
        academic_year_id=academic_year.id,
        start_date=date(2024, 8, 1),
        end_date=date(2024, 8, 15),
    )

    with pytest.raises(TermOutsideAcademicYearError):
        await term_service.create(data)


async def test_create_dates_after_year_end_raises(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    data = make_term_create(
        academic_year_id=academic_year.id,
        start_date=date(2025, 7, 1),
        end_date=date(2025, 7, 15),
    )

    with pytest.raises(TermOutsideAcademicYearError):
        await term_service.create(data)


async def test_update_dates_outside_year_raises(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    created = await term_service.create(make_term_create(academic_year_id=academic_year.id))

    with pytest.raises(TermOutsideAcademicYearError):
        await term_service.update(
            created.id,
            TermUpdate(start_date=date(2025, 7, 1), end_date=date(2025, 7, 15)),
        )


