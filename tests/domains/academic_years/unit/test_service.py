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


async def test_create_success(year_service: AcademicYearService) -> None:
    data = make_academic_year_create()

    year = await year_service.create(data)

    assert year.id is not None
    assert year.name == "2024-2025"
    assert year.start_date == date(2024, 9, 1)
    assert year.end_date == date(2025, 6, 30)


async def test_create_duplicate_name_raises(year_service: AcademicYearService) -> None:
    await year_service.create(make_academic_year_create(name="dup"))

    with pytest.raises(AcademicYearAlreadyExistsError):
        await year_service.create(make_academic_year_create(name="dup"))


async def test_get_success(year_service: AcademicYearService) -> None:
    created = await year_service.create(make_academic_year_create())

    fetched = await year_service.get(created.id)

    assert fetched.id == created.id
    assert fetched.name == created.name


async def test_get_missing_raises(year_service: AcademicYearService) -> None:
    with pytest.raises(AcademicYearNotFoundError):
        await year_service.get(uuid4())


async def test_list(year_service: AcademicYearService) -> None:
    await year_service.create(make_academic_year_create(name="2023-2024"))
    await year_service.create(make_academic_year_create(name="2024-2025"))

    years, total = await year_service.list(limit=50, offset=0)

    assert len(years) == 2
    assert total == 2
    assert {y.name for y in years} == {"2023-2024", "2024-2025"}


async def test_list_pagination_smoke(year_service: AcademicYearService) -> None:
    for i in range(3):
        await year_service.create(make_academic_year_create(name=f"Year-PG-{i}"))

    page, total = await year_service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 3


async def test_update_success(year_service: AcademicYearService) -> None:
    created = await year_service.create(make_academic_year_create())

    updated = await year_service.update(created.id, AcademicYearUpdate(name="2024-2025 Revised"))

    assert updated.id == created.id
    assert updated.name == "2024-2025 Revised"
    assert updated.start_date == created.start_date


async def test_update_duplicate_name_raises(year_service: AcademicYearService) -> None:
    await year_service.create(make_academic_year_create(name="taken"))
    other = await year_service.create(make_academic_year_create(name="free"))

    with pytest.raises(AcademicYearAlreadyExistsError):
        await year_service.update(other.id, AcademicYearUpdate(name="taken"))


async def test_update_missing_raises(year_service: AcademicYearService) -> None:
    with pytest.raises(AcademicYearNotFoundError):
        await year_service.update(uuid4(), AcademicYearUpdate(name="Nobody"))


async def test_delete_success(
    year_service: AcademicYearService, year_repository: FakeAcademicYearRepository
) -> None:
    created = await year_service.create(make_academic_year_create())

    await year_service.delete(created.id)

    assert await year_repository.get(created.id) is None


async def test_delete_missing_raises(year_service: AcademicYearService) -> None:
    with pytest.raises(AcademicYearNotFoundError):
        await year_service.delete(uuid4())


# ---------------------------------------------------------------------------
# TermService
# ---------------------------------------------------------------------------


async def test_create_term_success(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    data = make_term_create(academic_year_id=academic_year.id)

    term = await term_service.create(data)

    assert term.id is not None
    assert term.academic_year_id == academic_year.id
    assert term.name == "Term 1"
    assert term.start_date == date(2024, 9, 1)
    assert term.end_date == date(2024, 12, 20)


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


async def test_create_nonexistent_academic_year_raises(term_service: TermService) -> None:
    data = make_term_create(academic_year_id=uuid4())

    with pytest.raises(AcademicYearNotFoundError):
        await term_service.create(data)


async def test_create_term_duplicate_name_raises(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    await term_service.create(make_term_create(academic_year_id=academic_year.id, name="dup"))

    with pytest.raises(TermAlreadyExistsError):
        await term_service.create(
            make_term_create(
                academic_year_id=academic_year.id,
                name="dup",
                start_date=date(2025, 1, 6),
                end_date=date(2025, 3, 30),
            )
        )


async def test_get_term_success(term_service: TermService, academic_year: AcademicYear) -> None:
    created = await term_service.create(make_term_create(academic_year_id=academic_year.id))

    fetched = await term_service.get(created.id)

    assert fetched.id == created.id
    assert fetched.name == created.name


async def test_get_term_missing_raises(term_service: TermService) -> None:
    with pytest.raises(TermNotFoundError):
        await term_service.get(uuid4())


async def test_list_terms(term_service: TermService, academic_year: AcademicYear) -> None:
    await term_service.create(make_term_create(academic_year_id=academic_year.id, name="Term 1"))
    await term_service.create(
        make_term_create(
            academic_year_id=academic_year.id,
            name="Term 2",
            start_date=date(2025, 1, 6),
            end_date=date(2025, 3, 30),
        )
    )

    terms, total = await term_service.list(limit=50, offset=0)

    assert len(terms) == 2
    assert total == 2
    assert {t.name for t in terms} == {"Term 1", "Term 2"}


async def test_list_terms_pagination_slices_and_reports_total(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    for i in range(5):
        await term_service.create(
            make_term_create(
                academic_year_id=academic_year.id,
                name=f"Term-PG-{i}",
                start_date=date(2024, 9, 1),
                end_date=date(2024, 9, 30),
            )
        )

    page, total = await term_service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 5


async def test_list_terms_filtered_by_academic_year_id(
    term_service: TermService, year_service: AcademicYearService
) -> None:
    year_a = await year_service.create(make_academic_year_create(name="Year A"))
    year_b = await year_service.create(make_academic_year_create(name="Year B"))
    term_a = await term_service.create(make_term_create(academic_year_id=year_a.id, name="A1"))
    await term_service.create(make_term_create(academic_year_id=year_b.id, name="B1"))

    filtered, total = await term_service.list(academic_year_id=year_a.id, limit=50, offset=0)

    assert total == 1
    assert [t.id for t in filtered] == [term_a.id]


async def test_list_terms_newest_first_ordering(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    first = await term_service.create(
        make_term_create(academic_year_id=academic_year.id, name="Ord-1")
    )
    second = await term_service.create(
        make_term_create(
            academic_year_id=academic_year.id,
            name="Ord-2",
            start_date=date(2025, 1, 6),
            end_date=date(2025, 3, 30),
        )
    )

    page, total = await term_service.list(limit=50, offset=0)

    assert total == 2
    assert [t.id for t in page] == [second.id, first.id]


async def test_update_success_name_only(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    created = await term_service.create(make_term_create(academic_year_id=academic_year.id))

    updated = await term_service.update(created.id, TermUpdate(name="Term 1 Renamed"))

    assert updated.id == created.id
    assert updated.name == "Term 1 Renamed"
    assert updated.start_date == created.start_date


async def test_update_success_dates_within_range(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    created = await term_service.create(make_term_create(academic_year_id=academic_year.id))

    updated = await term_service.update(
        created.id,
        TermUpdate(start_date=date(2024, 9, 15), end_date=date(2024, 12, 10)),
    )

    assert updated.start_date == date(2024, 9, 15)
    assert updated.end_date == date(2024, 12, 10)


async def test_update_dates_outside_year_raises(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    created = await term_service.create(make_term_create(academic_year_id=academic_year.id))

    with pytest.raises(TermOutsideAcademicYearError):
        await term_service.update(
            created.id,
            TermUpdate(start_date=date(2025, 7, 1), end_date=date(2025, 7, 15)),
        )


async def test_update_term_duplicate_name_raises(
    term_service: TermService, academic_year: AcademicYear
) -> None:
    await term_service.create(make_term_create(academic_year_id=academic_year.id, name="Term 1"))
    second = await term_service.create(
        make_term_create(
            academic_year_id=academic_year.id,
            name="Term 2",
            start_date=date(2025, 1, 6),
            end_date=date(2025, 3, 30),
        )
    )

    with pytest.raises(TermAlreadyExistsError):
        await term_service.update(second.id, TermUpdate(name="Term 1"))


async def test_update_term_missing_raises(term_service: TermService) -> None:
    with pytest.raises(TermNotFoundError):
        await term_service.update(uuid4(), TermUpdate(name="Nobody"))


async def test_delete_term_success(
    term_service: TermService, term_repository: FakeTermRepository, academic_year: AcademicYear
) -> None:
    created = await term_service.create(make_term_create(academic_year_id=academic_year.id))

    await term_service.delete(created.id)

    assert await term_repository.get(created.id) is None


async def test_delete_term_missing_raises(term_service: TermService) -> None:
    with pytest.raises(TermNotFoundError):
        await term_service.delete(uuid4())
