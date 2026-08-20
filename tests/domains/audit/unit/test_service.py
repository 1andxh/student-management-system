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

    async def list(self) -> list[AuditLog]:
        # Deliberately unordered, matching every other repository's list()
        # in this codebase — AuditService.list_all() is what applies the
        # newest-first ordering, not the repository. Sorting here too would
        # still pass (list_all() would just re-sort an already-sorted
        # list), but it wouldn't accurately stand in for the real
        # repository's actual (unordered) contract.
        return list(self._entries.values())

    async def remove(self, entity: AuditLog) -> None:
        self._entries.pop(entity.id, None)


@pytest.fixture
def repository() -> FakeAuditLogRepository:
    return FakeAuditLogRepository()


@pytest.fixture
def service(repository: FakeAuditLogRepository) -> AuditService:
    return AuditService(repository)


async def test_record_stores_entry_retrievable_via_list_all(service: AuditService) -> None:
    actor_id = uuid4()
    target_id = uuid4()

    recorded = await service.record(
        actor_user_id=actor_id,
        action="user.created",
        target_user_id=target_id,
        before=None,
        after={"email": "ada@example.com", "role": "teacher", "is_active": True},
    )

    assert recorded.id is not None
    assert recorded.actor_user_id == actor_id
    assert recorded.action == "user.created"
    assert recorded.target_user_id == target_id
    assert recorded.before is None
    assert recorded.after == {"email": "ada@example.com", "role": "teacher", "is_active": True}

    entries = await service.list_all()
    assert recorded.id in {entry.id for entry in entries}


async def test_record_defaults_target_and_before_after_to_none(service: AuditService) -> None:
    recorded = await service.record(actor_user_id=None, action="user.login")

    assert recorded.actor_user_id is None
    assert recorded.action == "user.login"
    assert recorded.target_user_id is None
    assert recorded.before is None
    assert recorded.after is None


async def test_list_all_returns_newest_first(service: AuditService) -> None:
    # Distinguishable actions, recorded in a known order — list_all() must
    # come back in the reverse (newest-first) order, not insertion order.
    await service.record(actor_user_id=None, action="first.action")
    await service.record(actor_user_id=None, action="second.action")
    await service.record(actor_user_id=None, action="third.action")

    entries = await service.list_all()

    assert [entry.action for entry in entries] == [
        "third.action",
        "second.action",
        "first.action",
    ]
