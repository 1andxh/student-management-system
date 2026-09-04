# ScheduleSlotService defines list() and then _resolve_class_ids ->
# list[UUID], so the annotation would resolve against the method rather
# than the builtin. Fourth occurrence of this in the codebase (ADR
# 0018/0019) — see docs/adr/0026 for making this the default for new files
# rather than a fix applied after each recurrence.
from __future__ import annotations

from uuid import UUID

from sqlalchemy.exc import IntegrityError

from sms.domains.classes.exceptions import ClassNotFoundError
from sms.domains.classes.models import Class
from sms.domains.classes.repository import ClassRepository
from sms.domains.sections.repository import SectionAssignmentRepository
from sms.domains.students.repository import StudentRepository
from sms.domains.teachers.repository import TeacherRepository
from sms.domains.timetable.exceptions import (
    InvalidPeriodTimesError,
    PeriodAlreadyExistsError,
    PeriodInUseError,
    PeriodNotFoundError,
    PeriodOverlapsError,
    RoomDoubleBookedError,
    ScheduleSlotNotFoundError,
    SectionDoubleBookedError,
    SlotAlreadyScheduledError,
    TeacherDoubleBookedError,
    TimetableFilterRequiredError,
)
from sms.domains.timetable.models import DayOfWeek, Period, ScheduleSlot
from sms.domains.timetable.repository import PeriodRepository, ScheduleSlotRepository
from sms.domains.timetable.schemas import PeriodCreate, PeriodUpdate, ScheduleSlotCreate
from sms.domains.users.models import User, UserRole


def _translate_period_integrity_error(exc: IntegrityError) -> Exception:
    """Two different constraints guard `periods`, and conflating them would
    tell the caller to rename a period when the real problem is its times.
    Inspects the constraint name, the same approach used for
    uq_section_assignments_student_year in docs/adr/0024."""
    constraint = getattr(exc.orig, "constraint_name", None)
    if constraint == "ex_periods_no_overlap":
        return PeriodOverlapsError()
    return PeriodAlreadyExistsError()


class PeriodService:
    def __init__(self, repository: PeriodRepository) -> None:
        self._repository = repository

    async def create(self, data: PeriodCreate) -> Period:
        if await self._repository.get_by_name(data.name) is not None:
            raise PeriodAlreadyExistsError()

        period = Period(name=data.name, start_time=data.start_time, end_time=data.end_time)
        try:
            return await self._repository.add(period)
        except IntegrityError as exc:
            raise _translate_period_integrity_error(exc) from exc

    async def get(self, period_id: UUID) -> Period:
        period = await self._repository.get(period_id)
        if period is None:
            raise PeriodNotFoundError()
        return period

    async def list(self, *, limit: int, offset: int) -> tuple[list[Period], int]:
        return await self._repository.list(limit=limit, offset=offset)

    async def update(self, period_id: UUID, data: PeriodUpdate) -> Period:
        period = await self.get(period_id)
        updates = data.model_dump(exclude_unset=True)

        new_name = updates.get("name")
        if new_name is not None and new_name != period.name:
            existing = await self._repository.get_by_name(new_name)
            if existing is not None and existing.id != period_id:
                raise PeriodAlreadyExistsError()

        # A partial update touching only one end of the range still has to
        # hold against the stored value for the other end — the schema can
        # only check the case where both are supplied together.
        start = updates.get("start_time", period.start_time)
        end = updates.get("end_time", period.end_time)
        if end <= start:
            raise InvalidPeriodTimesError()

        for field, value in updates.items():
            setattr(period, field, value)
        try:
            return await self._repository.add(period)
        except IntegrityError as exc:
            raise _translate_period_integrity_error(exc) from exc

    async def delete(self, period_id: UUID) -> None:
        period = await self.get(period_id)
        try:
            await self._repository.remove(period)
        except IntegrityError as exc:
            # schedule_slots.period_id is RESTRICT, so deleting a period
            # that is still timetabled raises rather than cascading. Without
            # this it surfaced as a 500 (security-auditor finding). The same
            # gap exists in the other domains' remove() methods; fixed here
            # rather than swept codebase-wide unasked.
            raise PeriodInUseError() from exc


class ScheduleSlotService:
    """Conflict detection lives here rather than in the schema: the three
    rules key off Class.teacher_id / Class.room / Class.section_id, and
    those are mutable via PATCH /classes, so denormalising them onto the
    slot to get DB constraints would leave stale copies enforcing the wrong
    thing (see docs/adr/0024's contrasting case, where the denormalised
    column is immutable by design)."""

    def __init__(
        self,
        repository: ScheduleSlotRepository,
        period_repository: PeriodRepository,
        class_repository: ClassRepository,
        teacher_repository: TeacherRepository,
        student_repository: StudentRepository,
        assignment_repository: SectionAssignmentRepository,
    ) -> None:
        self._repository = repository
        self._periods = period_repository
        self._classes = class_repository
        self._teachers = teacher_repository
        self._students = student_repository
        self._assignments = assignment_repository

    async def _check_conflicts(self, cls: Class, day_of_week: DayOfWeek, period_id: UUID) -> None:
        """The three rules, evaluated against every other class already
        occupying this (day, period). Ordered teacher -> room -> section
        only so the error is deterministic when more than one applies."""
        competing = await self._repository.list_by_day_and_period(day_of_week, period_id)
        if not competing:
            return

        other_classes: list[Class] = []
        for slot in competing:
            if slot.class_id == cls.id:
                # The class's own slot — already rejected upstream by the
                # SlotAlreadyScheduledError check, and it can appear at most
                # once here thanks to uq_schedule_slots_class_day_period.
                continue
            other = await self._classes.get(slot.class_id)
            if other is None:
                # Actually fail closed. An earlier version filtered this out
                # while its comment claimed the opposite — silently skipping
                # the conflict check for a slot whose class had vanished.
                # RESTRICT makes it unreachable today, which is exactly why
                # a future schema change could reopen it unnoticed.
                raise ClassNotFoundError()
            other_classes.append(other)

        if any(other.teacher_id == cls.teacher_id for other in other_classes):
            raise TeacherDoubleBookedError()

        # A NULL room is exempt: "no room assigned" is not a resource two
        # classes can contend for. Note this is a string match — Class.room
        # is free text, so "Room 101" and "room 101" read as different
        # rooms. A real Room entity is the proper fix; see docs/adr/0026.
        if cls.room is not None and any(other.room == cls.room for other in other_classes):
            raise RoomDoubleBookedError()

        # The rule that protects students rather than resources: a
        # section's pupils cannot be in two rooms at once.
        if cls.section_id is not None and any(
            other.section_id == cls.section_id for other in other_classes
        ):
            raise SectionDoubleBookedError()

    async def create(self, data: ScheduleSlotCreate) -> ScheduleSlot:
        # Locking read on the Class, not a plain get. Two reasons: the
        # conflict rules read teacher_id/room/section_id off this row, so a
        # plain read here would evaluate them against pre-lock values; and
        # SectionService.attach_class also locks the Class, which is what
        # stops it racing this method. Without a shared lock, attach_class
        # can set section_id on a class whose slot was just checked while
        # section_id was still NULL — putting two classes from one section
        # in the same slot with no error (security-auditor finding).
        cls = await self._classes.get_for_update(data.class_id)
        if cls is None:
            raise ClassNotFoundError()

        # Locking read on the period — the checks below read the competing
        # slots and then insert, so concurrent callers have to serialise or
        # both could see the slot free. Nothing may commit between here and
        # this method's own commit, which is why the insert uses
        # commit=False (docs/adr/0017).
        period = await self._periods.get_for_update(data.period_id)
        if period is None:
            raise PeriodNotFoundError()

        if (
            await self._repository.get_by_class_day_period(
                cls.id, data.day_of_week, period.id
            )
            is not None
        ):
            raise SlotAlreadyScheduledError()

        await self._check_conflicts(cls, data.day_of_week, period.id)

        slot = ScheduleSlot(
            class_id=cls.id, day_of_week=data.day_of_week, period_id=period.id
        )
        try:
            created = await self._repository.add(slot, commit=False)
            await self._periods.commit()
        except IntegrityError as exc:
            await self._periods.rollback()
            raise SlotAlreadyScheduledError() from exc
        except Exception:
            await self._periods.rollback()
            raise
        return created

    async def delete(self, slot_id: UUID) -> None:
        slot = await self._repository.get(slot_id)
        if slot is None:
            raise ScheduleSlotNotFoundError()
        await self._repository.remove(slot)

    async def list(
        self,
        *,
        class_id: UUID | None = None,
        teacher_id: UUID | None = None,
        section_id: UUID | None = None,
        day_of_week: DayOfWeek | None = None,
    ) -> list[ScheduleSlot]:
        # An unfiltered call would return the whole school's schedule
        # unpaginated. No student identifiers appear in the response (so
        # this is not the docs/adr/0023 roster leak), but combined with the
        # public GET /classes it builds a week-by-week location map of every
        # member of staff and every cohort in two requests. Requiring a
        # filter preserves every legitimate view and removes the bulk scrape
        # (security-auditor finding).
        if class_id is None and teacher_id is None and section_id is None:
            raise TimetableFilterRequiredError()

        class_ids = await self._resolve_class_ids(
            class_id=class_id, teacher_id=teacher_id, section_id=section_id
        )
        return await self._repository.list_filtered(
            class_ids=class_ids, day_of_week=day_of_week
        )

    async def _resolve_class_ids(
        self,
        *,
        class_id: UUID | None,
        teacher_id: UUID | None,
        section_id: UUID | None,
    ) -> list[UUID] | None:
        """Collapses the caller-facing filters into a set of class ids, or
        None for "no class filter at all". Returning an empty list is
        meaningful and different — it means "filtered, and nothing matched",
        which the repository turns into an empty result rather than an
        unfiltered scan."""
        if class_id is None and teacher_id is None and section_id is None:
            return None

        candidates: list[set[UUID]] = []
        if class_id is not None:
            candidates.append({class_id})
        if teacher_id is not None:
            owned = await self._classes.list_by_teacher_id(teacher_id)
            candidates.append({c.id for c in owned})
        if section_id is not None:
            attached = await self._classes.list_by_section_id(section_id)
            candidates.append({c.id for c in attached})

        resolved = set.intersection(*candidates) if candidates else set()
        return list(resolved)

    async def list_my_timetable(self, current_user: User) -> list[ScheduleSlot]:
        """A teacher's own classes, or a student's own section's classes.
        No linked record means an empty timetable, not an error — the same
        "no linked record -> empty scope" precedent as docs/adr/0018/0023.

        ADMIN/SUPER_ADMIN get an empty list rather than everything: they
        have no personal timetable, and silently returning the whole
        school's schedule from a /me route would be a surprising default.
        They use GET /timetable's filters instead."""
        if current_user.role == UserRole.TEACHER:
            teacher = await self._teachers.get_by_user_id(current_user.id)
            if teacher is None:
                return []
            owned = await self._classes.list_by_teacher_id(teacher.id)
            return await self._repository.list_filtered(class_ids=[c.id for c in owned])

        if current_user.role == UserRole.STUDENT:
            student = await self._students.get_by_user_id(current_user.id)
            if student is None:
                return []
            assignment = await self._assignments.get_latest_by_student_id(student.id)
            if assignment is None:
                return []
            attached = await self._classes.list_by_section_id(assignment.section_id)
            return await self._repository.list_filtered(class_ids=[c.id for c in attached])

        return []
