from collections.abc import Awaitable, Callable
from datetime import date
from uuid import uuid4

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.teachers.models import Teacher
from sms.domains.users.models import User, UserRole


@pytest.fixture
def make_teacher(db_session: AsyncSession):
    """Local factory fixture, same shape as the one in test_router.py (not
    shared via conftest.py — see that file's comment). Supports a user_id
    override directly since Teacher.user_id is just another constructor
    kwarg, which is what make_teacher_user below relies on to link a
    Teacher to a specific login account."""

    async def _make_teacher(**overrides: object) -> Teacher:
        defaults: dict[str, object] = {
            "first_name": "Grace",
            "last_name": "Hopper",
            "email": "grace@example.com",
            "hire_date": date(2015, 6, 1),
        }
        defaults.update(overrides)
        teacher = Teacher(**defaults)
        db_session.add(teacher)
        await db_session.commit()
        await db_session.refresh(teacher)
        return teacher

    return _make_teacher


@pytest.fixture
def make_manage_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    most of these tests exercise the admin-only routes."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


@pytest.fixture
def make_teacher_user(
    make_user: Callable[..., Awaitable[User]],
    make_teacher: Callable[..., Awaitable[Teacher]],
    auth_headers: Callable[[User], dict[str, str]],
):
    """Creates a User with role=TEACHER plus a Teacher record whose
    user_id points back at that User — the shape /teachers/me and
    /teachers/me/change-requests need, since they resolve the caller's own
    Teacher from the bearer token's user_id (service.get_my_teacher).
    user_email controls the login account's email; teacher_overrides
    control the linked Teacher's HR fields (first_name/last_name/email),
    which are a separate, independently-unique-constrained field from the
    login email."""

    async def _make_teacher_user(
        user_email: str = "teacher-user@example.com", **teacher_overrides: object
    ) -> tuple[dict[str, str], Teacher, User]:
        user = await make_user(role=UserRole.TEACHER, email=user_email)
        defaults: dict[str, object] = {"user_id": user.id}
        defaults.update(teacher_overrides)
        teacher = await make_teacher(**defaults)
        headers = auth_headers(user)
        return headers, teacher, user

    return _make_teacher_user


# ---------------------------------------------------------------------------
# GET /teachers/me
# ---------------------------------------------------------------------------


async def test_get_teachers_me_happy_path(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    headers, teacher, _ = await make_teacher_user(
        "me-happy@example.com", email="me-happy-teacher@example.com"
    )

    response = await client.get("/teachers/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(teacher.id)
    assert body["email"] == teacher.email


async def test_get_teachers_me_no_linked_record_returns_404(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = await make_user(role=UserRole.TEACHER, email="no-link@example.com")
    headers = auth_headers(user)

    response = await client.get("/teachers/me", headers=headers)

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_get_teachers_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/teachers/me")

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# POST /teachers/me/change-requests
# ---------------------------------------------------------------------------


async def test_post_change_requests_happy_path(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    headers, teacher, user = await make_teacher_user(
        "post-happy@example.com", email="post-happy-teacher@example.com"
    )

    response = await client.post(
        "/teachers/me/change-requests",
        json={"first_name": "Updated", "email": "updated@example.com"},
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["teacher_id"] == str(teacher.id)
    assert body["requested_by"] == str(user.id)
    assert body["proposed_changes"] == {
        "first_name": "Updated",
        "email": "updated@example.com",
    }
    assert body["status"] == "pending"
    assert body["reviewed_by"] is None
    assert body["reviewed_at"] is None


async def test_post_change_requests_no_linked_teacher_returns_404(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = await make_user(role=UserRole.TEACHER, email="post-no-link@example.com")
    headers = auth_headers(user)

    response = await client.post(
        "/teachers/me/change-requests", json={"first_name": "Nobody"}, headers=headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_post_change_requests_second_pending_returns_409(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    headers, _, _ = await make_teacher_user(
        "post-dup@example.com", email="post-dup-teacher@example.com"
    )
    await client.post(
        "/teachers/me/change-requests", json={"first_name": "First"}, headers=headers
    )

    response = await client.post(
        "/teachers/me/change-requests", json={"first_name": "Second"}, headers=headers
    )

    assert response.status_code == 409


async def test_post_change_requests_empty_body_returns_422(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    headers, _, _ = await make_teacher_user(
        "post-empty@example.com", email="post-empty-teacher@example.com"
    )

    response = await client.post("/teachers/me/change-requests", json={}, headers=headers)

    assert response.status_code == 422


# ---------------------------------------------------------------------------
# GET /teachers/change-requests
# ---------------------------------------------------------------------------


async def test_get_change_requests_as_admin_returns_list(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher_headers, _, _ = await make_teacher_user(
        "list-owner@example.com", email="list-owner-teacher@example.com"
    )
    await client.post(
        "/teachers/me/change-requests", json={"first_name": "Listed"}, headers=teacher_headers
    )
    admin_headers = await make_manage_headers(email="list-admin@example.com")

    response = await client.get("/teachers/change-requests", headers=admin_headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert len(body) >= 1
    assert any(r["proposed_changes"] == {"first_name": "Listed"} for r in body)


async def test_get_change_requests_pagination_smoke(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(3):
        teacher_headers, _, _ = await make_teacher_user(
            f"pgsmoke{i}@example.com", email=f"pgsmoke-teacher{i}@example.com"
        )
        await client.post(
            "/teachers/me/change-requests",
            json={"first_name": f"Smoke{i}"},
            headers=teacher_headers,
        )
    admin_headers = await make_manage_headers(email="pg-smoke-admin@example.com")

    response = await client.get(
        "/teachers/change-requests", params={"limit": 2, "offset": 0}, headers=admin_headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    assert response.headers["X-Total-Count"] == "3"


async def test_get_change_requests_as_non_admin_returns_403(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    headers, _, _ = await make_teacher_user(
        "list-nonadmin@example.com", email="list-nonadmin-teacher@example.com"
    )

    response = await client.get("/teachers/change-requests", headers=headers)

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /teachers/change-requests/{request_id}/approve
# ---------------------------------------------------------------------------


async def test_patch_approve_happy_path_applies_change(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher_headers, teacher, _ = await make_teacher_user(
        "approve-owner@example.com", email="approve-owner-teacher@example.com"
    )
    admin_headers = await make_manage_headers(email="approve-admin@example.com")
    create_response = await client.post(
        "/teachers/me/change-requests",
        json={"first_name": "Approved-Name"},
        headers=teacher_headers,
    )
    request_id = create_response.json()["id"]

    response = await client.patch(
        f"/teachers/change-requests/{request_id}/approve", headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "approved"
    assert body["reviewed_by"] is not None
    assert body["reviewed_at"] is not None

    follow_up = await client.get(f"/teachers/{teacher.id}", headers=admin_headers)
    assert follow_up.status_code == 200
    assert follow_up.json()["first_name"] == "Approved-Name"


async def test_patch_approve_missing_returns_404(
    client: AsyncClient, make_manage_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    admin_headers = await make_manage_headers(email="approve-404-admin@example.com")

    response = await client.patch(
        f"/teachers/change-requests/{uuid4()}/approve", headers=admin_headers
    )

    assert response.status_code == 404
    assert "detail" in response.json()


async def test_patch_approve_already_reviewed_returns_409(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher_headers, _, _ = await make_teacher_user(
        "approve-dup@example.com", email="approve-dup-teacher@example.com"
    )
    admin_headers = await make_manage_headers(email="approve-dup-admin@example.com")
    create_response = await client.post(
        "/teachers/me/change-requests", json={"first_name": "Once"}, headers=teacher_headers
    )
    request_id = create_response.json()["id"]
    await client.patch(f"/teachers/change-requests/{request_id}/approve", headers=admin_headers)

    response = await client.patch(
        f"/teachers/change-requests/{request_id}/approve", headers=admin_headers
    )

    assert response.status_code == 409


async def test_patch_approve_as_non_admin_returns_403(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    teacher_headers, _, _ = await make_teacher_user(
        "approve-nonadmin@example.com", email="approve-nonadmin-teacher@example.com"
    )
    create_response = await client.post(
        "/teachers/me/change-requests", json={"first_name": "Nope"}, headers=teacher_headers
    )
    request_id = create_response.json()["id"]

    response = await client.patch(
        f"/teachers/change-requests/{request_id}/approve", headers=teacher_headers
    )

    assert response.status_code == 403


# ---------------------------------------------------------------------------
# PATCH /teachers/change-requests/{request_id}/reject
# ---------------------------------------------------------------------------


async def test_patch_reject_happy_path_leaves_teacher_unchanged(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
    make_manage_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    teacher_headers, teacher, _ = await make_teacher_user(
        "reject-owner@example.com", email="reject-owner-teacher@example.com"
    )
    admin_headers = await make_manage_headers(email="reject-admin@example.com")
    create_response = await client.post(
        "/teachers/me/change-requests",
        json={"first_name": "Should-Not-Apply"},
        headers=teacher_headers,
    )
    request_id = create_response.json()["id"]

    response = await client.patch(
        f"/teachers/change-requests/{request_id}/reject", headers=admin_headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "rejected"
    assert body["reviewed_by"] is not None
    assert body["reviewed_at"] is not None

    follow_up = await client.get(f"/teachers/{teacher.id}", headers=admin_headers)
    assert follow_up.status_code == 200
    assert follow_up.json()["first_name"] == teacher.first_name


async def test_patch_reject_as_non_admin_returns_403(
    client: AsyncClient,
    make_teacher_user: Callable[..., Awaitable[tuple[dict[str, str], Teacher, User]]],
) -> None:
    teacher_headers, _, _ = await make_teacher_user(
        "reject-nonadmin@example.com", email="reject-nonadmin-teacher@example.com"
    )
    create_response = await client.post(
        "/teachers/me/change-requests", json={"first_name": "Nope"}, headers=teacher_headers
    )
    request_id = create_response.json()["id"]

    response = await client.patch(
        f"/teachers/change-requests/{request_id}/reject", headers=teacher_headers
    )

    assert response.status_code == 403
