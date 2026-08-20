from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.repository import AbstractRepository
from sms.domains.users.models import User, UserRole


class UserRepository(AbstractRepository[User]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: User, *, commit: bool = True) -> User:
        self._session.add(entity)
        try:
            if commit:
                await self._session.commit()
            else:
                # Flush (not commit) still executes the INSERT/UPDATE and
                # populates server-generated defaults (id, created_at) via
                # RETURNING, without ending the transaction — used when the
                # caller needs this write to commit atomically together with
                # another repository's write (see UserService.create/update
                # and the security review in docs/adr/0011).
                await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def commit(self) -> None:
        await self._session.commit()

    async def rollback(self) -> None:
        await self._session.rollback()

    async def get(self, entity_id: UUID) -> User | None:
        return await self._session.get(User, entity_id)

    async def list(self) -> list[User]:
        result = await self._session.execute(select(User))
        return list(result.scalars().all())

    async def remove(self, entity: User) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_email(self, email: str) -> User | None:
        # Case-insensitive: email storage isn't normalized on write yet
        # (no user-creation endpoint exists to normalize at), but lookups
        # must not depend on write-side normalization catching up later.
        result = await self._session.execute(
            select(User).where(func.lower(User.email) == email.lower())
        )
        return result.scalar_one_or_none()

    async def count_active_super_admins(self) -> int:
        """SELECT ... FOR UPDATE, not a plain count — the caller uses this
        to decide whether a change would leave zero active super admins, so
        it must block a concurrent equivalent check on the same rows rather
        than both reading a stale pre-commit count (two concurrent
        demotions of two different super admins could otherwise both see
        "2 active" and both proceed, zeroing out the tier). The lock is
        held until the caller's subsequent commit — see
        UserService.update, which must not commit anything else on this
        session between calling this and its own final commit, or the
        lock's effectiveness silently breaks. See docs/adr/0011."""
        result = await self._session.execute(
            select(User.id)
            .where(User.role == UserRole.SUPER_ADMIN, User.is_active.is_(True))
            .with_for_update()
        )
        return len(result.all())
