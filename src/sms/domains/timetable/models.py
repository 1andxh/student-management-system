import uuid
from datetime import datetime, time
from enum import Enum

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, Time, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class DayOfWeek(str, Enum):
    MONDAY = "monday"
    TUESDAY = "tuesday"
    WEDNESDAY = "wednesday"
    THURSDAY = "thursday"
    FRIDAY = "friday"


class Period(Base):
    """A slot in the school's bell schedule, e.g. "Period 1", 08:00-08:45.
    School-wide rather than per academic year — a bell schedule rarely
    changes, and tying it to a year would mean recreating every period (and
    re-pointing every slot) each September for no benefit."""

    __tablename__ = "periods"
    __table_args__ = (
        UniqueConstraint("name", name="uq_periods_name"),
        CheckConstraint("end_time > start_time", name="ck_periods_end_after_start"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # start_time doubles as the ordering key — no separate rank column,
    # since the bell schedule's order is exactly its chronological order.
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ScheduleSlot(Base):
    """One weekly recurring meeting of a Class: "Monday, Period 3".

    Deliberately carries no date — a slot is a repeating pattern, not an
    occurrence. That's also why there's no "slot falls inside the term"
    validation: there is no date to compare against the term's bounds.

    Note what is NOT denormalised here: teacher_id, room and section_id all
    live on Class, and the three conflict rules key off them. Copying them
    onto this row would let the conflict checks be DB constraints, but
    unlike SectionAssignment.academic_year_id (docs/adr/0024) those columns
    are mutable via PATCH /classes — the copies would go stale and the
    constraint would then enforce the wrong thing. Conflicts are checked in
    ScheduleSlotService instead, under a locking read."""

    __tablename__ = "schedule_slots"
    __table_args__ = (
        UniqueConstraint(
            "class_id", "day_of_week", "period_id", name="uq_schedule_slots_class_day_period"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RESTRICT on both — a timetable is real scheduling data, same
    # protective reasoning as Class's own FKs (docs/adr/0016).
    class_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False
    )
    period_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("periods.id", ondelete="RESTRICT"), nullable=False
    )
    day_of_week: Mapped[DayOfWeek] = mapped_column(
        SAEnum(
            DayOfWeek,
            name="day_of_week",
            native_enum=True,
            # Stores the value ("monday"), not the member name ("MONDAY") —
            # same reasoning as every other enum here (docs/adr/0002).
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    # No updated_at, deliberately — a slot is created and deleted, never
    # edited in place. Same shape as Enrollment.enrolled_at.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
