from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from sms.domains.students.models import EnrollmentStatus


class StudentBase(BaseModel):
    student_number: str
    first_name: str
    last_name: str
    date_of_birth: date
    email: str
    guardian_name: str
    guardian_phone: str


class StudentCreate(StudentBase):
    # Overrides StudentBase's required student_number — omit it to have
    # StudentService.create() generate one (STU-0001, ...) via a DB
    # sequence; supply it to keep the existing manual-override behavior.
    student_number: str | None = None
    user_id: UUID | None = None


class StudentUpdate(BaseModel):
    student_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    email: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    enrollment_status: EnrollmentStatus | None = None
    user_id: UUID | None = None


class StudentRead(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_id: UUID | None
    enrollment_status: EnrollmentStatus
    profile_picture_path: str | None
    created_at: datetime
    updated_at: datetime


class StudentCredentialsRead(BaseModel):
    """The raw PIN appears here once, on generation/reset, and nowhere
    else — never persisted, never logged, not part of StudentRead."""

    student_number: str
    pin: str
