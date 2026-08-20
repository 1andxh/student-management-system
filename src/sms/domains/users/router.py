from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.rate_limit import limiter
from sms.db.session import get_db
from sms.domains.audit.repository import AuditLogRepository
from sms.domains.audit.service import AuditService
from sms.domains.auth.dependencies import require_role
from sms.domains.users.models import User, UserRole
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserCreate, UserRead, UserUpdate
from sms.domains.users.service import UserService

# Resource CRUD, not an auth-flow action — its own domain (see
# docs/adr/0012), not nested under /auth. Admin-only: managing login
# accounts/roles is a different trust level than managing academic records
# (Students allows admin+teacher; this doesn't).
router = APIRouter(prefix="/users", tags=["users"])
_admin_only = require_role(UserRole.ADMIN)


def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(UserRepository(session), AuditService(AuditLogRepository(session)))


@router.post("", response_model=UserRead, status_code=status.HTTP_201_CREATED)
@limiter.limit("30/minute")
async def create_user(
    request: Request,
    data: UserCreate,
    acting_user: User = Depends(_admin_only),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.create(data, acting_user)


@router.get("", response_model=list[UserRead], dependencies=[Depends(_admin_only)])
@limiter.limit("30/minute")
async def list_users(
    request: Request, service: UserService = Depends(get_user_service)
) -> list[User]:
    return await service.list()


@router.get("/{user_id}", response_model=UserRead, dependencies=[Depends(_admin_only)])
@limiter.limit("30/minute")
async def get_user(
    request: Request, user_id: UUID, service: UserService = Depends(get_user_service)
) -> User:
    return await service.get(user_id)


@router.patch("/{user_id}", response_model=UserRead)
@limiter.limit("30/minute")
async def update_user(
    request: Request,
    user_id: UUID,
    data: UserUpdate,
    acting_user: User = Depends(_admin_only),
    service: UserService = Depends(get_user_service),
) -> User:
    return await service.update(user_id, data, acting_user)
