from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from sms.domains.assessments.models import AssessmentType


class AssessmentBase(BaseModel):
    class_id: UUID
    name: str
    type: AssessmentType
    max_score: Decimal = Field(gt=0)
    date: date_type


class AssessmentCreate(AssessmentBase):
    pass


class AssessmentUpdate(BaseModel):
    class_id: UUID | None = None
    name: str | None = None
    type: AssessmentType | None = None
    max_score: Decimal | None = Field(default=None, gt=0)
    date: date_type | None = None


class AssessmentRead(AssessmentBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class GradeCreate(BaseModel):
    assessment_id: UUID
    student_id: UUID
    score: Decimal = Field(ge=0)


class GradeUpdate(BaseModel):
    # The only field — a grade update is always "set a new score", no
    # partial-update semantics needed.
    score: Decimal = Field(ge=0)


class GradeRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    assessment_id: UUID
    student_id: UUID
    score: Decimal
    graded_at: datetime


class GradebookAssessmentColumn(BaseModel):
    assessment_id: UUID
    name: str
    type: AssessmentType
    max_score: Decimal
    date: date_type


class GradebookStudentRow(BaseModel):
    student_id: UUID
    student_number: str
    first_name: str
    last_name: str
    # Keyed by assessment_id, not positionally aligned to the assessments
    # list — a dict is self-describing and can't silently desync the way a
    # same-length parallel array could. None = ungraded, never omitted.
    scores: dict[UUID, Decimal | None]


class ClassGradebookRead(BaseModel):
    class_id: UUID
    assessments: list[GradebookAssessmentColumn]
    students: list[GradebookStudentRow]
