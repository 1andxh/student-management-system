from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from sms.domains.enrollments.models import EnrollmentStatus


class EnrollmentCreate(BaseModel):
    student_id: UUID
    class_id: UUID


class EnrollmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    class_id: UUID
    status: EnrollmentStatus
    enrolled_at: datetime
