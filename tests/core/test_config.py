import pytest
from pydantic import ValidationError

from sms.core.config import Settings

_REQUIRED = {
    "database_url": "postgresql+asyncpg://u:p@h/db",
    "database_url_test": "postgresql+asyncpg://u:p@h/db_test",
    "jwt_secret_key": "x" * 40,
}


def test_cors_origins_rejects_wildcard() -> None:
    # With allow_credentials=True, Starlette answers "*" by echoing back
    # *any* request's Origin — every site becomes a credentialed origin.
    # The quick "make CORS work" edit must fail startup, not ship.
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        Settings(**_REQUIRED, cors_origins=["*"])


def test_insecure_refresh_cookie_rejected_outside_local() -> None:
    with pytest.raises(ValidationError, match="REFRESH_COOKIE_SECURE"):
        Settings(**_REQUIRED, env="production", refresh_cookie_secure=False)


def test_insecure_refresh_cookie_allowed_locally() -> None:
    # Escape hatch for a browser that refuses Secure cookies on
    # http://127.0.0.1 during local dev.
    settings = Settings(**_REQUIRED, env="local", refresh_cookie_secure=False)

    assert settings.refresh_cookie_secure is False


@pytest.mark.parametrize("seconds", [-1, 121])
def test_refresh_grace_seconds_is_bounded(seconds: int) -> None:
    # The grace window bounds how long a retired refresh token keeps working
    # (ADR 0031). A large value quietly undoes rotation, so a misconfigured
    # one fails startup instead.
    with pytest.raises(ValidationError, match="REFRESH_GRACE_SECONDS"):
        Settings(**_REQUIRED, refresh_grace_seconds=seconds)
