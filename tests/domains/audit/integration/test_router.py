from collections.abc import Awaitable, Callable

import pytest
from httpx import AsyncClient

from sms.domains.users.models import User, UserRole


@pytest.fixture
def make_role_headers(
    make_user: Callable[..., Awaitable[User]], auth_headers: Callable[[User], dict[str, str]]
):
    """Auth header for a user with the given role — local to this file, same
    pattern as make_role_headers in tests/domains/auth/integration/test_router.py
    and make_manage_headers in tests/domains/students/integration/test_router.py.
    Unlike those, role has no default here: every /audit-log test below
    deliberately picks admin vs. super_admin, so a silent default would hide
    which one a given test actually means to exercise."""

    async def _make_headers(role: UserRole, **overrides: object) -> dict[str, str]:
        user = await make_user(role=role, **overrides)
        return auth_headers(user)

    return _make_headers


async def test_get_audit_log_as_super_admin_returns_200(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    headers = await make_role_headers(
        UserRole.SUPER_ADMIN, email="super-admin-audit1@example.com"
    )

    response = await client.get("/audit-log", headers=headers)

    assert response.status_code == 200
    assert isinstance(response.json(), list)


async def test_get_audit_log_as_admin_returns_403(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    # Audit visibility is super-admin-exclusive — a plain admin (who can
    # otherwise manage /users) is not allowed to read the audit log.
    headers = await make_role_headers(UserRole.ADMIN, email="admin-audit1@example.com")

    response = await client.get("/audit-log", headers=headers)

    assert response.status_code == 403


async def test_get_audit_log_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/audit-log")

    assert response.status_code == 401


async def test_post_users_then_get_audit_log_shows_user_created_entry(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    admin_headers = await make_role_headers(UserRole.ADMIN, email="admin-audit2@example.com")

    create_response = await client.post(
        "/users",
        json={
            "email": "audited-new-user@example.com",
            "password": "correct-horse",
            "role": "teacher",
        },
        headers=admin_headers,
    )
    assert create_response.status_code == 201
    created_user_id = create_response.json()["id"]

    super_admin_headers = await make_role_headers(
        UserRole.SUPER_ADMIN, email="super-admin-audit2@example.com"
    )
    response = await client.get("/audit-log", headers=super_admin_headers)

    assert response.status_code == 200
    entries = response.json()
    matching = [
        entry
        for entry in entries
        if entry["action"] == "user.created" and entry["target_user_id"] == created_user_id
    ]
    assert len(matching) == 1
