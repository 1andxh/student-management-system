from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest
from httpx import AsyncClient

from sms.domains.users.models import User, UserRole


@pytest.fixture
def make_role_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — admin by default, since
    make_user itself defaults to UserRole.ADMIN and most of the /users tests
    below exercise the admin-only path; pass role=UserRole.TEACHER or
    role=UserRole.STUDENT to exercise the "authenticated but not admin" 403
    path instead. Same pattern as make_manage_headers in the students
    integration tests."""

    async def _make_headers(role: UserRole = UserRole.ADMIN, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


def make_user_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "email": "grace@example.com",
        "password": "correct-horse",
        "role": "teacher",
    }
    payload.update(overrides)
    return payload


async def test_post_users_happy_path(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(email="admin1@example.com")

    response = await client.post(
        "/users", json=make_user_payload(email="grace@example.com"), headers=headers
    )

    assert response.status_code == 201
    body = response.json()
    assert "id" in body
    assert body["email"] == "grace@example.com"
    assert body["role"] == "teacher"
    assert body["is_active"] is True
    assert "hashed_password" not in body
    assert "password" not in body


async def test_post_users_duplicate_email_returns_409(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(email="admin2@example.com")
    await client.post(
        "/users", json=make_user_payload(email="dup@example.com"), headers=headers
    )

    response = await client.post(
        "/users", json=make_user_payload(email="dup@example.com"), headers=headers
    )

    assert response.status_code == 409


async def test_post_users_case_variant_duplicate_email_returns_409(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    # Regression test for the case-insensitive uniqueness fix (docs/adr/0010,
    # security review finding 1): "Dup@Example.com" and "dup@example.com"
    # must be treated as the same email, not two distinct accounts — a
    # bare case-sensitive UniqueConstraint would let both through and break
    # login for that address with an unhandled MultipleResultsFound.
    headers = await make_role_headers(email="admin3@example.com")
    await client.post(
        "/users", json=make_user_payload(email="CaseDup@Example.com"), headers=headers
    )

    response = await client.post(
        "/users", json=make_user_payload(email="casedup@example.com"), headers=headers
    )

    assert response.status_code == 409


async def test_post_users_short_password_returns_422(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(email="admin3@example.com")

    response = await client.post(
        "/users",
        json=make_user_payload(email="short-pw@example.com", password="short"),
        headers=headers,
    )

    assert response.status_code == 422


async def test_post_users_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.post("/users", json=make_user_payload())

    assert response.status_code == 401


async def test_post_users_as_teacher_returns_403(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(role=UserRole.TEACHER, email="teacher1@example.com")

    response = await client.post(
        "/users", json=make_user_payload(email="new-user@example.com"), headers=headers
    )

    assert response.status_code == 403


async def test_get_users_list(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    created = await make_user(email="listed@example.com")
    headers = await make_role_headers(email="admin4@example.com")

    response = await client.get("/users", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert str(created.id) in {u["id"] for u in body}


async def test_get_users_list_pagination_smoke(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    for i in range(3):
        await make_user(email=f"pgsmoke{i}@example.com")
    headers = await make_role_headers(email="admin-pg-smoke@example.com")

    response = await client.get("/users", params={"limit": 2, "offset": 0}, headers=headers)

    assert response.status_code == 200
    assert len(response.json()) == 2
    # Total includes the admin actor itself (created above the loop via
    # make_role_headers), not just the 3 looped users.
    assert int(response.headers["X-Total-Count"]) >= 3


async def test_get_users_as_non_admin_returns_403(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(role=UserRole.TEACHER, email="teacher2@example.com")

    response = await client.get("/users", headers=headers)

    assert response.status_code == 403


async def test_get_user_by_id_happy_path(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    target = await make_user(email="target@example.com")
    headers = await make_role_headers(email="admin5@example.com")

    response = await client.get(f"/users/{target.id}", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(target.id)
    assert body["email"] == "target@example.com"


async def test_get_user_by_id_missing_returns_404(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(email="admin6@example.com")

    response = await client.get(f"/users/{uuid4()}", headers=headers)

    assert response.status_code == 404


async def test_patch_user_is_active_happy_path(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    target = await make_user(email="to-deactivate@example.com", role=UserRole.TEACHER)
    headers = await make_role_headers(email="admin7@example.com")

    response = await client.patch(
        f"/users/{target.id}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(target.id)
    assert body["is_active"] is False
    assert body["role"] == "teacher"


async def test_patch_user_missing_returns_404(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(email="admin8@example.com")

    response = await client.patch(
        f"/users/{uuid4()}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 404


async def test_patch_user_as_non_admin_returns_403(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    target = await make_user(email="patch-target@example.com")
    headers = await make_role_headers(role=UserRole.TEACHER, email="teacher3@example.com")

    response = await client.patch(
        f"/users/{target.id}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 403


# --- super_admin tier protection (HTTP level) ---


async def test_patch_admin_target_as_admin_returns_403(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    target = await make_user(email="admin-target1@example.com", role=UserRole.ADMIN)
    headers = await make_role_headers(role=UserRole.ADMIN, email="plain-admin1@example.com")

    response = await client.patch(
        f"/users/{target.id}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 403


async def test_patch_admin_target_as_super_admin_returns_200(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    target = await make_user(email="admin-target2@example.com", role=UserRole.ADMIN)
    headers = await make_role_headers(
        role=UserRole.SUPER_ADMIN, email="super-admin1@example.com"
    )

    response = await client.patch(
        f"/users/{target.id}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 200
    body = response.json()
    assert body["is_active"] is False


async def test_post_users_super_admin_role_as_admin_returns_403(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(role=UserRole.ADMIN, email="plain-admin2@example.com")

    response = await client.post(
        "/users",
        json=make_user_payload(email="blocked-super@example.com", role="super_admin"),
        headers=headers,
    )

    assert response.status_code == 403


async def test_post_users_super_admin_role_as_super_admin_returns_201(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(
        role=UserRole.SUPER_ADMIN, email="super-admin2@example.com"
    )

    response = await client.post(
        "/users",
        json=make_user_payload(email="new-super@example.com", role="super_admin"),
        headers=headers,
    )

    assert response.status_code == 201
    body = response.json()
    assert body["role"] == "super_admin"


async def test_patch_last_active_super_admin_returns_409(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    # The only active super_admin in the system, acting on themselves —
    # deactivating them would leave zero.
    only_super_admin = await make_user(
        email="only-super-http@example.com", role=UserRole.SUPER_ADMIN
    )
    headers = auth_headers(only_super_admin)

    response = await client.patch(
        f"/users/{only_super_admin.id}", json={"is_active": False}, headers=headers
    )

    assert response.status_code == 409
