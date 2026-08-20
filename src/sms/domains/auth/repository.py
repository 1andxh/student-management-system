from datetime import datetime
from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.repository import AbstractRepository
from sms.domains.auth.models import Session


class SessionRepository(AbstractRepository[Session]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: Session) -> Session:
        self._session.add(entity)
        try:
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> Session | None:
        return await self._session.get(Session, entity_id)

    async def list(self) -> list[Session]:
        result = await self._session.execute(select(Session))
        return list(result.scalars().all())

    async def remove(self, entity: Session) -> None:
        await self._session.delete(entity)
        await self._session.commit()

    async def get_by_token_hash(self, refresh_token_hash: str) -> Session | None:
        result = await self._session.execute(
            select(Session).where(Session.refresh_token_hash == refresh_token_hash)
        )
        return result.scalar_one_or_none()

    async def rotate(
        self,
        old_hash: str,
        new_hash: str,
        now: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """Atomic compare-and-swap on the hash — a plain read-then-write
        here would let two concurrent refresh() calls with the same token
        both pass validation and each mint a different "next" token, with
        the loser silently overwritten. Returns False if old_hash was
        already rotated or revoked by someone else first; the caller should
        treat that identically to any other invalid token.
        user_agent/ip_address ride along in the same statement rather than a
        separate update — mutating the in-memory ORM object after this call
        wouldn't persist anything, since the UPDATE above bypasses it."""
        result = await self._session.execute(
            update(Session)
            .where(Session.refresh_token_hash == old_hash, Session.revoked_at.is_(None))
            .values(
                refresh_token_hash=new_hash,
                last_used_at=now,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )
        await self._session.commit()
        return result.rowcount == 1
