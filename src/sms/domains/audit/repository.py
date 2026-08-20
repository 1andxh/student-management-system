from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import paginate
from sms.core.repository import AbstractRepository
from sms.domains.audit.models import AuditLog


class AuditLogRepository(AbstractRepository[AuditLog]):
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, entity: AuditLog, *, commit: bool = True) -> AuditLog:
        self._session.add(entity)
        try:
            if commit:
                await self._session.commit()
            else:
                # See UserRepository.add's docstring — used so this entry
                # commits atomically together with the mutation it records,
                # not as two independently-durable writes. See docs/adr/0011.
                await self._session.flush()
        except Exception:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)
        return entity

    async def get(self, entity_id: UUID) -> AuditLog | None:
        return await self._session.get(AuditLog, entity_id)

    async def list(self, *, limit: int, offset: int) -> tuple[list[AuditLog], int]:
        # Ordering moved here from AuditService.list_all()'s Python-side
        # sorted() — a genuine reason to revisit that ADR 0011 decision,
        # not a silent reversal: pagination requires the DB to order
        # before slicing, since a page can't be correctly sliced and then
        # separately re-sorted client-side. See docs/adr/0020.
        query = select(AuditLog).order_by(AuditLog.created_at.desc())
        return await paginate(self._session, query, limit=limit, offset=offset)

    async def remove(self, entity: AuditLog) -> None:
        await self._session.delete(entity)
        await self._session.commit()
