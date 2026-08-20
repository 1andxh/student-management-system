"""Auth domain — sessions, login/refresh/logout, RBAC dependencies. Owns no
account data itself: it depends on sms.domains.users for the User model and
repository (see docs/adr/0012). Every other domain depends on this one for
authentication/authorization (see docs/adr/0006)."""

from sms.domains.auth.dependencies import get_current_user, require_role
from sms.domains.auth.exceptions import (
    InactiveUserError,
    InvalidCredentialsError,
    InvalidRefreshTokenError,
)
from sms.domains.auth.models import Session
from sms.domains.auth.repository import SessionRepository
from sms.domains.auth.schemas import LoginRequest, LogoutRequest, RefreshRequest, TokenResponse
from sms.domains.auth.service import AuthService

__all__ = [
    "get_current_user",
    "require_role",
    "InactiveUserError",
    "InvalidCredentialsError",
    "InvalidRefreshTokenError",
    "Session",
    "SessionRepository",
    "LoginRequest",
    "LogoutRequest",
    "RefreshRequest",
    "TokenResponse",
    "AuthService",
]
