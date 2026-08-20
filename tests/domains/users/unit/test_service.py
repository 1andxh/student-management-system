from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sms.core.repository import AbstractRepository
from sms.core.security import hash_password
from sms.domains.users.exceptions import (
    AdminTierProtectedError,
    LastSuperAdminError,
    UserAlreadyExistsError,
    UserNotFoundError,
)
from sms.domains.users.models import User, UserRole
from sms.domains.users.schemas import UserCreate, UserUpdate
from sms.domains.users.service import UserService

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing created_at stamps (see FakeUserRepository.add),
# same pattern as tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeUserRepository(AbstractRepository[User]):
    """In-memory stand-in for UserRepository, backed by a plain dict. Same
    style as FakeStudentRepository in tests/domains/students/test_service.py
    — implements the full AbstractRepository contract plus the
    domain-specific get_by_email/count_active_super_admins lookups so
    UserService can be unit tested without a database. list() mirrors the
    real repository's pagination contract."""

    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}
        self._sequence = 0

    async def add(self, entity: User, *, commit: bool = True) -> User:
        # commit is accepted but irrelevant here — there's no real
        # transaction to defer, this just matches the real
        # UserRepository.add's signature so UserService's atomic
        # create/update flow (commit=False then a final commit()) works
        # against this fake too. See docs/adr/0011.
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._users[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> User | None:
        return self._users.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[User], int]:
        all_users = sorted(self._users.values(), key=lambda u: u.created_at, reverse=True)
        return all_users[offset : offset + limit], len(all_users)

    async def remove(self, entity: User) -> None:
        self._users.pop(entity.id, None)

    async def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email:
                return user
        return None

    async def count_active_super_admins(self) -> int:
        # Same computation the real UserRepository.count_active_super_admins
        # runs as a COUNT query — needed so UserService's last-super-admin
        # guard (see sms.domains.users.service) can be unit tested without a
        # database.
        return sum(
            1
            for user in self._users.values()
            if user.role == UserRole.SUPER_ADMIN and user.is_active
        )


class FakeAuditService:
    """Minimal stand-in for sms.domains.audit.service.AuditService —
    UserService.create/update require an AuditService in their constructor,
    but users' own unit tests only need that dependency to be satisfiable,
    not to verify audit persistence itself (that's covered by
    tests/domains/audit/unit/test_service.py and the audit integration
    test's "user.created" assertion). Duck-types AuditService.record's
    signature; calls are recorded in-memory in case a future test here
    wants to assert on them."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def record(
        self,
        *,
        actor_user_id: UUID | None,
        action: str,
        target_user_id: UUID | None = None,
        before: dict | None = None,
        after: dict | None = None,
        commit: bool = True,
    ) -> None:
        self.calls.append(
            {
                "actor_user_id": actor_user_id,
                "action": action,
                "target_user_id": target_user_id,
                "before": before,
                "after": after,
            }
        )


def make_user(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "email": "ada@example.com",
        "hashed_password": hash_password("correct-horse"),
        "role": UserRole.ADMIN,
        "is_active": True,
    }
    defaults.update(overrides)
    return User(**defaults)


@pytest.fixture
def repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def audit_service() -> FakeAuditService:
    return FakeAuditService()


@pytest.fixture
def user_service(
    repository: FakeUserRepository, audit_service: FakeAuditService
) -> UserService:
    return UserService(repository, audit_service)


@pytest.fixture
def admin_actor() -> User:
    """A plain ADMIN acting_user — most existing create/update tests use
    this, since none of the pre-existing scenarios touch an admin-tier
    target or create a SUPER_ADMIN."""
    return make_user(email="acting-admin@example.com", role=UserRole.ADMIN)


@pytest.fixture
def super_admin_actor() -> User:
    return make_user(email="acting-super-admin@example.com", role=UserRole.SUPER_ADMIN)


def make_user_create(**overrides: object) -> UserCreate:
    defaults: dict[str, object] = {
        "email": "ada@example.com",
        "password": "correct-horse",
        "role": UserRole.TEACHER,
    }
    defaults.update(overrides)
    return UserCreate(**defaults)


async def test_user_service_create_success(
    user_service: UserService, admin_actor: User
) -> None:
    user = await user_service.create(
        make_user_create(email="grace@example.com", role=UserRole.TEACHER),
        acting_user=admin_actor,
    )

    assert user.id is not None
    assert user.email == "grace@example.com"
    assert user.role == UserRole.TEACHER
    # The hash, not the plaintext, must be persisted on the model.
    assert user.hashed_password != "correct-horse"


async def test_user_service_create_duplicate_email_raises(
    user_service: UserService, admin_actor: User
) -> None:
    await user_service.create(make_user_create(email="dup@example.com"), acting_user=admin_actor)

    with pytest.raises(UserAlreadyExistsError):
        await user_service.create(make_user_create(email="dup@example.com"), acting_user=admin_actor)


async def test_user_service_get_success(
    user_service: UserService, admin_actor: User
) -> None:
    created = await user_service.create(
        make_user_create(email="ada@example.com"), acting_user=admin_actor
    )

    fetched = await user_service.get(created.id)

    assert fetched.id == created.id
    assert fetched.email == "ada@example.com"


async def test_user_service_get_missing_raises(user_service: UserService) -> None:
    with pytest.raises(UserNotFoundError):
        await user_service.get(uuid4())


async def test_user_service_list(user_service: UserService, admin_actor: User) -> None:
    await user_service.create(make_user_create(email="a@example.com"), acting_user=admin_actor)
    await user_service.create(make_user_create(email="b@example.com"), acting_user=admin_actor)

    users, total = await user_service.list(limit=50, offset=0)

    assert len(users) == 2
    assert total == 2
    assert {u.email for u in users} == {"a@example.com", "b@example.com"}


async def test_user_service_list_pagination_smoke(
    user_service: UserService, admin_actor: User
) -> None:
    for i in range(3):
        await user_service.create(
            make_user_create(email=f"pg{i}@example.com"), acting_user=admin_actor
        )

    page, total = await user_service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 3


async def test_user_service_update_role_leaves_is_active_unchanged(
    user_service: UserService, admin_actor: User, super_admin_actor: User
) -> None:
    # Promoting TEACHER -> ADMIN touches the admin tier via the *new* role,
    # even though the target isn't currently admin-tier — only a
    # super_admin acting_user can do this (see AdminTierProtectedError
    # tests below for the plain-admin-blocked case).
    created = await user_service.create(
        make_user_create(email="ada@example.com", role=UserRole.TEACHER),
        acting_user=admin_actor,
    )

    updated = await user_service.update(
        created.id, UserUpdate(role=UserRole.ADMIN), acting_user=super_admin_actor
    )

    assert updated.id == created.id
    assert updated.role == UserRole.ADMIN
    assert updated.is_active is True


async def test_user_service_update_is_active_leaves_role_unchanged(
    user_service: UserService, admin_actor: User
) -> None:
    # Target stays TEACHER throughout (role isn't part of this update), so
    # this never touches the admin tier — a plain admin_actor is fine here.
    created = await user_service.create(
        make_user_create(email="ada@example.com", role=UserRole.TEACHER),
        acting_user=admin_actor,
    )

    updated = await user_service.update(
        created.id, UserUpdate(is_active=False), acting_user=admin_actor
    )

    assert updated.id == created.id
    assert updated.is_active is False
    assert updated.role == UserRole.TEACHER


async def test_user_service_update_missing_raises(
    user_service: UserService, admin_actor: User
) -> None:
    with pytest.raises(UserNotFoundError):
        await user_service.update(uuid4(), UserUpdate(is_active=False), acting_user=admin_actor)


# --- super_admin tier protection (docs/adr/0010-style contract) ---


async def test_user_service_create_super_admin_as_super_admin_succeeds(
    user_service: UserService, super_admin_actor: User
) -> None:
    user = await user_service.create(
        make_user_create(email="new-super@example.com", role=UserRole.SUPER_ADMIN),
        acting_user=super_admin_actor,
    )

    assert user.role == UserRole.SUPER_ADMIN


async def test_user_service_create_super_admin_as_admin_raises(
    user_service: UserService, admin_actor: User
) -> None:
    with pytest.raises(AdminTierProtectedError):
        await user_service.create(
            make_user_create(email="blocked-super@example.com", role=UserRole.SUPER_ADMIN),
            acting_user=admin_actor,
        )


async def test_user_service_create_admin_as_admin_succeeds(
    user_service: UserService, admin_actor: User
) -> None:
    # Creating a *plain* ADMIN account isn't gated — only creating a new
    # SUPER_ADMIN is (see test above).
    user = await user_service.create(
        make_user_create(email="new-admin@example.com", role=UserRole.ADMIN),
        acting_user=admin_actor,
    )

    assert user.role == UserRole.ADMIN


async def test_user_service_update_admin_target_as_admin_raises(
    user_service: UserService, admin_actor: User
) -> None:
    target = await user_service.create(
        make_user_create(email="target-admin@example.com", role=UserRole.ADMIN),
        acting_user=admin_actor,
    )

    with pytest.raises(AdminTierProtectedError):
        await user_service.update(
            target.id, UserUpdate(is_active=False), acting_user=admin_actor
        )


async def test_user_service_update_admin_target_as_super_admin_succeeds(
    user_service: UserService, admin_actor: User, super_admin_actor: User
) -> None:
    target = await user_service.create(
        make_user_create(email="target-admin2@example.com", role=UserRole.ADMIN),
        acting_user=admin_actor,
    )

    updated = await user_service.update(
        target.id, UserUpdate(is_active=False), acting_user=super_admin_actor
    )

    assert updated.is_active is False


async def test_user_service_update_last_super_admin_self_demote_raises(
    user_service: UserService, repository: FakeUserRepository
) -> None:
    # Only one active super_admin exists (the acting_user itself) —
    # changing their role away from SUPER_ADMIN would leave zero.
    only_super_admin = await repository.add(
        make_user(email="only-super@example.com", role=UserRole.SUPER_ADMIN)
    )

    with pytest.raises(LastSuperAdminError):
        await user_service.update(
            only_super_admin.id,
            UserUpdate(role=UserRole.ADMIN),
            acting_user=only_super_admin,
        )


async def test_user_service_update_last_super_admin_deactivate_raises(
    user_service: UserService, repository: FakeUserRepository
) -> None:
    # Same guard, triggered via is_active=False instead of a role change.
    only_super_admin = await repository.add(
        make_user(email="only-super-2@example.com", role=UserRole.SUPER_ADMIN)
    )

    with pytest.raises(LastSuperAdminError):
        await user_service.update(
            only_super_admin.id,
            UserUpdate(is_active=False),
            acting_user=only_super_admin,
        )


async def test_user_service_update_super_admin_with_another_active_succeeds(
    user_service: UserService, repository: FakeUserRepository
) -> None:
    # A second active super_admin exists, so demoting/deactivating one of
    # them isn't "last super admin" — it's allowed.
    acting = await repository.add(
        make_user(email="acting-super2@example.com", role=UserRole.SUPER_ADMIN)
    )
    target = await repository.add(
        make_user(email="target-super2@example.com", role=UserRole.SUPER_ADMIN)
    )

    updated = await user_service.update(
        target.id, UserUpdate(is_active=False), acting_user=acting
    )

    assert updated.is_active is False
