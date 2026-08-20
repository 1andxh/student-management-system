"""Users domain — the User model, admin CRUD on accounts, admin-tier
protections. Dependency-free at its core (models/schemas/repository/service
import nothing from other domains); only its router reaches into auth for
RBAC gating, same as every other domain's router. auth depends on this
domain for the User model/repository, not the other way around. See
docs/adr/0012."""

from sms.domains.users.exceptions import (
    AdminTierProtectedError,
    LastSuperAdminError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from sms.domains.users.models import User, UserRole
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserCreate, UserRead, UserUpdate
from sms.domains.users.service import UserService

__all__ = [
    "AdminTierProtectedError",
    "LastSuperAdminError",
    "UserAlreadyExistsError",
    "UserNotFoundError",
    "User",
    "UserRole",
    "UserRepository",
    "UserCreate",
    "UserRead",
    "UserUpdate",
    "UserService",
]
