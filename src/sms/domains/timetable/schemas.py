from datetime import datetime, time
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from sms.domains.timetable.models import DayOfWeek


class PeriodBase(BaseModel):
    name: str
    start_time: time
    end_time: time


class PeriodCreate(PeriodBase):
    @model_validator(mode="after")
    def _end_after_start(self) -> "PeriodCreate":
        # Mirrors ck_periods_end_after_start so the caller gets a 422 naming
        # the field rather than a 409 from the constraint.
        if self.end_time <= self.start_time:
            raise ValueError("end_time must be after start_time")
        return self


class PeriodUpdate(BaseModel):
    name: str | None = None
    start_time: time | None = None
    end_time: time | None = None

    @model_validator(mode="after")
    def _end_after_start(self) -> "PeriodUpdate":
        # Only checkable when both are supplied together; a partial update
        # touching one of them is validated against the stored row in
        # PeriodService.update, where the other value is known.
        if (
            self.start_time is not None
            and self.end_time is not None
            and self.end_time <= self.start_time
        ):
            raise ValueError("end_time must be after start_time")
        return self


class PeriodRead(PeriodBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class ScheduleSlotCreate(BaseModel):
    class_id: UUID
    day_of_week: DayOfWeek
    period_id: UUID


class ScheduleSlotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    class_id: UUID
    day_of_week: DayOfWeek
    period_id: UUID
    created_at: datetime
