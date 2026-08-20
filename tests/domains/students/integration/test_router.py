from collections.abc import Awaitable, Callable
from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.users.models import User, UserRole
from sms.domains.students.models import Student


def make_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "student_number": "S-1000",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": "2010-01-01",
        "email": "ada@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def make_student(db_session: AsyncSession):
    """Local factory fixture — only this file creates Students directly via
    the DB, so it isn't promoted to the shared conftest.py yet."""

    async def _make_student(**overrides: object) -> Student:
        defaults: dict[str, object] = {
            "student_number": "S-2000",
            "first_name": "Grace",
            "last_name": "Hopper",
            "date_of_birth": date(1906, 12, 9),
            "email": "grace@example.com",
            "guardian_name": "Walter Hopper",
            "guardian_phone": "+1-555-0200",
        }
        defaults.update(overrides)
        student = Student(**defaults)
        db_session.add(student)
        await db_session.commit()
        await db_session.refresh(student)
        return student

    return _make_student


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    most of these tests exercise the "can manage" path; pass
    role=UserRole.STUDENT to exercise the "authenticated but not allowed to
    mutate" path instead."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


async def test_post_students_happy_path(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin1@example.com")

    response = await client.post("/students", json=make_payload(), headers=headers)

    assert response.status_code == 201
    body = response.json()
    assert body["student_number"] == "S-1000"
    assert body["first_name"] == "Ada"
    assert body["last_name"] == "Lovelace"
    assert body["date_of_birth"] == "2010-01-01"
    assert body["email"] == "ada@example.com"
    assert body["guardian_name"] == "Byron Lovelace"
    assert body["guardian_phone"] == "+1-555-0100"
    assert body["enrollment_status"] == "active"
    assert "id" in body
    assert "created_at" in body
    assert "updated_at" in body


async def test_post_students_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/students", json=make_payload())

    assert response.status_code == 401


async def test_post_students_as_student_role_returns_403(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(role=UserRole.STUDENT, email="student1@example.com")

    response = await client.post("/students", json=make_payload(), headers=headers)

    assert response.status_code == 403


async def test_post_students_duplicate_email_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin2@example.com")

    await client.post(
        "/students",
        json=make_payload(student_number="S-1001", email="dup@example.com"),
        headers=headers,
    )

    response = await client.post(
        "/students",
        json=make_payload(student_number="S-1002", email="dup@example.com"),
        headers=headers,
    )

    assert response.status_code == 409


async def test_post_students_duplicate_student_number_returns_409(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin3@example.com")

    await client.post(
        "/students",
        json=make_payload(student_number="S-DUP", email="one@example.com"),
        headers=headers,
    )

    response = await client.post(
        "/students",
        json=make_payload(student_number="S-DUP", email="two@example.com"),
        headers=headers,
    )

    assert response.status_code == 409


async def test_get_students_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/students")

    assert response.status_code == 401


async def test_get_students_list(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    await make_student(student_number="S-3001", email="one@example.com")
    await make_student(student_number="S-3002", email="two@example.com")
    # A student-role account can read even though it can't mutate — proves
    # the read path is gated on "authenticated", not "admin/teacher".
    headers = await make_manage_headers(role=UserRole.STUDENT, email="student2@example.com")

    response = await client.get("/students", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) == 2
    assert {s["student_number"] for s in body} == {"S-3001", "S-3002"}


async def test_get_student_by_id_happy_path(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    headers = await make_manage_headers(role=UserRole.STUDENT, email="student3@example.com")

    response = await client.get(f"/students/{student.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(student.id)
    assert body["email"] == student.email


async def test_get_student_by_id_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin4@example.com")

    response = await client.get(f"/students/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_student_happy_path(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    headers = await make_manage_headers(email="admin5@example.com")

    response = await client.patch(
        f"/students/{student.id}", json={"first_name": "Grace-Updated"}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(student.id)
    assert body["first_name"] == "Grace-Updated"
    assert body["last_name"] == student.last_name


async def test_patch_student_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin6@example.com")

    response = await client.patch(
        f"/students/{uuid4()}", json={"first_name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_delete_student_happy_path(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    student = await make_student()
    headers = await make_manage_headers(email="admin7@example.com")

    response = await client.delete(f"/students/{student.id}", headers=headers)

    assert response.status_code == 204

    follow_up = await client.get(f"/students/{student.id}", headers=headers)
    assert follow_up.status_code == 404


async def test_delete_student_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin8@example.com")

    response = await client.delete(f"/students/{uuid4()}", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_get_students_list_pagination_slices_and_sets_total_count_header(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(5):
        await make_student(student_number=f"S-PG-{i:04d}", email=f"pg{i}@example.com")
    headers = await make_manage_headers(email="admin-pg1@example.com")

    response = await client.get("/students", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert response.headers["X-Total-Count"] == "5"


async def test_get_students_list_pagination_offset_skips_correctly(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # Explicit, distinguishable created_at per row — db_session wraps the
    # whole test in one outer Postgres transaction (SAVEPOINT-based
    # rollback, see conftest.py), and func.now()/CURRENT_TIMESTAMP is
    # transaction-scoped, not statement-scoped, so every row inserted
    # within a single test would otherwise get an identical server-default
    # created_at, making the newest-first ordering nondeterministic among
    # ties. Passing created_at explicitly is the same override any other
    # constructor kwarg gets via make_student's **overrides.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    created = [
        await make_student(
            student_number=f"S-OFF-{i:04d}",
            email=f"off{i}@example.com",
            created_at=base + timedelta(minutes=i),
        )
        for i in range(5)
    ]
    headers = await make_manage_headers(email="admin-pg2@example.com")

    first_page = await client.get(
        "/students", params={"limit": 2, "offset": 0}, headers=headers
    )
    second_page = await client.get(
        "/students", params={"limit": 2, "offset": 2}, headers=headers
    )

    first_page_ids = {s["id"] for s in first_page.json()}
    second_page_ids = {s["id"] for s in second_page.json()}
    assert first_page_ids.isdisjoint(second_page_ids)
    # newest-first: the most recently created students appear first, so
    # offset=2 skips the two newest, landing on the middle two.
    expected_full_order = [str(s.id) for s in reversed(created)]
    assert [s["id"] for s in second_page.json()] == expected_full_order[2:4]


async def test_get_students_list_newest_first_ordering(
    client: AsyncClient,
    make_student: Callable[..., Awaitable[Student]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    # Explicit, distinguishable created_at — see the offset test above for
    # why (func.now() is transaction-scoped, and this whole test runs
    # inside one outer transaction via db_session's SAVEPOINT isolation).
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    first = await make_student(
        student_number="S-ORD-1", email="ordhttp1@example.com", created_at=base
    )
    second = await make_student(
        student_number="S-ORD-2",
        email="ordhttp2@example.com",
        created_at=base + timedelta(minutes=1),
    )
    third = await make_student(
        student_number="S-ORD-3",
        email="ordhttp3@example.com",
        created_at=base + timedelta(minutes=2),
    )
    headers = await make_manage_headers(email="admin-pg3@example.com")

    response = await client.get("/students", headers=headers)

    assert response.status_code == 200
    ids = [s["id"] for s in response.json()]
    assert ids.index(str(third.id)) < ids.index(str(second.id)) < ids.index(str(first.id))


async def test_post_students_missing_required_field_returns_422(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_manage_headers(email="admin9@example.com")
    payload = make_payload()
    del payload["email"]

    response = await client.post("/students", json=payload, headers=headers)

    assert response.status_code == 422
    body = response.json()
    assert body["detail"] == "Validation failed."
    assert "errors" in body
