from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, model_validator

from sms.domains.teachers.models import ChangeRequestStatus


class TeacherBase(BaseModel):
    first_name: str
    last_name: str
    email: str
    hire_date: date


class TeacherCreate(TeacherBase):
    user_id: UUID | None = None


class TeacherUpdate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None
    hire_date: date | None = None
    user_id: UUID | None = None


class TeacherRead(TeacherBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    created_at: datetime
    updated_at: datetime


class TeacherChangeRequestCreate(BaseModel):
    first_name: str | None = None
    last_name: str | None = None
    email: str | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> "TeacherChangeRequestCreate":
        if self.first_name is None and self.last_name is None and self.email is None:
            raise ValueError("At least one field must be provided.")
        return self


class TeacherChangeRequestRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    teacher_id: UUID
    requested_by: UUID | None
    proposed_changes: dict[str, str]
    status: ChangeRequestStatus
    reviewed_by: UUID | None
    reviewed_at: datetime | None
    created_at: datetime
