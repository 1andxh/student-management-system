from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.exceptions import PermissionDeniedError, UnauthorizedError
from sms.core.security import decode_access_token
from sms.db.session import get_db
from sms.domains.auth.exceptions import InactiveUserError
from sms.domains.auth.models import User, UserRole
from sms.domains.auth.repository import UserRepository

# auto_error=False so a missing header comes back as our own 401
# (UnauthorizedError) instead of HTTPBearer's default 403.
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    session: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise UnauthorizedError("Missing bearer token.")

    user_id = decode_access_token(credentials.credentials)
    if user_id is None:
        raise UnauthorizedError("Invalid or expired token.")

    user = await UserRepository(session).get(user_id)
    if user is None:
        raise UnauthorizedError("Invalid or expired token.")
    if not user.is_active:
        raise InactiveUserError()

    return user


def require_role(*allowed_roles: UserRole):
    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise PermissionDeniedError()
        return current_user

    return dependency
