"""Timetable — the school's bell schedule (Period) and the weekly recurring
meetings of each class (ScheduleSlot).

Fans into classes, sections, students and teachers; nothing depends back on
this domain, which is why every timetable view lives on this domain's own
router rather than being hung off /teachers or /students — those would be
the import direction that makes a cycle.

Conflict detection (teacher / room / section double-booking) is service-
level rather than schema-level, deliberately: see ScheduleSlotService."""

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
from sms.domains.timetable.schemas import (
    PeriodCreate,
    PeriodRead,
    PeriodUpdate,
    ScheduleSlotCreate,
    ScheduleSlotRead,
)
from sms.domains.timetable.service import PeriodService, ScheduleSlotService

__all__ = [
    "InvalidPeriodTimesError",
    "PeriodAlreadyExistsError",
    "PeriodInUseError",
    "PeriodNotFoundError",
    "PeriodOverlapsError",
    "RoomDoubleBookedError",
    "ScheduleSlotNotFoundError",
    "SectionDoubleBookedError",
    "SlotAlreadyScheduledError",
    "TeacherDoubleBookedError",
    "TimetableFilterRequiredError",
    "DayOfWeek",
    "Period",
    "ScheduleSlot",
    "PeriodRepository",
    "ScheduleSlotRepository",
    "PeriodCreate",
    "PeriodRead",
    "PeriodUpdate",
    "ScheduleSlotCreate",
    "ScheduleSlotRead",
    "PeriodService",
    "ScheduleSlotService",
]
