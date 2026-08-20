from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.users.models import User, UserRole


def make_year_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "name": "2024-2025",
        "start_date": "2024-09-01",
        "end_date": "2025-06-30",
    }
    payload.update(overrides)
    return payload


def make_term_payload(academic_year_id: object, **overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "academic_year_id": str(academic_year_id),
        "name": "Term 1",
        "start_date": "2024-09-01",
        "end_date": "2024-12-20",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def make_academic_year(db_session: AsyncSession):
    """Local factory fixture — only this file creates AcademicYears
    directly via the DB, so it isn't promoted to the shared conftest.py
    yet (same pattern as teachers/integration/test_router.py's
    make_teacher)."""

    async def _make_academic_year(**overrides: object) -> AcademicYear:
        defaults: dict[str, object] = {
            "name": "2024-2025",
            "start_date": date(2024, 9, 1),
            "end_date": date(2025, 6, 30),
        }
        defaults.update(overrides)
        year = AcademicYear(**defaults)
        db_session.add(year)
        await db_session.commit()
        await db_session.refresh(year)
        return year

    return _make_academic_year


@pytest.fixture
def make_term(db_session: AsyncSession):
    """Local factory fixture — creates a Term directly via the DB, tied to
    an already-created AcademicYear (pass academic_year_id explicitly)."""

    async def _make_term(academic_year_id: object, **overrides: object) -> Term:
        defaults: dict[str, object] = {
            "academic_year_id": academic_year_id,
            "name": "Term 1",
            "start_date": date(2024, 9, 1),
            "end_date": date(2024, 12, 20),
        }
        defaults.update(overrides)
        term = Term(**defaults)
        db_session.add(term)
        await db_session.commit()
        await db_session.refresh(term)
        return term

    return _make_term


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    most of these tests exercise the "can manage" path; pass
    role=UserRole.TEACHER to exercise the "authenticated but not allowed to
    mutate" path instead (academic-years/terms are ADMIN-only for writes,
    same tier as teachers)."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


# ---------------------------------------------------------------------------
# /academic-years
# ---------------------------------------------------------------------------


async def test_post_academic_years_happy_path(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin1@example.com")

    response = await client.post(
        "/academic-years", json=make_year_payload(), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "2024-2025"
    assert body["start_date"] == "2024-09-01"
    assert body["end_date"] == "2025-06-30"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_academic_years_duplicate_name_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin2@example.com")

    await client.post(
        "/academic-years", json=make_year_payload(name="dup-year"), headers=headers
    )

    response = await client.post(
        "/academic-years", json=make_year_payload(name="dup-year"), headers=headers
    )

    assert response.status_code == 409


async def test_post_academic_years_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/academic-years", json=make_year_payload())

    assert response.status_code == 401


async def test_post_academic_years_as_teacher_role_returns_403(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher1@example.com")

    response = await client.post(
        "/academic-years", json=make_year_payload(), headers=headers
    )

    assert response.status_code == 403


async def test_get_academic_years_list(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    await make_academic_year(name="2023-2024")
    await make_academic_year(name="2024-2025")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher2@example.com")

    response = await client.get("/academic-years", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {y["name"] for y in body} == {"2023-2024", "2024-2025"}


async def test_get_academic_years_list_pagination_smoke(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(3):
        await make_academic_year(name=f"Year-Smoke-{i}")
    headers = await make_manage_headers(email="admin-pg-smoke@example.com")

    response = await client.get(
        "/academic-years", params={"limit": 2, "offset": 0}, headers=headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_academic_years_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/academic-years")

    assert response.status_code == 401


async def test_get_academic_year_by_id_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher3@example.com")

    response = await client.get(f"/academic-years/{year.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(year.id)
    assert body["name"] == year.name


async def test_get_academic_year_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin3@example.com")

    response = await client.get(f"/academic-years/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_academic_year_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin4@example.com")

    response = await client.patch(
        f"/academic-years/{year.id}", json={"name": "2024-2025 Revised"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(year.id)
    assert body["name"] == "2024-2025 Revised"


async def test_patch_academic_year_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin5@example.com")

    response = await client.patch(
        f"/academic-years/{uuid4()}", json={"name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_academic_year_as_teacher_role_returns_403(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher4@example.com")

    response = await client.patch(
        f"/academic-years/{year.id}", json={"name": "Nope"}, headers=headers
    )

    assert response.status_code == 403


async def test_delete_academic_year_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin6@example.com")

    response = await client.delete(f"/academic-years/{year.id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/academic-years/{year.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_academic_year_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin7@example.com")

    response = await client.delete(f"/academic-years/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


# ---------------------------------------------------------------------------
# /terms
# ---------------------------------------------------------------------------


async def test_post_terms_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin8@example.com")

    response = await client.post(
        "/terms", json=make_term_payload(year.id), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert body["academic_year_id"] == str(year.id)
    assert body["name"] == "Term 1"
    assert body["start_date"] == "2024-09-01"
    assert body["end_date"] == "2024-12-20"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_terms_dates_outside_year_returns_409(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin9@example.com")

    response = await client.post(
        "/terms",
        json=make_term_payload(year.id, start_date="2025-07-01", end_date="2025-07-15"),
        headers=headers,
    )

    assert response.status_code == 409


async def test_post_terms_nonexistent_academic_year_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin10@example.com")

    response = await client.post(
        "/terms", json=make_term_payload(uuid4()), headers=headers
    )

    assert response.status_code == 404


async def test_post_terms_duplicate_year_name_returns_409(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(email="admin11@example.com")

    await client.post("/terms", json=make_term_payload(year.id, name="dup-term"), headers=headers)

    response = await client.post(
        "/terms",
        json=make_term_payload(
            year.id, name="dup-term", start_date="2025-01-06", end_date="2025-03-30"
        ),
        headers=headers,
    )

    assert response.status_code == 409


async def test_post_terms_without_token_returns_401(
    client: AsyncClient, make_academic_year: Callable[..., Awaitable[AcademicYear]]
) -> None:
    year = await make_academic_year()

    response = await client.post("/terms", json=make_term_payload(year.id))

    assert response.status_code == 401


async def test_post_terms_as_teacher_role_returns_403(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher5@example.com")

    response = await client.post(
        "/terms", json=make_term_payload(year.id), headers=headers
    )

    assert response.status_code == 403


async def test_get_terms_list(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    await make_term(year.id, name="Term 1")
    await make_term(
        year.id, name="Term 2", start_date=date(2025, 1, 6), end_date=date(2025, 3, 30)
    )
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher6@example.com")

    response = await client.get("/terms", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {t["name"] for t in body} == {"Term 1", "Term 2"}


async def test_get_terms_list_pagination_slices_and_sets_total_count_header(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year(name="PG Year")
    for i in range(5):
        await make_term(
            year.id,
            name=f"Term-PG-{i}",
            start_date=date(2024, 9, 1 + i),
            end_date=date(2024, 9, 20 + i),
        )
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-pg1@example.com")

    response = await client.get("/terms", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "5"


async def test_get_terms_list_filtered_by_academic_year_id(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year_a = await make_academic_year(name="Filter Year A")
    year_b = await make_academic_year(name="Filter Year B")
    term_a = await make_term(year_a.id, name="FA1")
    await make_term(year_b.id, name="FB1")
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-pg2@example.com")

    response = await client.get(
        "/terms", params={"academic_year_id": str(year_a.id)}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == str(term_a.id)


async def test_get_terms_list_newest_first_ordering(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # Explicit, distinguishable created_at — db_session wraps the whole test
    # in one outer Postgres transaction (SAVEPOINT-based rollback, see
    # conftest.py); func.now()/CURRENT_TIMESTAMP is transaction-scoped, not
    # statement-scoped, so every row inserted in one test would otherwise
    # get an identical server-default created_at.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    year = await make_academic_year(name="Ord Year")
    first = await make_term(year.id, name="Ord-1", created_at=base)
    second = await make_term(
        year.id,
        name="Ord-2",
        start_date=date(2025, 1, 6),
        end_date=date(2025, 3, 30),
        created_at=base + timedelta(minutes=1),
    )
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher-pg3@example.com")

    response = await client.get("/terms", headers=headers)

    assert response.status_code == 200
    ids = [t["id"] for t in response.json()]
    assert ids.index(str(second.id)) < ids.index(str(first.id))


async def test_get_terms_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/terms")

    assert response.status_code == 401


async def test_get_term_by_id_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    term = await make_term(year.id)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher7@example.com")

    response = await client.get(f"/terms/{term.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(term.id)
    assert body["academic_year_id"] == str(year.id)


async def test_get_term_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin12@example.com")

    response = await client.get(f"/terms/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_term_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    term = await make_term(year.id)
    headers = await make_manage_headers(email="admin13@example.com")

    response = await client.patch(
        f"/terms/{term.id}", json={"name": "Term 1 Renamed"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(term.id)
    assert body["name"] == "Term 1 Renamed"


async def test_patch_term_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin14@example.com")

    response = await client.patch(
        f"/terms/{uuid4()}", json={"name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_term_as_teacher_role_returns_403(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    term = await make_term(year.id)
    headers = await make_manage_headers(role=UserRole.TEACHER, email="teacher8@example.com")

    response = await client.patch(
        f"/terms/{term.id}", json={"name": "Nope"}, headers=headers
    )

    assert response.status_code == 403


async def test_delete_term_happy_path(
    client: AsyncClient,
    make_academic_year: Callable[..., Awaitable[AcademicYear]],
    make_term: Callable[..., Awaitable[Term]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    year = await make_academic_year()
    term = await make_term(year.id)
    headers = await make_manage_headers(email="admin15@example.com")

    response = await client.delete(f"/terms/{term.id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/terms/{term.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_term_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin16@example.com")

    response = await client.delete(f"/terms/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()
