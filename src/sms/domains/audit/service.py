from uuid import UUID

from sms.domains.audit.models import AuditLog
from sms.domains.audit.repository import AuditLogRepository


class AuditService:
    def __init__(self, repository: AuditLogRepository) -> None:
        self._repository = repository

    async def record(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        target_user_id: UUID | None = None,
        before: dict | None = None,
        after: dict | None = None,
        commit: bool = True,
    ) -> AuditLog:
        entry = AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            target_user_id=target_user_id,
            before=before,
            after=after,
        )
        return await self._repository.add(entry, commit=commit)

    async def list_all(self, *, limit: int, offset: int) -> tuple[list[AuditLog], int]:
        # No Python-side sorted() anymore — the repository orders at the
        # DB level now, required for pagination to slice correctly. See
        # docs/adr/0020.
        return await self._repository.list(limit=limit, offset=offset)
