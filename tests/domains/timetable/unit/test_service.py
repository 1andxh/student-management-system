from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from sqlalchemy.exc import IntegrityError

from sms.core.repository import AbstractRepository
from sms.domains.classes.models import Class
from sms.domains.sections.models import SectionAssignment
from sms.domains.students.models import Student
from sms.domains.teachers.models import Teacher
from sms.domains.timetable.exceptions import (
    RoomDoubleBookedError,
    SectionDoubleBookedError,
    SlotAlreadyScheduledError,
    TeacherDoubleBookedError,
)
from sms.domains.timetable.models import DayOfWeek, Period, ScheduleSlot
from sms.domains.timetable.schemas import ScheduleSlotCreate
from sms.domains.timetable.service import ScheduleSlotService
from sms.domains.users.models import User, UserRole

# Arbitrary fixed epoch, same convention as
# tests/domains/enrollments/unit/test_service.py's identical constant —
# only used for the fake SectionAssignmentRepository's deterministic,
# monotonically increasing assigned_at stamps.
_EPOCH = datetime(2020, 1, 1, tzinfo=timezone.utc)


# ---------------------------------------------------------------------------
# fakes — minimal in-memory stand-ins matching the real repositories'
# actual methods (src/sms/domains/timetable/repository.py,
# src/sms/domains/classes/repository.py, src/sms/domains/teachers/
# repository.py, src/sms/domains/students/repository.py,
# src/sms/domains/sections/repository.py), read directly rather than
# guessed — see docs/adr/0025 on why fakes drifting from the real
# interface is worse than no fake at all.
# ---------------------------------------------------------------------------


class FakeScheduleSlotRepository(AbstractRepository[ScheduleSlot]):
    def __init__(self) -> None:
        self._slots: dict[UUID, ScheduleSlot] = {}

    async def add(self, entity: ScheduleSlot, *, commit: bool = True) -> ScheduleSlot:
        for existing in self._slots.values():
            if existing.id == entity.id:
                continue
            if (
                existing.class_id == entity.class_id
                and existing.day_of_week == entity.day_of_week
                and existing.period_id == entity.period_id
            ):
                # Mirrors uq_schedule_slots_class_day_period — the
                # IntegrityError ScheduleSlotService.create's try/except is
                # meant to catch when the pre-check misses a race, same
                # "pre-check narrows the window, doesn't close it" pattern
                # as every other domain's fake (docs/adr/0004).
                raise IntegrityError("duplicate slot", params=None, orig=Exception())
        if entity.id is None:
            entity.id = uuid4()
        self._slots[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> ScheduleSlot | None:
        return self._slots.get(entity_id)

    async def list(self) -> list[ScheduleSlot]:
        return list(self._slots.values())

    async def remove(self, entity: ScheduleSlot) -> None:
        self._slots.pop(entity.id, None)

    async def get_by_class_day_period(
        self, class_id: UUID, day_of_week: DayOfWeek, period_id: UUID
    ) -> ScheduleSlot | None:
        for slot in self._slots.values():
            if (
                slot.class_id == class_id
                and slot.day_of_week == day_of_week
                and slot.period_id == period_id
            ):
                return slot
        return None

    async def list_by_day_and_period(
        self, day_of_week: DayOfWeek, period_id: UUID
    ) -> list[ScheduleSlot]:
        return [
            slot
            for slot in self._slots.values()
            if slot.day_of_week == day_of_week and slot.period_id == period_id
        ]

    async def list_filtered(
        self,
        *,
        class_ids: list[UUID] | None = None,
        day_of_week: DayOfWeek | None = None,
    ) -> list[ScheduleSlot]:
        results = list(self._slots.values())
        if class_ids is not None:
            results = [slot for slot in results if slot.class_id in class_ids]
        if day_of_week is not None:
            results = [slot for slot in results if slot.day_of_week == day_of_week]
        return results


class FakePeriodRepository(AbstractRepository[Period]):
    """get_for_update() behaves identically to get() here — a
    single-threaded unit test has no concurrent transaction for a real row
    lock to matter against; the lock's concurrency-safety is code-review-
    verified, not something this fake needs to (or can) simulate. Same
    reasoning as FakeClassRepository.get_for_update in
    tests/domains/enrollments/unit/test_service.py. commit()/rollback() are
    no-ops — ScheduleSlotService.create calls them on this session-less
    fake purely to release the (fake) lock."""

    def __init__(self) -> None:
        self._periods: dict[UUID, Period] = {}

    async def add(self, entity: Period) -> Period:
        if entity.id is None:
            entity.id = uuid4()
        self._periods[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Period | None:
        return self._periods.get(entity_id)

    async def list(self) -> list[Period]:
        return list(self._periods.values())

    async def remove(self, entity: Period) -> None:
        self._periods.pop(entity.id, None)

    async def get_for_update(self, entity_id: UUID) -> Period | None:
        return self._periods.get(entity_id)

    async def commit(self) -> None:
        pass

    async def rollback(self) -> None:
        pass


class FakeClassRepository(AbstractRepository[Class]):
    """Minimal in-memory stand-in for ClassRepository.
    list_by_teacher_id/list_by_section_id mirror the real repository's
    identically-named methods (also already used verbatim by
    tests/domains/enrollments/unit/test_service.py and
    tests/domains/assessments/unit/test_service.py's fakes)."""

    def __init__(self) -> None:
        self._classes: dict[UUID, Class] = {}

    async def add(self, entity: Class) -> Class:
        if entity.id is None:
            entity.id = uuid4()
        self._classes[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Class | None:
        return self._classes.get(entity_id)

    async def get_for_update(self, entity_id: UUID) -> Class | None:
        # No locking to model in-memory — mirrors the real
        # repository's interface, which both attach_class and
        # ScheduleSlotService.create go through for their row lock.
        return self._classes.get(entity_id)

    async def list_by_teacher_id(self, teacher_id: UUID) -> list[Class]:
        return [c for c in self._classes.values() if c.teacher_id == teacher_id]

    async def list_by_section_id(self, section_id: UUID) -> list[Class]:
        return [c for c in self._classes.values() if c.section_id == section_id]

    async def list(self) -> list[Class]:
        return list(self._classes.values())

    async def remove(self, entity: Class) -> None:
        self._classes.pop(entity.id, None)


class FakeTeacherRepository(AbstractRepository[Teacher]):
    def __init__(self) -> None:
        self._teachers: dict[UUID, Teacher] = {}

    async def add(self, entity: Teacher) -> Teacher:
        if entity.id is None:
            entity.id = uuid4()
        self._teachers[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Teacher | None:
        return self._teachers.get(entity_id)

    async def list(self) -> list[Teacher]:
        return list(self._teachers.values())

    async def remove(self, entity: Teacher) -> None:
        self._teachers.pop(entity.id, None)

    async def get_by_user_id(self, user_id: UUID) -> Teacher | None:
        for teacher in self._teachers.values():
            if teacher.user_id == user_id:
                return teacher
        return None


class FakeStudentRepository(AbstractRepository[Student]):
    def __init__(self) -> None:
        self._students: dict[UUID, Student] = {}

    async def add(self, entity: Student) -> Student:
        if entity.id is None:
            entity.id = uuid4()
        self._students[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> Student | None:
        return self._students.get(entity_id)

    async def list(self) -> list[Student]:
        return list(self._students.values())

    async def remove(self, entity: Student) -> None:
        self._students.pop(entity.id, None)

    async def get_by_user_id(self, user_id: UUID) -> Student | None:
        for student in self._students.values():
            if student.user_id == user_id:
                return student
        return None


class FakeSectionAssignmentRepository(AbstractRepository[SectionAssignment]):
    """get_latest_by_student_id mirrors the real repository's method of the
    same name (src/sms/domains/sections/repository.py) — "most recent by
    assigned_at" stands in for "current" for the same reason documented
    there: nothing marks an AcademicYear as the one in progress yet."""

    def __init__(self) -> None:
        self._assignments: dict[UUID, SectionAssignment] = {}
        self._sequence = 0

    async def add(self, entity: SectionAssignment) -> SectionAssignment:
        if entity.id is None:
            entity.id = uuid4()
        if entity.assigned_at is None:
            self._sequence += 1
            entity.assigned_at = _EPOCH + timedelta(microseconds=self._sequence)
        self._assignments[entity.id] = entity
        return entity

    async def get(self, entity_id: UUID) -> SectionAssignment | None:
        return self._assignments.get(entity_id)

    async def list(self) -> list[SectionAssignment]:
        return list(self._assignments.values())

    async def remove(self, entity: SectionAssignment) -> None:
        self._assignments.pop(entity.id, None)

    async def get_latest_by_student_id(self, student_id: UUID) -> SectionAssignment | None:
        candidates = [a for a in self._assignments.values() if a.student_id == student_id]
        if not candidates:
            return None
        return max(candidates, key=lambda a: a.assigned_at)


# ---------------------------------------------------------------------------
# instance builders
# ---------------------------------------------------------------------------


def make_class_instance(**overrides: object) -> Class:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "subject_id": uuid4(),
        "term_id": uuid4(),
        "teacher_id": uuid4(),
        "capacity": 30,
        "room": None,
        "section_id": None,
    }
    defaults.update(overrides)
    return Class(**defaults)


def make_period_instance(**overrides: object) -> Period:
    defaults: dict[str, object] = {"id": uuid4(), "name": "Period 1"}
    defaults.update(overrides)
    return Period(**defaults)


def make_teacher_instance(**overrides: object) -> Teacher:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "user_id": None,
        "first_name": "Grace",
        "last_name": "Hopper",
        "email": f"teacher{uuid4().hex[:8]}@example.com",
        "hire_date": date(2015, 6, 1),
    }
    defaults.update(overrides)
    return Teacher(**defaults)


def make_student_instance(**overrides: object) -> Student:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "student_number": f"S-{uuid4().hex[:8]}",
        "first_name": "Ada",
        "last_name": "Lovelace",
        "date_of_birth": date(2010, 1, 1),
        "email": f"{uuid4().hex[:8]}@example.com",
        "guardian_name": "Byron Lovelace",
        "guardian_phone": "+1-555-0100",
    }
    defaults.update(overrides)
    return Student(**defaults)


def make_user_instance(**overrides: object) -> User:
    defaults: dict[str, object] = {
        "id": uuid4(),
        "email": f"{uuid4().hex[:8]}@example.com",
        "hashed_password": "not-a-real-hash",
        "role": UserRole.ADMIN,
        "is_active": True,
    }
    defaults.update(overrides)
    return User(**defaults)


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def slot_repository() -> FakeScheduleSlotRepository:
    return FakeScheduleSlotRepository()


@pytest.fixture
def period_repository() -> FakePeriodRepository:
    return FakePeriodRepository()


@pytest.fixture
def class_repository() -> FakeClassRepository:
    return FakeClassRepository()


@pytest.fixture
def teacher_repository() -> FakeTeacherRepository:
    return FakeTeacherRepository()


@pytest.fixture
def student_repository() -> FakeStudentRepository:
    return FakeStudentRepository()


@pytest.fixture
def assignment_repository() -> FakeSectionAssignmentRepository:
    return FakeSectionAssignmentRepository()


@pytest.fixture
def slot_service(
    slot_repository: FakeScheduleSlotRepository,
    period_repository: FakePeriodRepository,
    class_repository: FakeClassRepository,
    teacher_repository: FakeTeacherRepository,
    student_repository: FakeStudentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
) -> ScheduleSlotService:
    return ScheduleSlotService(
        slot_repository,
        period_repository,
        class_repository,
        teacher_repository,
        student_repository,
        assignment_repository,
    )


@pytest.fixture
async def period(period_repository: FakePeriodRepository) -> Period:
    return await period_repository.add(make_period_instance())


@pytest.fixture
async def other_period(period_repository: FakePeriodRepository) -> Period:
    return await period_repository.add(make_period_instance(name="Period 2"))


# ---------------------------------------------------------------------------
# ScheduleSlotService.create — the three conflict-detection rules
# ---------------------------------------------------------------------------


async def test_create_teacher_double_booked_raises(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    shared_teacher_id = uuid4()
    first = await class_repository.add(make_class_instance(teacher_id=shared_teacher_id))
    second = await class_repository.add(make_class_instance(teacher_id=shared_teacher_id))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    with pytest.raises(TeacherDoubleBookedError):
        await slot_service.create(
            ScheduleSlotCreate(
                class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id
            )
        )


async def test_create_room_double_booked_raises(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    first = await class_repository.add(make_class_instance(room="Room 101"))
    second = await class_repository.add(make_class_instance(room="Room 101"))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    with pytest.raises(RoomDoubleBookedError):
        await slot_service.create(
            ScheduleSlotCreate(
                class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id
            )
        )


async def test_create_null_room_does_not_conflict(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    first = await class_repository.add(make_class_instance(room=None))
    second = await class_repository.add(make_class_instance(room=None))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    slot = await slot_service.create(
        ScheduleSlotCreate(class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    assert slot.class_id == second.id


async def test_create_section_double_booked_raises(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    shared_section_id = uuid4()
    first = await class_repository.add(make_class_instance(section_id=shared_section_id))
    second = await class_repository.add(make_class_instance(section_id=shared_section_id))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    with pytest.raises(SectionDoubleBookedError):
        await slot_service.create(
            ScheduleSlotCreate(
                class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id
            )
        )


async def test_create_null_section_does_not_conflict(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    first = await class_repository.add(make_class_instance(section_id=None))
    second = await class_repository.add(make_class_instance(section_id=None))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    slot = await slot_service.create(
        ScheduleSlotCreate(class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    assert slot.class_id == second.id


async def test_create_same_class_same_slot_twice_raises_already_scheduled(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    cls = await class_repository.add(make_class_instance())
    await slot_service.create(
        ScheduleSlotCreate(class_id=cls.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    with pytest.raises(SlotAlreadyScheduledError):
        await slot_service.create(
            ScheduleSlotCreate(
                class_id=cls.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id
            )
        )


async def test_create_succeeds_in_different_period(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
    other_period: Period,
) -> None:
    shared_teacher_id = uuid4()
    first = await class_repository.add(make_class_instance(teacher_id=shared_teacher_id))
    second = await class_repository.add(make_class_instance(teacher_id=shared_teacher_id))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    # Same teacher, same day, but a different period — no contention.
    slot = await slot_service.create(
        ScheduleSlotCreate(
            class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=other_period.id
        )
    )

    assert slot.period_id == other_period.id


async def test_create_succeeds_on_different_day(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    shared_teacher_id = uuid4()
    first = await class_repository.add(make_class_instance(teacher_id=shared_teacher_id))
    second = await class_repository.add(make_class_instance(teacher_id=shared_teacher_id))
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    # Same teacher, same period, but a different day — no contention.
    slot = await slot_service.create(
        ScheduleSlotCreate(
            class_id=second.id, day_of_week=DayOfWeek.TUESDAY, period_id=period.id
        )
    )

    assert slot.day_of_week == DayOfWeek.TUESDAY


async def test_create_different_teachers_rooms_sections_all_succeed(
    slot_service: ScheduleSlotService,
    class_repository: FakeClassRepository,
    period: Period,
) -> None:
    first = await class_repository.add(
        make_class_instance(teacher_id=uuid4(), room="Room A", section_id=uuid4())
    )
    second = await class_repository.add(
        make_class_instance(teacher_id=uuid4(), room="Room B", section_id=uuid4())
    )
    await slot_service.create(
        ScheduleSlotCreate(class_id=first.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    slot = await slot_service.create(
        ScheduleSlotCreate(class_id=second.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )

    assert slot.class_id == second.id


# Nonexistent-class / nonexistent-period 404s are deliberately NOT
# duplicated here — they're integration-only coverage per this stage's
# test-volume policy (docs/adr/0025): each is exercised once, over HTTP, in
# tests/domains/timetable/integration/test_router.py.


# ---------------------------------------------------------------------------
# ScheduleSlotService.list_my_timetable — the self-scoped resolution
# ---------------------------------------------------------------------------


async def test_list_my_timetable_teacher_gets_only_own_classes_slots(
    slot_service: ScheduleSlotService,
    slot_repository: FakeScheduleSlotRepository,
    class_repository: FakeClassRepository,
    teacher_repository: FakeTeacherRepository,
    period: Period,
) -> None:
    user = make_user_instance(role=UserRole.TEACHER)
    teacher = await teacher_repository.add(make_teacher_instance(user_id=user.id))
    my_class = await class_repository.add(make_class_instance(teacher_id=teacher.id))
    other_class = await class_repository.add(make_class_instance(teacher_id=uuid4()))
    my_slot = await slot_repository.add(
        ScheduleSlot(class_id=my_class.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )
    await slot_repository.add(
        ScheduleSlot(class_id=other_class.id, day_of_week=DayOfWeek.TUESDAY, period_id=period.id)
    )

    result = await slot_service.list_my_timetable(user)

    assert [slot.id for slot in result] == [my_slot.id]


async def test_list_my_timetable_student_gets_their_section_slots(
    slot_service: ScheduleSlotService,
    slot_repository: FakeScheduleSlotRepository,
    class_repository: FakeClassRepository,
    student_repository: FakeStudentRepository,
    assignment_repository: FakeSectionAssignmentRepository,
    period: Period,
) -> None:
    user = make_user_instance(role=UserRole.STUDENT)
    student = await student_repository.add(make_student_instance(user_id=user.id))
    my_section_id = uuid4()
    await assignment_repository.add(
        SectionAssignment(
            student_id=student.id, section_id=my_section_id, academic_year_id=uuid4()
        )
    )
    my_class = await class_repository.add(make_class_instance(section_id=my_section_id))
    other_class = await class_repository.add(make_class_instance(section_id=uuid4()))
    my_slot = await slot_repository.add(
        ScheduleSlot(class_id=my_class.id, day_of_week=DayOfWeek.MONDAY, period_id=period.id)
    )
    await slot_repository.add(
        ScheduleSlot(class_id=other_class.id, day_of_week=DayOfWeek.TUESDAY, period_id=period.id)
    )

    result = await slot_service.list_my_timetable(user)

    assert [slot.id for slot in result] == [my_slot.id]


async def test_list_my_timetable_unlinked_teacher_returns_empty(
    slot_service: ScheduleSlotService,
) -> None:
    user = make_user_instance(role=UserRole.TEACHER)

    result = await slot_service.list_my_timetable(user)

    assert result == []


async def test_list_my_timetable_unlinked_student_returns_empty(
    slot_service: ScheduleSlotService,
) -> None:
    user = make_user_instance(role=UserRole.STUDENT)

    result = await slot_service.list_my_timetable(user)

    assert result == []


async def test_list_my_timetable_student_with_no_section_assignment_returns_empty(
    slot_service: ScheduleSlotService,
    student_repository: FakeStudentRepository,
) -> None:
    user = make_user_instance(role=UserRole.STUDENT)
    await student_repository.add(make_student_instance(user_id=user.id))

    result = await slot_service.list_my_timetable(user)

    assert result == []


async def test_list_my_timetable_admin_returns_empty(slot_service: ScheduleSlotService) -> None:
    user = make_user_instance(role=UserRole.ADMIN)

    result = await slot_service.list_my_timetable(user)

    assert result == []
