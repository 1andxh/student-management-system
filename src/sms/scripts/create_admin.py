"""One-off bootstrap for the first super admin account.

There's no API endpoint for this on purpose — an admin-gated "create user"
endpoint can't create the very first account, and an open "first user
becomes admin" registration route is its own security surface this project
isn't building. Run once, out of band:

    docker compose exec api uv run python -m sms.scripts.create_admin

Reads ADMIN_EMAIL / ADMIN_PASSWORD from the environment rather than argv, so
the password never ends up in shell history. Goes through UserCreate and
UserService.create — the same validation (email format, password length)
and uniqueness-race handling (see docs/adr/0004) as the admin-facing
POST /users endpoint, rather than re-implementing those checks here.

Creates a SUPER_ADMIN, not a plain ADMIN — this is the account every other
admin-tier account traces back to (see docs/adr/0011), so it needs the
authority to create/manage other admins from the start.
"""

import asyncio
import os
import sys

from pydantic import ValidationError

from sms.db.session import async_session_factory
from sms.domains.audit.repository import AuditLogRepository
from sms.domains.audit.service import AuditService
from sms.domains.users.exceptions import UserAlreadyExistsError
from sms.domains.users.models import UserRole
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserCreate
from sms.domains.users.service import UserService


async def main() -> None:
    email = os.environ.get("ADMIN_EMAIL", "")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not email or not password:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD environment variables.", file=sys.stderr)
        sys.exit(1)

    try:
        data = UserCreate(email=email, password=password, role=UserRole.SUPER_ADMIN)
    except ValidationError as exc:
        print(f"Invalid ADMIN_EMAIL/ADMIN_PASSWORD: {exc}", file=sys.stderr)
        sys.exit(1)

    async with async_session_factory() as session:
        service = UserService(UserRepository(session), AuditService(AuditLogRepository(session)))
        try:
            # acting_user=None — bootstrapping the very first account means
            # there's no real user yet to act as. UserService.create()
            # treats None as "the system": it's allowed to create a
            # SUPER_ADMIN (that's this script's only purpose), and the
            # resulting audit entry records actor_user_id=None rather than
            # a fabricated identity standing in for a real actor.
            user = await service.create(data, acting_user=None)
        except UserAlreadyExistsError:
            print(f"A user with email {data.email!r} already exists.", file=sys.stderr)
            sys.exit(1)

        print(f"Created super admin user {user.email!r}.")


if __name__ == "__main__":
    asyncio.run(main())
