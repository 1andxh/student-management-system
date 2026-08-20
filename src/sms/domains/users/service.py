from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.core.security import hash_password
from sms.domains.audit.service import AuditService
from sms.domains.users.exceptions import (
    AdminTierProtectedError,
    LastSuperAdminError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from sms.domains.users.models import User, UserRole
from sms.domains.users.repository import UserRepository
from sms.domains.users.schemas import UserCreate, UserUpdate

_ADMIN_TIER = (UserRole.ADMIN, UserRole.SUPER_ADMIN)


class UserService:
    """Admin CRUD on accounts — its own domain (see docs/adr/0012), not
    folded into auth, even though auth depends on this domain's model and
    repository for login/session lookups. Every mutation takes the
    acting_user, not just the target — admin-tier accounts get extra
    protection (see docs/adr/0011), and that protection depends on who's
    asking, not just what's being asked."""

    def __init__(self, repository: UserRepository, audit: AuditService) -> None:
        self._repository = repository
        self._audit = audit

    async def create(self, data: UserCreate, acting_user: User | None) -> User:
        # acting_user is None only for the bootstrap script creating the
        # very first account — there's no real actor yet. An explicit
        # None is safer than a fabricated, never-persisted User standing
        # in for "the system"; see docs/adr/0011 and the security review
        # that flagged the fabricated-actor pattern as a footgun.
        #
        # Creating a new super admin is itself admin-tier-protected —
        # granting the top trust tier is gated the same as modifying an
        # existing one (bootstrap's None bypasses this, deliberately).
        # Creating a *regular* admin stays open to any existing
        # admin/super admin, unchanged from before.
        if (
            data.role == UserRole.SUPER_ADMIN
            and acting_user is not None
            and acting_user.role != UserRole.SUPER_ADMIN
        ):
            raise AdminTierProtectedError()

        if await self._repository.get_by_email(data.email) is not None:
            raise UserAlreadyExistsError()

        user = User(
            email=data.email,
            hashed_password=hash_password(data.password),
            role=data.role,
            is_active=True,
        )
        # created and its audit entry must commit together, not as two
        # independently-durable writes — a fault in between would
        # otherwise leave the account created with no audit trail at all.
        # See docs/adr/0011.
        try:
            created = await self._repository.add(user, commit=False)
            await self._audit.record(
                actor_user_id=acting_user.id if acting_user is not None else None,
                action="user.created",
                target_user_id=created.id,
                after={
                    "email": created.email,
                    "role": created.role.value,
                    "is_active": created.is_active,
                },
                commit=False,
            )
            await self._repository.commit()
        except IntegrityError as exc:
            await self._repository.rollback()
            # Same check-then-create race guard as every other domain's
            # create() — see docs/adr/0004.
            raise UserAlreadyExistsError() from exc
        except Exception:
            await self._repository.rollback()
            raise

        return created

    async def get(self, user_id: UUID) -> User:
        user = await self._repository.get(user_id)
        if user is None:
            raise UserNotFoundError()
        return user

    async def list(self, *, limit: int, offset: int) -> tuple[list[User], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, user_id: UUID, data: UserUpdate, acting_user: User) -> User:
        user = await self.get(user_id)
        updates = data.model_dump(exclude_unset=True)

        new_role = updates.get("role", user.role)
        touches_admin_tier = user.role in _ADMIN_TIER or new_role in _ADMIN_TIER
        if touches_admin_tier and acting_user.role != UserRole.SUPER_ADMIN:
            raise AdminTierProtectedError()

        new_is_active = updates.get("is_active", user.is_active)
        losing_active_super_admin_status = (
            user.role == UserRole.SUPER_ADMIN
            and user.is_active
            and (new_role != UserRole.SUPER_ADMIN or not new_is_active)
        )
        if losing_active_super_admin_status:
            if await self._repository.count_active_super_admins() <= 1:
                raise LastSuperAdminError()

        before = {"role": user.role.value, "is_active": user.is_active}
        for field, value in updates.items():
            setattr(user, field, value)

        # See create()'s comment: the mutation and its audit entry must
        # commit together. This also matters for the FOR UPDATE lock
        # count_active_super_admins() may have just taken above — nothing
        # here may commit before the final commit below, or the lock's
        # protection against the concurrent-demotion race breaks silently.
        try:
            updated = await self._repository.add(user, commit=False)
            await self._audit.record(
                actor_user_id=acting_user.id,
                action="user.updated",
                target_user_id=updated.id,
                before=before,
                after={"role": updated.role.value, "is_active": updated.is_active},
                commit=False,
            )
            await self._repository.commit()
        except Exception:
            await self._repository.rollback()
            raise

        return updated
