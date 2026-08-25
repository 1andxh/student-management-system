from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest

from sms.core.repository import AbstractRepository
from sms.domains.teachers.exceptions import (
    ChangeRequestNotPendingError,
    PendingChangeRequestExistsError,
    TeacherAlreadyExistsError,
    TeacherChangeRequestNotFoundError,
    TeacherHasNoLinkedRecordError,
)
from sms.domains.teachers.models import ChangeRequestStatus, TeacherChangeRequest
from sms.domains.teachers.schemas import TeacherChangeRequestCreate
from sms.domains.teachers.service import TeacherChangeRequestService, TeacherService
from sms.domains.users.models import User, UserRole
from tests.domains.teachers.unit.test_service import (
    FakeClassRepository,
    FakeTeacherRepository,
    FakeUserRepository,
    make_teacher_create,
)

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing created_at stamps (see
# FakeTeacherChangeRequestRepository.add), same pattern as
# tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeTeacherChangeRequestRepository(AbstractRepository[TeacherChangeRequest]):
    """In-memory stand-in for TeacherChangeRequestRepository, matching the
    dict-backed style of FakeTeacherRepository (tests/domains/teachers/unit/
    test_service.py). Implements the AbstractRepository contract plus the
    one domain-specific lookup the service needs for its pending-request
    pre-check. list() mirrors the real repository's pagination contract."""

    def __init__(self) -> None:
        self._requests: dict[UUID, TeacherChangeRequest] = {}
        self._sequence = 0

    async def add(self, entity: TeacherChangeRequest) -> TeacherChangeRequest:
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._requests[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> TeacherChangeRequest | None:
        return self._requests.get(entity_id)

    async def list(
        self, *, limit: int = 50, offset: int = 0
    ) -> tuple[list[TeacherChangeRequest], int]:
        all_requests = sorted(
            self._requests.values(), key=lambda r: r.created_at, reverse=True
        )
        return all_requests[offset : offset + limit], len(all_requests)

    async def remove(self, entity: TeacherChangeRequest) -> None:
        self._requests.pop(entity.id, None)

    async def get_pending_by_teacher_id(self, teacher_id: UUID) -> TeacherChangeRequest | None:
        for request in self._requests.values():
            if request.teacher_id == teacher_id and request.status == ChangeRequestStatus.PENDING:
                return request
        return None


@pytest.fixture
def teacher_repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def user_repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def teacher_service(
    teacher_repository: FakeTeacherRepository, user_repository: FakeUserRepository
) -> TeacherService:
    # class_repository is only needed for get_my_classes, which
    # TeacherChangeRequestService never calls — a fresh, empty fake is
    # enough here. user_repository IS exposed (not a throwaway instance)
    # because several tests below link a Teacher to a specific user_id via
    # teacher_service.create(...), which now requires that user_id to
    # resolve to a real, TEACHER-role User (_require_teacher_role_user).
    return TeacherService(teacher_repository, user_repository, FakeClassRepository())


async def _make_teacher_role_user(
    user_repository: FakeUserRepository, **overrides: object
) -> User:
    """Local helper — every test below that links a Teacher to a user_id
    needs a real, TEACHER-role User to link to first, now that
    TeacherService._require_teacher_role_user validates that link (mirrors
    the equivalent helper usage in tests/domains/teachers/unit/
    test_service.py)."""
    defaults: dict[str, object] = {
        "email": f"link-{uuid4().hex[:8]}@example.com",
        "hashed_password": "not-a-real-hash",
        "role": UserRole.TEACHER,
        "is_active": True,
    }
    defaults.update(overrides)
    return await user_repository.add(User(**defaults))


@pytest.fixture
def change_request_repository() -> FakeTeacherChangeRequestRepository:
    return FakeTeacherChangeRequestRepository()


@pytest.fixture
def service(
    change_request_repository: FakeTeacherChangeRequestRepository,
    teacher_repository: FakeTeacherRepository,
    teacher_service: TeacherService,
) -> TeacherChangeRequestService:
    return TeacherChangeRequestService(
        change_request_repository, teacher_repository, teacher_service
    )


async def test_get_my_teacher_success(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="linked@example.com")
    teacher = await teacher_service.create(
        make_teacher_create(email="linked@example.com", user_id=user.id)
    )

    fetched = await service.get_my_teacher(user.id)

    assert fetched.id == teacher.id


async def test_get_my_teacher_no_linked_record_raises(
    service: TeacherChangeRequestService,
) -> None:
    with pytest.raises(TeacherHasNoLinkedRecordError):
        await service.get_my_teacher(uuid4())


async def test_create_success(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="create1@example.com")
    teacher = await teacher_service.create(
        make_teacher_create(email="create1@example.com", user_id=user.id)
    )

    request = await service.create(
        user.id, TeacherChangeRequestCreate(first_name="Augusta", email="augusta@example.com")
    )

    assert request.id is not None
    assert request.teacher_id == teacher.id
    assert request.requested_by == user.id
    assert request.proposed_changes == {
        "first_name": "Augusta",
        "email": "augusta@example.com",
    }
    assert request.status == ChangeRequestStatus.PENDING
    assert request.reviewed_by is None
    assert request.reviewed_at is None


async def test_create_partial_proposed_changes_email_only(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="create2@example.com")
    await teacher_service.create(make_teacher_create(email="create2@example.com", user_id=user.id))

    request = await service.create(user.id, TeacherChangeRequestCreate(email="new2@example.com"))

    assert request.proposed_changes == {"email": "new2@example.com"}


async def test_create_no_linked_teacher_raises(service: TeacherChangeRequestService) -> None:
    with pytest.raises(TeacherHasNoLinkedRecordError):
        await service.create(uuid4(), TeacherChangeRequestCreate(first_name="Nobody"))


async def test_create_pending_request_exists_raises(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="create3@example.com")
    await teacher_service.create(make_teacher_create(email="create3@example.com", user_id=user.id))
    await service.create(user.id, TeacherChangeRequestCreate(first_name="First"))

    with pytest.raises(PendingChangeRequestExistsError):
        await service.create(user.id, TeacherChangeRequestCreate(first_name="Second"))


async def test_list_all(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user_a = await _make_teacher_role_user(user_repository, email="list-user-a@example.com")
    user_b = await _make_teacher_role_user(user_repository, email="list-user-b@example.com")
    await teacher_service.create(make_teacher_create(email="list1@example.com", user_id=user_a.id))
    await teacher_service.create(make_teacher_create(email="list2@example.com", user_id=user_b.id))
    await service.create(user_a.id, TeacherChangeRequestCreate(first_name="A"))
    await service.create(user_b.id, TeacherChangeRequestCreate(first_name="B"))

    requests, total = await service.list_all(limit=50, offset=0)

    assert len(requests) == 2
    assert total == 2


async def test_list_all_pagination_smoke(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    for i in range(3):
        user = await _make_teacher_role_user(user_repository, email=f"listpg-user-{i}@example.com")
        await teacher_service.create(
            make_teacher_create(email=f"listpg{i}@example.com", user_id=user.id)
        )
        await service.create(user.id, TeacherChangeRequestCreate(first_name=f"Change{i}"))

    page, total = await service.list_all(limit=2, offset=0)

    assert len(page) == 2
    assert total == 3


async def test_approve_success_mutates_teacher(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    teacher_repository: FakeTeacherRepository,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="approve1@example.com")
    teacher = await teacher_service.create(
        make_teacher_create(
            email="approve1@example.com", first_name="Old", last_name="Name", user_id=user.id
        )
    )
    request = await service.create(
        user.id, TeacherChangeRequestCreate(first_name="New", email="approved1@example.com")
    )
    reviewer_id = uuid4()

    approved = await service.approve(request.id, reviewer_id)

    assert approved.status == ChangeRequestStatus.APPROVED
    assert approved.reviewed_by == reviewer_id
    assert isinstance(approved.reviewed_at, datetime)

    updated_teacher = await teacher_repository.get(teacher.id)
    assert updated_teacher is not None
    assert updated_teacher.first_name == "New"
    assert updated_teacher.email == "approved1@example.com"
    assert updated_teacher.last_name == "Name"


async def test_approve_missing_raises(service: TeacherChangeRequestService) -> None:
    with pytest.raises(TeacherChangeRequestNotFoundError):
        await service.approve(uuid4(), uuid4())


async def test_approve_already_reviewed_raises(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="approve2@example.com")
    await teacher_service.create(make_teacher_create(email="approve2@example.com", user_id=user.id))
    request = await service.create(user.id, TeacherChangeRequestCreate(first_name="X"))
    reviewer_id = uuid4()
    await service.approve(request.id, reviewer_id)

    with pytest.raises(ChangeRequestNotPendingError):
        await service.approve(request.id, reviewer_id)


async def test_approve_propagates_uniqueness_conflict_and_stays_pending(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="approve3@example.com")
    await teacher_service.create(make_teacher_create(email="taken@example.com"))
    await teacher_service.create(make_teacher_create(email="approve3@example.com", user_id=user.id))
    request = await service.create(
        user.id, TeacherChangeRequestCreate(email="taken@example.com")
    )
    reviewer_id = uuid4()

    with pytest.raises(TeacherAlreadyExistsError):
        await service.approve(request.id, reviewer_id)

    # The change request must stay PENDING when the underlying Teacher
    # update fails — approve() shouldn't mark it reviewed on a failed apply.
    still_pending, _total = await service.list_all(limit=50, offset=0)
    matching = next(r for r in still_pending if r.id == request.id)
    assert matching.status == ChangeRequestStatus.PENDING
    assert matching.reviewed_by is None


async def test_reject_success_leaves_teacher_unchanged(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    teacher_repository: FakeTeacherRepository,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="reject1@example.com")
    teacher = await teacher_service.create(
        make_teacher_create(
            email="reject1@example.com", first_name="Same", last_name="Name", user_id=user.id
        )
    )
    request = await service.create(user.id, TeacherChangeRequestCreate(first_name="Different"))
    reviewer_id = uuid4()

    rejected = await service.reject(request.id, reviewer_id)

    assert rejected.status == ChangeRequestStatus.REJECTED
    assert rejected.reviewed_by == reviewer_id
    assert isinstance(rejected.reviewed_at, datetime)

    unchanged_teacher = await teacher_repository.get(teacher.id)
    assert unchanged_teacher is not None
    assert unchanged_teacher.first_name == "Same"


async def test_reject_missing_raises(service: TeacherChangeRequestService) -> None:
    with pytest.raises(TeacherChangeRequestNotFoundError):
        await service.reject(uuid4(), uuid4())


async def test_reject_already_reviewed_raises(
    service: TeacherChangeRequestService,
    teacher_service: TeacherService,
    user_repository: FakeUserRepository,
) -> None:
    user = await _make_teacher_role_user(user_repository, email="reject2@example.com")
    await teacher_service.create(make_teacher_create(email="reject2@example.com", user_id=user.id))
    request = await service.create(user.id, TeacherChangeRequestCreate(first_name="X"))
    reviewer_id = uuid4()
    await service.reject(request.id, reviewer_id)

    with pytest.raises(ChangeRequestNotPendingError):
        await service.reject(request.id, reviewer_id)
