from datetime import datetime
from uuid import UUID

from sqlalchemy import and_, or_, select, update
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

    async def get_for_refresh(self, token_hash: str, grace_cutoff: datetime) -> Session | None:
        """The session this token belongs to: as its current token, or as the
        token it just replaced, if that rotation happened after grace_cutoff
        (docs/adr/0031). Revocation and expiry are the caller's to check.

        populate_existing: re-read the row even if this AsyncSession already
        holds the object. AuthService.refresh re-reads after losing a
        compare-and-swap to a concurrent request; without this, SQLAlchemy's
        identity map would hand back the stale copy it already had, and the
        retry would see the old state and fail the same way."""
        result = await self._session.execute(
            select(Session)
            .where(
                or_(
                    Session.refresh_token_hash == token_hash,
                    and_(
                        Session.previous_refresh_token_hash == token_hash,
                        Session.rotated_at > grace_cutoff,
                    ),
                )
            )
            .execution_options(populate_existing=True)
        )
        return result.scalar_one_or_none()

    async def rotate(
        self,
        session_id: UUID,
        expected_current_hash: str,
        new_hash: str,
        previous_hash: str | None,
        rotated_at: datetime | None,
        now: datetime,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> bool:
        """Atomic compare-and-swap on the session's current hash — a plain
        read-then-write would let two concurrent refreshes both pass
        validation and each mint a different "next" token, the loser
        silently overwritten (docs/adr/0009). Returns False if the session
        moved on (or was revoked) since the caller read it; the caller
        decides whether to re-read and retry.

        previous_hash/rotated_at are written as given: a normal rotation
        records the token it replaced and now; a grace-window rotation
        passes the existing values through unchanged, so the window stays
        anchored to the original rotation (docs/adr/0031).

        user_agent/ip_address ride along in the same statement — mutating the
        in-memory ORM object afterwards wouldn't persist, since this UPDATE
        bypasses it."""
        result = await self._session.execute(
            update(Session)
            .where(
                Session.id == session_id,
                Session.refresh_token_hash == expected_current_hash,
                Session.revoked_at.is_(None),
            )
            .values(
                refresh_token_hash=new_hash,
                previous_refresh_token_hash=previous_hash,
                rotated_at=rotated_at,
                last_used_at=now,
                user_agent=user_agent,
                ip_address=ip_address,
            )
        )
        await self._session.commit()
        return result.rowcount == 1
