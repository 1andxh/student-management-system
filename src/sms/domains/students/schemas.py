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
    pass


class StudentUpdate(BaseModel):
    student_number: str | None = None
    first_name: str | None = None
    last_name: str | None = None
    date_of_birth: date | None = None
    email: str | None = None
    guardian_name: str | None = None
    guardian_phone: str | None = None
    enrollment_status: EnrollmentStatus | None = None


class StudentRead(StudentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    enrollment_status: EnrollmentStatus
    created_at: datetime
    updated_at: datetime
