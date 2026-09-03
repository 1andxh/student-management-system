from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sms.core.repository import AbstractRepository
from sms.domains.audit.models import AuditLog
from sms.domains.audit.service import AuditService

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing created_at stamps (see FakeAuditLogRepository.add).
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeAuditLogRepository(AbstractRepository[AuditLog]):
    """In-memory stand-in for AuditLogRepository, backed by a plain dict —
    same style as FakeStudentRepository/FakeUserRepository. AuditLog.id and
    .created_at are both DB-assigned defaults (uuid4() / server_default
    func.now()) in the real model, so this fake assigns them at add() time
    too, the same way it assigns id. created_at uses a monotonically
    increasing counter rather than wall-clock time so ordering tests are
    deterministic regardless of how fast add() is called in a test."""

    def __init__(self) -> None:
        self._entries: dict[UUID, AuditLog] = {}
        self._sequence = 0

    async def add(self, entity: AuditLog, *, commit: bool = True) -> AuditLog:
        # commit is accepted but irrelevant here, matching the real
        # AuditLogRepository.add's signature — see docs/adr/0011.
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._entries[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> AuditLog | None:
        return self._entries.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[AuditLog], int]:
        # Ordering moved into the repository layer (superseding the old
        # "sorting is a service/consumer concern" approach — see
        # docs/adr/0011 and the comment on the real AuditLogRepository.list):
        # DB-level LIMIT/OFFSET pagination requires the sort to happen
        # before slicing, which a post-fetch Python sort in the service
        # can no longer correctly do once only a page is fetched.
        all_entries = sorted(self._entries.values(), key=lambda e: e.created_at, reverse=True)
        return all_entries[offset : offset + limit], len(all_entries)

    async def remove(self, entity: AuditLog) -> None:
        self._entries.pop(entity.id, None)


@pytest.fixture
def repository() -> FakeAuditLogRepository:
    return FakeAuditLogRepository()


@pytest.fixture
def service(repository: FakeAuditLogRepository) -> AuditService:
    return AuditService(repository)


async def test_record_defaults_target_and_before_after_to_none(service: AuditService) -> None:
    recorded = await service.record(actor_user_id=None, action="user.login")

    assert recorded.actor_user_id is None
    assert recorded.action == "user.login"
    assert recorded.target_user_id is None
    assert recorded.before is None
    assert recorded.after is None


