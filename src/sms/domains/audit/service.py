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

    async def list_all(self) -> list[AuditLog]:
        entries = await self._repository.list()
        return sorted(entries, key=lambda entry: entry.created_at, reverse=True)
