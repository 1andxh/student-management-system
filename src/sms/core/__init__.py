"""Cross-cutting, domain-agnostic building blocks — config, the exception
hierarchy every domain raises against, the generic repository abstraction,
logging/middleware, and JWT/password primitives. Nothing here imports from
sms.domains; domains depend on core, never the reverse."""

from sms.core.config import settings
from sms.core.exception_handlers import register_exception_handlers
from sms.core.exceptions import (
    AppException,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
    UnauthorizedError,
)
from sms.core.logging import configure_logging
from sms.core.middleware import RequestLoggingMiddleware
from sms.core.rate_limit import limiter
from sms.core.repository import AbstractRepository
from sms.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_token,
    verify_password,
)

__all__ = [
    "settings",
    "register_exception_handlers",
    "AppException",
    "ConflictError",
    "NotFoundError",
    "PermissionDeniedError",
    "UnauthorizedError",
    "configure_logging",
    "RequestLoggingMiddleware",
    "limiter",
    "AbstractRepository",
    "DUMMY_PASSWORD_HASH",
    "create_access_token",
    "decode_access_token",
    "generate_refresh_token",
    "hash_password",
    "hash_token",
    "verify_password",
]
