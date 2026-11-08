from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update
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
    _assert_refresh_cookie_set(response)
    assert "refresh_token" not in body


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
    _assert_refresh_cookie_set(response)
    assert response.cookies[REFRESH_COOKIE] != body["access_token"]


async def test_post_login_does_not_expose_refresh_token_in_body(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # The whole point of the cookie (ADR 0027): if the raw token were also in
    # the JSON body, page JavaScript — including injected script — could
    # still read it, and the HttpOnly flag would protect nothing.
    await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))

    response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )

    assert "refresh_token" not in response.json()


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
    await _login(client, make_user)
    original_refresh_token = client.cookies[REFRESH_COOKIE]

    # No body: the browser (here, httpx's cookie jar) sends the cookie itself.
    response = await client.post("/auth/refresh")

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert "refresh_token" not in body
    _assert_refresh_cookie_set(response)
    assert response.cookies[REFRESH_COOKIE] != original_refresh_token


async def test_post_refresh_without_cookie_returns_401(client: AsyncClient) -> None:
    response = await client.post("/auth/refresh")

    assert response.status_code == 401


async def test_post_refresh_with_unknown_token_returns_401(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/refresh", headers=_cookie_header("this-token-was-never-issued")
    )

    assert response.status_code == 401


async def test_post_refresh_with_previous_token_within_grace_succeeds(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # The double-reload case (ADR 0031): the server rotated, but the browser
    # threw the response (and its new cookie) away, so it presents the token
    # the server just replaced. Inside the grace window that must still work,
    # and what it returns must be a token that works from then on.
    await _login(client, make_user)
    previous = client.cookies[REFRESH_COOKIE]
    await client.post("/auth/refresh")  # rotates; this response is "lost"

    client.cookies.clear()
    response = await client.post("/auth/refresh", headers=_cookie_header(previous))

    assert response.status_code == 200
    _assert_refresh_cookie_set(response)
    client.cookies.clear()
    follow_up = await client.post("/auth/refresh", headers=_cookie_header(response.cookies[REFRESH_COOKIE]))
    assert follow_up.status_code == 200


async def test_replaying_the_previous_token_returns_the_same_next_token(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # Deterministic rotation (ADR 0031): a replay doesn't mint a *second*
    # successor that would retire the first — it gets the same one back.
    await _login(client, make_user)
    previous = client.cookies[REFRESH_COOKIE]
    first = await client.post("/auth/refresh")
    next_token = first.cookies[REFRESH_COOKIE]

    client.cookies.clear()
    replay = await client.post("/auth/refresh", headers=_cookie_header(previous))

    assert replay.status_code == 200
    assert replay.cookies[REFRESH_COOKIE] == next_token


async def test_post_logout_is_limited_generously(client: AsyncClient) -> None:
    # 120/minute, not the login routes' 5 or refresh's 20: logout can only
    # end sessions, and a school behind one IP must be able to sign a whole
    # class out at a bell without anyone hitting the limit (security review
    # F3 #1). Still limited, to blunt a flood.
    for _ in range(120):
        assert (await client.post("/auth/logout")).status_code == 204

    assert (await client.post("/auth/logout")).status_code == 429


async def test_post_refresh_with_previous_token_after_grace_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], db_session: AsyncSession
) -> None:
    # Rotation still invalidates the old token over HTTP (ADR 0009) — once
    # the grace window has passed.
    await _login(client, make_user)
    previous = client.cookies[REFRESH_COOKIE]
    await client.post("/auth/refresh")
    await _age_last_rotation(db_session, seconds=settings.refresh_grace_seconds + 1)

    client.cookies.clear()
    response = await client.post("/auth/refresh", headers=_cookie_header(previous))

    assert response.status_code == 401


async def test_grace_use_does_not_extend_the_window(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], db_session: AsyncSession
) -> None:
    # The window is anchored to the rotation that retired the token. If
    # using the previous token moved it, a stolen previous token could keep
    # itself alive indefinitely by refreshing every 29 seconds.
    await _login(client, make_user)
    previous = client.cookies[REFRESH_COOKIE]
    await client.post("/auth/refresh")
    rotated_at_before = await _rotated_at(db_session)

    client.cookies.clear()
    response = await client.post("/auth/refresh", headers=_cookie_header(previous))

    assert response.status_code == 200
    assert await _rotated_at(db_session) == rotated_at_before


async def test_post_logout_with_previous_token_within_grace_revokes_session(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # Logging out with the cookie the browser actually holds (the "lost
    # response" one) must end the session, not silently leave it alive
    # under a token nobody has.
    await _login(client, make_user)
    previous = client.cookies[REFRESH_COOKIE]
    await client.post("/auth/refresh")
    current = client.cookies[REFRESH_COOKIE]

    client.cookies.clear()
    logout = await client.post("/auth/logout", headers=_cookie_header(previous))
    assert logout.status_code == 204

    response = await client.post("/auth/refresh", headers=_cookie_header(current))
    assert response.status_code == 401


async def test_post_refresh_with_deactivated_user_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]], db_session: AsyncSession
) -> None:
    # A refresh token issued while the user was active must stop working
    # the moment the account is deactivated — refresh() re-checks the user,
    # not just the session, so this doesn't wait for the token to expire.
    user = await _login(client, make_user)

    user.is_active = False
    db_session.add(user)
    await db_session.commit()

    response = await client.post("/auth/refresh")

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
    await _login(client, make_user)
    refresh_token = client.cookies[REFRESH_COOKIE]

    logout_response = await client.post("/auth/logout")

    assert logout_response.status_code == 204
    _assert_refresh_cookie_cleared(logout_response)

    client.cookies.clear()
    refresh_response = await client.post("/auth/refresh", headers=_cookie_header(refresh_token))

    assert refresh_response.status_code == 401


async def test_post_logout_with_unknown_token_returns_204(client: AsyncClient) -> None:
    # Idempotent by design: logging out with an unknown/already-revoked
    # token is a no-op, not an error.
    response = await client.post(
        "/auth/logout", headers=_cookie_header("this-token-was-never-issued")
    )

    assert response.status_code == 204
    _assert_refresh_cookie_cleared(response)


async def test_post_logout_without_cookie_returns_204(client: AsyncClient) -> None:
    # Same idempotency as an unknown token: "ensure no session is active
    # here" is already true, so there is nothing to report as an error.
    response = await client.post("/auth/logout")

    assert response.status_code == 204


async def test_cors_preflight_allows_credentials_for_frontend_origin(
    client: AsyncClient,
) -> None:
    # Without Access-Control-Allow-Credentials the browser silently drops the
    # Set-Cookie from a cross-origin login response, and never attaches the
    # cookie to /auth/refresh — so the frontend can't log in at all.
    response = await client.options(
        "/auth/refresh",
        headers={
            "Origin": "http://127.0.0.1:5173",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-credentials"] == "true"
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:5173"


async def test_post_refresh_from_frontend_origin_succeeds(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # The real SPA case: the browser sends Origin on every POST.
    await _login(client, make_user)

    response = await client.post("/auth/refresh", headers={"Origin": FRONTEND_ORIGIN})

    assert response.status_code == 200


async def test_post_refresh_from_disallowed_origin_returns_403_and_does_not_rotate(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # CSRF: the cookie is attached automatically, and CORS only hides the
    # *response* from a disallowed origin — the request itself still runs.
    # Another port on 127.0.0.1 counts as the same *site*, so SameSite
    # doesn't stop it either. The Origin check is what does.
    await _login(client, make_user)
    refresh_token = client.cookies[REFRESH_COOKIE]

    response = await client.post(
        "/auth/refresh", headers={"Origin": "http://127.0.0.1:3000"}
    )

    assert response.status_code == 403
    client.cookies.clear()
    still_valid = await client.post("/auth/refresh", headers=_cookie_header(refresh_token))
    assert still_valid.status_code == 200


async def test_post_logout_from_disallowed_origin_returns_403_and_keeps_session(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    await _login(client, make_user)
    refresh_token = client.cookies[REFRESH_COOKIE]

    response = await client.post("/auth/logout", headers={"Origin": "http://127.0.0.1:3000"})

    assert response.status_code == 403
    client.cookies.clear()
    still_valid = await client.post("/auth/refresh", headers=_cookie_header(refresh_token))
    assert still_valid.status_code == 200


async def test_post_refresh_with_duplicate_cookies_returns_401(
    client: AsyncClient, make_user: Callable[..., Awaitable[User]]
) -> None:
    # Cookie tossing: a cookie planted at a broader path (or from a sibling
    # subdomain) arrives *alongside* the real one, and the framework would
    # silently keep the last. Two values means we can't know which session
    # the caller means, so fail closed rather than guess.
    await _login(client, make_user)
    real_token = client.cookies[REFRESH_COOKIE]
    client.cookies.clear()

    # Real token last — the position the framework would pick — so this
    # can only be a 401 because of the duplicate check, not because the
    # planted value happens to be invalid.
    response = await client.post(
        "/auth/refresh",
        headers={"Cookie": f"{REFRESH_COOKIE}=attacker-planted; {REFRESH_COOKIE}={real_token}"},
    )

    assert response.status_code == 401


async def test_post_refresh_failure_sets_no_cookie(client: AsyncClient) -> None:
    response = await client.post(
        "/auth/refresh", headers=_cookie_header("this-token-was-never-issued")
    )

    assert response.status_code == 401
    assert response.headers.get_list("set-cookie") == []


async def test_cors_preflight_from_disallowed_origin_gets_no_allow_origin(
    client: AsyncClient,
) -> None:
    response = await client.options(
        "/auth/refresh",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers


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


REFRESH_COOKIE = "sms_refresh"
FRONTEND_ORIGIN = "http://127.0.0.1:5173"


async def _login(client: AsyncClient, make_user: Callable[..., Awaitable[User]]) -> User:
    """Logs a fresh user in over HTTP, leaving the refresh cookie in the
    client's cookie jar — the same state a browser is in after login."""
    user = await make_user(email="ada@example.com", **_hashed("s3cr3t-pw"))
    response = await client.post(
        "/auth/login", json={"email": "ada@example.com", "password": "s3cr3t-pw"}
    )
    assert response.status_code == 200, response.text
    return user


def _cookie_header(refresh_token: str) -> dict[str, str]:
    """Presents a specific refresh token, bypassing the cookie jar — for
    replaying an old or made-up token. Callers clear the jar first so it
    can't contribute a second, conflicting value."""
    return {"Cookie": f"{REFRESH_COOKIE}={refresh_token}"}


def _refresh_set_cookie(response) -> str:
    headers = [
        h for h in response.headers.get_list("set-cookie") if h.startswith(f"{REFRESH_COOKIE}=")
    ]
    assert len(headers) == 1, response.headers.get_list("set-cookie")
    return headers[0].lower()


def _assert_refresh_cookie_set(response) -> None:
    """Each attribute is load-bearing, so each is asserted: HttpOnly keeps
    it away from page JavaScript, SameSite=Strict keeps other sites from
    making the browser send it, Path=/auth keeps it off every other API
    request, Secure keeps it off plain http. And it has *no* Max-Age or
    Expires: it is a session cookie, so closing the browser ends the login
    on a shared computer (ADR 0027) — the server's own 30-day absolute
    expiry (ADR 0009) still applies on top."""
    header = _refresh_set_cookie(response)
    assert response.cookies[REFRESH_COOKIE]
    assert "httponly" in header
    assert "samesite=strict" in header
    assert "path=/auth" in header
    assert "secure" in header
    assert "max-age" not in header
    assert "expires" not in header


def _assert_refresh_cookie_cleared(response) -> None:
    header = _refresh_set_cookie(response)
    assert "max-age=0" in header
    assert "path=/auth" in header


async def _age_last_rotation(db_session: AsyncSession, seconds: int) -> None:
    """Moves every session's last rotation into the past: the grace window
    tested without sleeping through it."""
    await db_session.execute(
        update(Session).values(rotated_at=datetime.now(timezone.utc) - timedelta(seconds=seconds))
    )
    await db_session.commit()


async def _rotated_at(db_session: AsyncSession) -> datetime | None:
    result = await db_session.execute(
        select(Session.rotated_at).order_by(Session.created_at.desc()).execution_options(populate_existing=True)
    )
    return result.scalars().first()
