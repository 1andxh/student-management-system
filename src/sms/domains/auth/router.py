from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.config import settings
from sms.core.rate_limit import limiter
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user
from sms.domains.auth.exceptions import DisallowedOriginError, InvalidRefreshTokenError
from sms.domains.auth.repository import SessionRepository
from sms.domains.auth.schemas import (
    AccessTokenResponse,
    LoginRequest,
    PinLoginRequest,
    TokenPair,
)
from sms.domains.auth.service import AuthService
from sms.domains.students.repository import StudentRepository
from sms.domains.users.models import User
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(session), SessionRepository(session), StudentRepository(session))


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


# The refresh token travels only in this cookie, never in a JSON body
# (docs/adr/0027). Every attribute is doing a job:
# - HttpOnly: page JavaScript (including injected script) cannot read it.
# - SameSite=Strict: another site cannot make the browser attach it.
# - Path=/auth: it rides along only on auth requests, not every API call.
# - Secure: never sent over plain http (settings.refresh_cookie_secure).
# - No Max-Age/Expires, on purpose: a session cookie, so closing the browser
#   ends the login on a shared school computer. The server's own 30-day
#   absolute expiry (docs/adr/0009) still applies within a browser session.
REFRESH_COOKIE_NAME = "sms_refresh"
REFRESH_COOKIE_PATH = "/auth"


def _set_refresh_cookie(response: Response, refresh_token: str) -> None:
    response.set_cookie(
        key=REFRESH_COOKIE_NAME,
        value=refresh_token,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _clear_refresh_cookie(response: Response) -> None:
    # Attributes must match the ones the cookie was set with (path above
    # all) or the browser treats this as a different cookie and keeps the
    # original.
    response.delete_cookie(
        key=REFRESH_COOKIE_NAME,
        path=REFRESH_COOKIE_PATH,
        secure=settings.refresh_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def _refresh_cookie(request: Request) -> str | None:
    """The refresh cookie's value, read from the raw Cookie header rather
    than FastAPI's Cookie() parameter. That parser keeps the *last* of
    several same-named cookies, so a cookie planted at a broader path or
    from a sibling subdomain ("cookie tossing") could silently win over the
    real one. More than one value fails closed, with the same error as any
    other bad token."""
    values = []
    for part in request.headers.get("cookie", "").split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name == REFRESH_COOKIE_NAME:
            values.append(value)
    if len(values) > 1:
        raise InvalidRefreshTokenError()
    return values[0] if values else None


def _require_allowed_origin(request: Request) -> None:
    """CSRF guard for the routes the cookie alone authenticates. The browser
    attaches the cookie automatically, CORS only hides the *response* from a
    disallowed origin (the request still runs), and SameSite is drawn around
    the site, not the origin: another port on 127.0.0.1, or any subdomain
    of a shared parent domain, counts as same-site. Browsers send Origin on
    every POST, so a present Origin that isn't on the allowlist is a forged
    request. A missing Origin means a non-browser client (curl, tests),
    which no other site can drive, so it is allowed."""
    origin = request.headers.get("origin")
    if origin is not None and origin not in settings.cors_origins:
        raise DisallowedOriginError()


def _to_client(tokens: TokenPair, response: Response) -> AccessTokenResponse:
    """Splits the service's token pair at the HTTP boundary: refresh token
    into the cookie, access token into the body. The service never knows
    cookies exist."""
    _set_refresh_cookie(response, tokens.refresh_token)
    return AccessTokenResponse(access_token=tokens.access_token, token_type=tokens.token_type)


@router.post("/login", response_model=AccessTokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    response: Response,
    data: LoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AccessTokenResponse:
    user_agent, ip_address = _client_metadata(request)
    tokens = await service.login(data, user_agent=user_agent, ip_address=ip_address)
    return _to_client(tokens, response)


@router.post("/login-pin", response_model=AccessTokenResponse)
@limiter.limit("5/minute")
async def login_pin(
    request: Request,
    response: Response,
    data: PinLoginRequest,
    service: AuthService = Depends(get_auth_service),
) -> AccessTokenResponse:
    user_agent, ip_address = _client_metadata(request)
    tokens = await service.login_with_pin(data, user_agent=user_agent, ip_address=ip_address)
    return _to_client(tokens, response)


@router.post(
    "/refresh",
    response_model=AccessTokenResponse,
    dependencies=[Depends(_require_allowed_origin)],
)
@limiter.limit("20/minute")
async def refresh(
    request: Request,
    response: Response,
    refresh_token: str | None = Depends(_refresh_cookie),
    service: AuthService = Depends(get_auth_service),
) -> AccessTokenResponse:
    # A missing cookie gets the exact same error as an unknown, expired or
    # revoked one — the uniform-error rule from docs/adr/0008 and 0009.
    if not refresh_token:
        raise InvalidRefreshTokenError()
    user_agent, ip_address = _client_metadata(request)
    tokens = await service.refresh(refresh_token, user_agent=user_agent, ip_address=ip_address)
    return _to_client(tokens, response)


@router.post(
    "/logout",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(_require_allowed_origin)],
)
@limiter.limit("20/minute")
async def logout(
    request: Request,
    response: Response,
    refresh_token: str | None = Depends(_refresh_cookie),
    service: AuthService = Depends(get_auth_service),
) -> None:
    # Idempotent, as before (docs/adr/0009): no cookie or an unknown token
    # is a no-op. The cookie is cleared either way, so the browser never
    # holds on to a token the server no longer honours.
    if refresh_token:
        await service.logout(refresh_token)
    _clear_refresh_cookie(response)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
