import io
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi import UploadFile
from starlette.datastructures import Headers

from sms.core.config import settings
from sms.core.repository import AbstractRepository
from sms.core.security import DUMMY_PASSWORD_HASH, hash_password, verify_password
from sms.domains.students.exceptions import (
    StudentAlreadyExistsError,
    StudentHasNoLinkedRecordError,
    StudentNotFoundError,
)
from sms.domains.students.models import Student
from sms.domains.students.schemas import StudentCreate, StudentCredentialsRead, StudentUpdate
from sms.domains.students.service import StudentService
from sms.domains.users.models import User, UserRole

# Deliberately NOT imported from tests/domains/auth/unit/test_service.py:
# that module needs FakeStudentRepository/make_student_create from *this*
# file to test AuthService.login_with_pin (see the contract's cross-domain
# note), so importing FakeUserRepository the other way here would create a
# circular import between the two test modules. This is a small, local
# duplicate of the same fake instead — one-directional dependency, matching
# the existing precedent of tests/domains/teachers/unit/
# test_change_request_service.py importing from test_service.py rather than
# the reverse.

# Arbitrary fixed epoch — only used as a base for the fake's deterministic,
# monotonically increasing created_at stamps (see FakeStudentRepository.add),
# same pattern as tests/domains/audit/unit/test_service.py's _EPOCH.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


class FakeStudentRepository(AbstractRepository[Student]):
    """In-memory stand-in for StudentRepository, backed by a plain dict.
    Implements the full AbstractRepository contract plus the two
    domain-specific lookups so StudentService can be unit tested without a
    database. list() mirrors the real repository's pagination contract:
    sorted newest-first by created_at, sliced by limit/offset, returning
    (items, total) — total reflects the full filtered set, not just the
    slice."""

    def __init__(self) -> None:
        self._students: dict[UUID, Student] = {}
        self._sequence = 0
        self._student_number_seq = 0

    async def add(self, entity: Student, *, commit: bool = True) -> Student:
        # commit is accepted but irrelevant here — there's no real
        # transaction to defer, this just matches the real
        # (post-Stage-9) StudentRepository.add's signature, mirroring
        # FakeUserRepository.add in tests/domains/auth/unit/test_service.py.
        if entity.id is None:
            entity.id = uuid4()
        if entity.created_at is None:
            self._sequence += 1
            entity.created_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._students[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> Student | None:
        return self._students.get(entity_id)

    async def list(self, *, limit: int = 50, offset: int = 0) -> tuple[list[Student], int]:
        all_students = sorted(
            self._students.values(), key=lambda s: s.created_at, reverse=True
        )
        return all_students[offset : offset + limit], len(all_students)

    async def remove(self, entity: Student) -> None:
        self._students.pop(entity.id, None)

    async def get_by_email(self, email: str) -> Student | None:
        for student in self._students.values():
            if student.email == email:
                return student
        return None

    async def get_by_student_number(self, student_number: str) -> Student | None:
        for student in self._students.values():
            if student.student_number == student_number:
                return student
        return None

    async def get_by_user_id(self, user_id: UUID) -> Student | None:
        for student in self._students.values():
            if student.user_id == user_id:
                return student
        return None

    async def next_student_number_seq(self) -> int:
        # Mirrors Postgres's nextval('student_number_seq'): monotonically
        # increasing, 1-based, never reused — a plain in-memory counter is
        # enough to exercise StudentService.create's "format whatever the
        # sequence returns" logic without a real DB.
        self._student_number_seq += 1
        return self._student_number_seq


class FakeUserRepository(AbstractRepository[User]):
    """Local, minimal stand-in for UserRepository — only what
    StudentService.generate_pin needs (create-or-reuse a linked User via the
    commit=False two-write pattern). Not the same object as
    tests/domains/auth/unit/test_service.py's FakeUserRepository: importing
    that one here would create a circular import (see the module docstring
    comment above), so this is a deliberately small local duplicate."""

    def __init__(self) -> None:
        self._users: dict[UUID, User] = {}

    async def add(self, entity: User, *, commit: bool = True) -> User:
        if entity.id is None:
            entity.id = uuid4()
        self._users[entity.id] = entity
        return entity

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass

    async def get(self, entity_id: UUID) -> User | None:
        return self._users.get(entity_id)

    async def list(self) -> list[User]:
        return list(self._users.values())

    async def remove(self, entity: User) -> None:
        self._users.pop(entity.id, None)

    async def get_by_email(self, email: str) -> User | None:
        for user in self._users.values():
            if user.email == email:
                return user
        return None


def make_student_create(**overrides: object) -> StudentCreate:
    defaults: dict[str, object] = {
        "student_number": "S-0001",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": date(2010, 1, 1),
        "email": "ada@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
    }
    defaults.update(overrides)
    return StudentCreate(**defaults)


def make_upload_file(
    content: bytes, content_type: str, filename: str = "photo.jpg"
) -> UploadFile:
    return UploadFile(
        io.BytesIO(content), filename=filename, headers=Headers({"content-type": content_type})
    )


@pytest.fixture
def repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def user_repository() -> FakeUserRepository:
    return FakeUserRepository()


@pytest.fixture
def service(
    repository: FakeStudentRepository, user_repository: FakeUserRepository
) -> StudentService:
    # StudentService.generate_pin needs to create-or-reuse a User (the
    # same atomic two-write pattern as UserService.create — see
    # docs/adr and the contract for this stage), so it depends on a
    # UserRepository too, not just its own StudentRepository.
    return StudentService(repository, user_repository)


async def test_create_success(service: StudentService) -> None:
    data = make_student_create()

    student = await service.create(data)

    assert student.id is not None
    assert student.student_number == "S-0001"
    assert student.first_name == "Ada"
    assert student.last_name == "Lovelace"
    assert student.email == "ada@example.com"
    assert student.enrollment_status == "active"


async def test_create_duplicate_email_raises(service: StudentService) -> None:
    await service.create(make_student_create(student_number="S-0001", email="dup@example.com"))

    with pytest.raises(StudentAlreadyExistsError):
        await service.create(
            make_student_create(student_number="S-0002", email="dup@example.com")
        )


async def test_create_duplicate_student_number_raises(service: StudentService) -> None:
    await service.create(make_student_create(student_number="S-DUP", email="one@example.com"))

    with pytest.raises(StudentAlreadyExistsError):
        await service.create(
            make_student_create(student_number="S-DUP", email="two@example.com")
        )


async def test_get_success(service: StudentService) -> None:
    created = await service.create(make_student_create())

    fetched = await service.get(created.id)

    assert fetched.id == created.id
    assert fetched.email == created.email


async def test_get_missing_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.get(uuid4())


async def test_list(service: StudentService) -> None:
    await service.create(make_student_create(student_number="S-0001", email="a@example.com"))
    await service.create(make_student_create(student_number="S-0002", email="b@example.com"))

    students, total = await service.list(limit=50, offset=0)

    assert len(students) == 2
    assert total == 2
    assert {s.student_number for s in students} == {"S-0001", "S-0002"}


async def test_list_pagination_slices_and_reports_total(service: StudentService) -> None:
    for i in range(5):
        await service.create(
            make_student_create(student_number=f"S-{i:04d}", email=f"s{i}@example.com")
        )

    page, total = await service.list(limit=2, offset=0)

    assert len(page) == 2
    assert total == 5


async def test_list_pagination_offset_skips_correctly(service: StudentService) -> None:
    created = [
        await service.create(
            make_student_create(student_number=f"S-{i:04d}", email=f"off{i}@example.com")
        )
        for i in range(5)
    ]
    # newest-first: index 4 (last created) is first in the full ordering.
    expected_full_order_ids = [s.id for s in reversed(created)]

    page, total = await service.list(limit=2, offset=2)

    assert total == 5
    assert [s.id for s in page] == expected_full_order_ids[2:4]


async def test_list_newest_first_ordering(service: StudentService) -> None:
    first = await service.create(
        make_student_create(student_number="S-ORD-1", email="ord1@example.com")
    )
    second = await service.create(
        make_student_create(student_number="S-ORD-2", email="ord2@example.com")
    )
    third = await service.create(
        make_student_create(student_number="S-ORD-3", email="ord3@example.com")
    )

    page, total = await service.list(limit=50, offset=0)

    assert total == 3
    assert [s.id for s in page] == [third.id, second.id, first.id]


async def test_update_success(service: StudentService) -> None:
    created = await service.create(make_student_create())

    updated = await service.update(
        created.id, StudentUpdate(first_name="Augusta", enrollment_status="graduated")
    )

    assert updated.id == created.id
    assert updated.first_name == "Augusta"
    assert updated.enrollment_status == "graduated"
    assert updated.last_name == "Lovelace"


async def test_update_missing_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.update(uuid4(), StudentUpdate(first_name="Nobody"))


async def test_delete_success(service: StudentService, repository: FakeStudentRepository) -> None:
    created = await service.create(make_student_create())

    await service.delete(created.id)

    assert await repository.get(created.id) is None


async def test_delete_missing_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.delete(uuid4())


# ---------------------------------------------------------------------------
# Auto-generated student_number
# ---------------------------------------------------------------------------


async def test_create_without_student_number_generates_one(service: StudentService) -> None:
    data = make_student_create(student_number=None, email="autogen1@example.com")

    student = await service.create(data)

    assert re.fullmatch(r"STU-\d{4}", student.student_number)


async def test_create_without_student_number_sequential_creates_get_different_numbers(
    service: StudentService,
) -> None:
    first = await service.create(
        make_student_create(student_number=None, email="autogen2@example.com")
    )
    second = await service.create(
        make_student_create(student_number=None, email="autogen3@example.com")
    )

    assert first.student_number != second.student_number
    assert re.fullmatch(r"STU-\d{4}", first.student_number)
    assert re.fullmatch(r"STU-\d{4}", second.student_number)


async def test_create_with_student_number_override_still_works(
    service: StudentService,
) -> None:
    data = make_student_create(student_number="CUSTOM-0001", email="override1@example.com")

    student = await service.create(data)

    assert student.student_number == "CUSTOM-0001"


# ---------------------------------------------------------------------------
# generate_pin
# ---------------------------------------------------------------------------


async def test_generate_pin_creates_user_when_no_linked_user(
    service: StudentService,
    repository: FakeStudentRepository,
    user_repository: FakeUserRepository,
) -> None:
    created = await service.create(
        make_student_create(student_number="STU-PIN-1", email="pin1@example.com")
    )
    assert created.user_id is None

    result = await service.generate_pin(created.id)

    assert isinstance(result, StudentCredentialsRead)
    assert result.student_number == "STU-PIN-1"
    assert re.fullmatch(r"\d{6}", result.pin)

    refreshed = await repository.get(created.id)
    assert refreshed is not None
    assert refreshed.user_id is not None
    assert refreshed.pin_hash is not None
    assert verify_password(result.pin, refreshed.pin_hash)

    linked_user = await user_repository.get(refreshed.user_id)
    assert linked_user is not None
    assert linked_user.email == created.email
    assert linked_user.role == UserRole.STUDENT
    assert linked_user.is_active is True
    # The discarded secret used to create the account must never end up
    # stored as the fixed dummy hash — that constant exists purely for
    # login's constant-time oracle defense, reusing it as a real stored
    # credential would be a genuine vulnerability (any dummy-password guess
    # would then authenticate as this user).
    assert linked_user.hashed_password != DUMMY_PASSWORD_HASH


async def test_generate_pin_reuses_existing_linked_user(
    service: StudentService,
    repository: FakeStudentRepository,
    user_repository: FakeUserRepository,
) -> None:
    existing_user = await user_repository.add(
        User(
            email="pin2@example.com",
            hashed_password=hash_password("whatever"),
            role=UserRole.STUDENT,
            is_active=True,
        )
    )
    created = await service.create(
        make_student_create(
            student_number="STU-PIN-2", email="pin2@example.com", user_id=existing_user.id
        )
    )
    users_before = await user_repository.list()

    result = await service.generate_pin(created.id)

    users_after = await user_repository.list()
    assert len(users_after) == len(users_before)  # no new User created — reused the link

    refreshed = await repository.get(created.id)
    assert refreshed is not None
    assert refreshed.user_id == existing_user.id
    assert verify_password(result.pin, refreshed.pin_hash)


async def test_generate_pin_missing_student_raises(service: StudentService) -> None:
    with pytest.raises(StudentNotFoundError):
        await service.generate_pin(uuid4())


# ---------------------------------------------------------------------------
# get_my_student
# ---------------------------------------------------------------------------


async def test_get_my_student_success(
    service: StudentService, user_repository: FakeUserRepository
) -> None:
    linked_user = await user_repository.add(
        User(email="me1@example.com", hashed_password=DUMMY_PASSWORD_HASH, role=UserRole.STUDENT)
    )
    created = await service.create(
        make_student_create(
            student_number="STU-ME-1", email="me1@example.com", user_id=linked_user.id
        )
    )

    fetched = await service.get_my_student(linked_user.id)

    assert fetched.id == created.id


async def test_get_my_student_no_linked_record_raises(service: StudentService) -> None:
    with pytest.raises(StudentHasNoLinkedRecordError):
        await service.get_my_student(uuid4())


# ---------------------------------------------------------------------------
# upload_profile_picture / delete cleanup
# ---------------------------------------------------------------------------


async def test_upload_profile_picture_success(
    service: StudentService,
    repository: FakeStudentRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    created = await service.create(
        make_student_create(student_number="STU-PFP-1", email="pfp1@example.com")
    )
    upload = make_upload_file(b"\xff\xd8\xfffake-jpeg-body", "image/jpeg")

    updated = await service.upload_profile_picture(created.id, upload)

    assert updated.profile_picture_path == f"students/{created.id}.jpg"
    saved_path = Path(settings.upload_dir) / updated.profile_picture_path
    assert saved_path.exists()
    assert saved_path.read_bytes() == b"\xff\xd8\xfffake-jpeg-body"

    refreshed = await repository.get(created.id)
    assert refreshed is not None
    assert refreshed.profile_picture_path == updated.profile_picture_path


async def test_upload_profile_picture_missing_student_raises(
    service: StudentService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    upload = make_upload_file(b"fake-jpeg-bytes", "image/jpeg")

    with pytest.raises(StudentNotFoundError):
        await service.upload_profile_picture(uuid4(), upload)


async def test_delete_cleans_up_profile_picture_file(
    service: StudentService,
    repository: FakeStudentRepository,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    created = await service.create(
        make_student_create(student_number="STU-PFP-2", email="pfp2@example.com")
    )
    upload = make_upload_file(b"\xff\xd8\xfffake-jpeg-body", "image/jpeg")
    updated = await service.upload_profile_picture(created.id, upload)
    saved_path = Path(settings.upload_dir) / updated.profile_picture_path
    assert saved_path.exists()

    await service.delete(created.id)

    assert not saved_path.exists()
    assert await repository.get(created.id) is None


async def test_delete_without_profile_picture_does_not_raise(
    service: StudentService, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "upload_dir", str(tmp_path))
    created = await service.create(
        make_student_create(student_number="STU-PFP-3", email="pfp3@example.com")
    )

    await service.delete(created.id)  # must not raise even with no picture set
