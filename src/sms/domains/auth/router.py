from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.rate_limit import limiter
from sms.db.session import get_db
from sms.domains.auth.dependencies import get_current_user
from sms.domains.auth.repository import SessionRepository
from sms.domains.auth.schemas import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from sms.domains.auth.service import AuthService
from sms.domains.users.models import User
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserRead

router = APIRouter(prefix="/auth", tags=["auth"])


def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(UserRepository(session), SessionRepository(session))


def _client_metadata(request: Request) -> tuple[str | None, str | None]:
    user_agent = request.headers.get("user-agent")
    ip_address = request.client.host if request.client else None
    return user_agent, ip_address


@router.post("/login", response_model=TokenResponse)
@limiter.limit("5/minute")
async def login(
    request: Request, data: LoginRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    user_agent, ip_address = _client_metadata(request)
    return await service.login(data, user_agent=user_agent, ip_address=ip_address)


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("20/minute")
async def refresh(
    request: Request, data: RefreshRequest, service: AuthService = Depends(get_auth_service)
) -> TokenResponse:
    user_agent, ip_address = _client_metadata(request)
    return await service.refresh(data.refresh_token, user_agent=user_agent, ip_address=ip_address)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("20/minute")
async def logout(
    request: Request, data: LogoutRequest, service: AuthService = Depends(get_auth_service)
) -> None:
    await service.logout(data.refresh_token)


@router.get("/me", response_model=UserRead)
async def read_current_user(current_user: User = Depends(get_current_user)) -> User:
    return current_user
