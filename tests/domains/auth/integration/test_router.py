from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.config import settings
from sms.domains.auth.models import Session
from sms.domains.users.models import User, UserRole


@pytest.fixture
def issue_student_credentials(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
):
    """Creates a Student over HTTP (POST /students, auto-generated
    student_number) and issues it login credentials (POST
    /students/{id}/credentials), returning (student_number, pin) — the pair
    /auth/login-pin tests need. Goes through the real admin-only endpoints
    rather than inserting directly via db_session, since the point of these
    tests is proving the PIN issued by that endpoint actually works against
    login-pin end to end."""

    async def _issue(email: str = "pin-e2e@example.com") -> tuple[str, str]:
        admin = await make_user(role=UserRole.ADMIN, email=f"admin-{email}")
        admin_headers = auth_headers(admin)

        create_response = await client.post(
            "/students",
            json={
                "first_name": "Ada",
                "last_name": "Lovelace",
                "date_of_birth": "2010-01-01",
                "email": email,
                "guardian_name": "Byron Lovelace",
                "guardian_phone": "+1-555-0100",
            },
            headers=admin_headers,
        )
        assert create_response.status_code == 201, create_response.text
        student_id = create_response.json()["id"]
        student_number = create_response.json()["student_number"]

        creds_response = await client.post(
            f"/students/{student_id}/credentials", headers=admin_headers
        )
        assert creds_response.status_code == 200, creds_response.text
        pin = creds_response.json()["pin"]

        return student_number, pin

    return _issue


async def test_post_login_pin_happy_path(
    client: AsyncClient,
    issue_student_credentials: Callable[..., Awaitable[tuple[str, str]]],
) -> None:
    student_number, pin = await issue_student_credentials("pin-happy@example.com")

    response = await client.post(
        "/auth/login-pin", json={"student_number": student_number, "pin": pin}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["refresh_token"]
    assert body["refresh_token"] != body["access_token"]


async def test_post_login_pin_wrong_pin_returns_401(
    client: AsyncClient,
    issue_student_credentials: Callable[..., Awaitable[tuple[str, str]]],
) -> None:
    student_number, _pin = await issue_student_credentials("pin-wrong@example.com")

    response = await client.post(
        "/auth/login-pin", json={"student_number": student_number, "pin": "000000"}
    )

    assert response.status_code == 401


async def test_post_login_pin_unknown_student_number_returns_401(
    client: AsyncClient,
) -> None:
    response = await client.post(
        "/auth/login-pin", json={"student_number": "NO-SUCH-STUDENT", "pin": "123456"}
    )

    assert response.status_code == 401


async def test_post_login_pin_rate_limited_after_five_attempts(
    client: AsyncClient,
    issue_student_credentials: Callable[..., Awaitable[tuple[str, str]]],
) -> None:
    student_number, _pin = await issue_student_credentials("pin-ratelimit@example.com")
    payload = {"student_number": student_number, "pin": "000000"}

    for _ in range(5):
        response = await client.post("/auth/login-pin", json=payload)
        assert response.status_code == 401

    sixth = await client.post("/auth/login-pin", json=payload)

    assert sixth.status_code == 429


async def test_post_login_happy_path(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))

    response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )

    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["access_token"]
    assert body["token_type"] == "bearer"
    assert body["refresh_token"]
    assert body["refresh_token"] != body["access_token"]


async def test_post_login_wrong_password_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))

    response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "not-the-password"}
    )

    assert response.status_code == 401


async def test_post_login_rate_limited_after_five_attempts(client: AsyncClient) -> None:
    payload = {"email": "nobody@example.com", "password": "whatever"}

    for _ in range(5):
        response = await client.post("/auth/login", json=payload)
        assert response.status_code == 401

    sixth = await client.post("/auth/login", json=payload)

    assert sixth.status_code == 429


async def test_post_login_unknown_email_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/login", json={"email": "nobody@example.com", "password": "whatever"}
    )

    assert response.status_code == 401


async def test_post_login_inactive_user_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    await make_user(email="inactive@example.com", is_active=False, **_hashed("s3cr3t-pw"))

    response = await client.post(
        "/auth/login", json={"email": "inactive@example.com", "password": "s3cr3t-pw"}
    )

    assert response.status_code == 401


async def test_post_refresh_happy_path(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))
    login_response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )
    original_refresh_token = login_response.json()["refresh_token"]

    response = await client.post("/auth/refresh", json={"refresh_token": original_refresh_token})

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["refresh_token"]
    assert body["refresh_token"] != original_refresh_token


async def test_post_refresh_with_unknown_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/refresh", json={"refresh_token": "this-token-was-never-issued"}
    )

    assert response.status_code == 401


async def test_post_refresh_with_already_rotated_token_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # Proves rotation actually invalidates the old raw token over HTTP, not
    # just at the service layer — the first refresh below rotates the
    # session onto a new token, so re-presenting the original one must fail.
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))
    login_response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )
    original_refresh_token = login_response.json()["refresh_token"]
    await client.post("/auth/refresh", json={"refresh_token": original_refresh_token})

    response = await client.post("/auth/refresh", json={"refresh_token": original_refresh_token})

    assert response.status_code == 401


async def test_post_refresh_with_deactivated_user_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], db_session: AsyncSession
) -> None:
    # A refresh token issued while the user was active must stop working
    # the moment the account is deactivated — refresh() re-checks the user,
    # not just the session, so this doesn't wait for the token to expire.
    user = await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))
    login_response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )
    refresh_token = login_response.json()["refresh_token"]

    user.is_active = False
    db_session.add(user)
    await db_session.commit()

    response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert response.status_code == 401


async def test_post_login_records_user_agent_and_ip(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], db_session: AsyncSession
) -> None:
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))

    await client.post(
        "/auth/login",
        json={"email": "ada@example.com", "password": "s3cr3t-pw"},
        headers={"User-Agent": "pytest-integration-client/1.0"},
    )

    result = await db_session.execute(select(Session).order_by(Session.created_at.desc()))
    session = result.scalars().first()
    assert session is not None
    # ASGITransport doesn't simulate a real client IP for in-process test
    # requests, so ip_address isn't asserted here — user_agent (from a real
    # header) is the meaningful part of this test.
    assert session.user_agent == "pytest-integration-client/1.0"


async def test_post_logout_happy_path(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))
    login_response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )
    refresh_token = login_response.json()["refresh_token"]

    logout_response = await client.post("/auth/logout", json={"refresh_token": refresh_token})

    assert logout_response.status_code == 204

    refresh_response = await client.post("/auth/refresh", json={"refresh_token": refresh_token})

    assert refresh_response.status_code == 401


async def test_post_logout_with_unknown_token_returns_204(client: AsyncClient) -> None:
    # Idempotent by design: logging out with an unknown/already-revoked
    # token is a no-op, not an error.
    response = await client.post(
        "/auth/logout", json={"refresh_token": "this-token-was-never-issued"}
    )

    assert response.status_code == 204


async def test_get_me_with_valid_token(
    client: AsyncClient,
    make_user: Callable[..., Awaitable[User]],
    auth_headers: Callable[[User], dict[str, str]],
) -> None:
    user = await make_user(email="ada@example.com")

    response = await client.get("/auth/me", headers=auth_headers(user))

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(user.id)
    assert body["email"] == "ada@example.com"


async def test_get_me_without_token_returns_401(client: AsyncClient) -> None:
    response = await client.get("/auth/me")

    assert response.status_code == 401


async def test_get_me_with_invalid_token_returns_401(client: AsyncClient) -> None:
    response = await client.get(
        "/auth/me", headers={"Authorization": "Bearer this-is-not-a-real-jwt"}
    )

    assert response.status_code == 401


async def test_get_me_with_expired_token_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    user = await make_user(email="ada@example.com")

    response = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {_expired_token(user.id)}"}
    )

    assert response.status_code == 401


def _expired_token(subject: UUID) -> str:
    """Builds a JWT with a past expiry using the app's real secret/algorithm,
    to exercise decode_access_token's expiry handling without waiting for a
    real token to expire."""
    payload = {"sub": str(subject), "exp": datetime.now(timezone.utc) - timedelta(minutes=1)}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _hashed(plaintext_password: str) -> dict[str, object]:
    """Builds the kwarg make_user expects for a known plaintext password,
    without pulling sms.core.security's hashing import into every test —
    hash_password isn't guaranteed to be cheap, and only login tests that
    need to authenticate against a *specific* password need it."""
    from sms.core.security import hash_password

    return {"hashed_password": hash_password(plaintext_password)}
