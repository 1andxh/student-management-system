from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from sms.domains.audit.models import AuditLog
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


async def test_get_audit_log_pagination_slices_and_sets_total_count_header(
    client: AsyncClient, make_role_headers: Callable[..., Awaitable[dict[str, str]]]
) -> None:
    admin_headers = await make_role_headers(UserRole.ADMIN, email="pg-admin1@example.com")
    for i in range(5):
        await client.post(
            "/users",
            json={
                "email": f"pg-audit-user{i}@example.com",
                "password": "correct-horse",
                "role": "teacher",
            },
            headers=admin_headers,
        )
    super_admin_headers = await make_role_headers(
        UserRole.SUPER_ADMIN, email="pg-super-admin1@example.com"
    )

    response = await client.get(
        "/audit-log", params={"limit": 2, "offset": 0}, headers=super_admin_headers
    )

    assert response.status_code == 200
    assert len(response.json()) == 2
    # At least the 5 user.created entries above; X-Total-Count reflects the
    # full filtered set, not just the 2-item slice.
    assert int(response.headers["X-Total-Count"]) >= 5


async def test_get_audit_log_newest_first_ordering(
    client: AsyncClient,
    db_session: AsyncSession,
    make_role_headers: Callable[..., Awaitable[dict[str, str]]],
) -> None:
    admin_headers = await make_role_headers(UserRole.ADMIN, email="ord-admin1@example.com")
    created_ids = []
    for i in range(3):
        response = await client.post(
            "/users",
            json={
                "email": f"ord-audit-user{i}@example.com",
                "password": "correct-horse",
                "role": "teacher",
            },
            headers=admin_headers,
        )
        created_ids.append(response.json()["id"])
    # Each user.created AuditLog entry is written server-side (not
    # client-settable via the request body), and db_session wraps this
    # whole test in one outer Postgres transaction (SAVEPOINT-based
    # rollback, see conftest.py) — func.now()/CURRENT_TIMESTAMP is
    # transaction-scoped, not statement-scoped, so all 3 entries would
    # otherwise get an identical server-default created_at. A direct
    # post-creation UPDATE gives them distinguishable timestamps.
    base = datetime(2024, 1, 1, tzinfo=timezone.utc)
    for i, target_user_id in enumerate(created_ids):
        await db_session.execute(
            update(AuditLog)
            .where(
                AuditLog.action == "user.created",
                AuditLog.target_user_id == UUID(target_user_id),
            )
            .values(created_at=base + timedelta(minutes=i))
        )
    await db_session.commit()
    super_admin_headers = await make_role_headers(
        UserRole.SUPER_ADMIN, email="ord-super-admin1@example.com"
    )

    response = await client.get("/audit-log", headers=super_admin_headers)

    assert response.status_code == 200
    entries = response.json()
    target_user_ids_in_order = [e["target_user_id"] for e in entries if e["target_user_id"] in created_ids]
    # Recorded in creation order (0, 1, 2) — must come back reversed
    # (newest-first: 2, 1, 0), matching the DB-level .order_by() added to
    # AuditLogRepository.list() (docs/adr/0011).
    assert target_user_ids_in_order == list(reversed(created_ids))


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
