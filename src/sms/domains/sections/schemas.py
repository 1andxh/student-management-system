from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class GradeLevelBase(BaseModel):
    name: str
    # ge=0, matching ck_grade_levels_rank_non_negative — a
    # Reception/Kindergarten year ranks below Grade 1.
    rank: int = Field(ge=0)


class GradeLevelCreate(GradeLevelBase):
    pass


class GradeLevelUpdate(BaseModel):
    name: str | None = None
    rank: int | None = Field(default=None, ge=0)


class GradeLevelRead(GradeLevelBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class SectionCreate(BaseModel):
    grade_level_id: UUID
    academic_year_id: UUID
    name: str
    capacity: int = Field(gt=0)
    class_teacher_id: UUID | None = None


class SectionUpdate(BaseModel):
    # grade_level_id/academic_year_id are deliberately not updatable —
    # moving a populated section to a different year would silently
    # invalidate every SectionAssignment's denormalised academic_year_id.
    # Delete and recreate instead.
    name: str | None = None
    capacity: int | None = Field(default=None, gt=0)
    class_teacher_id: UUID | None = None


class SectionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    grade_level_id: UUID
    academic_year_id: UUID
    name: str
    capacity: int
    class_teacher_id: UUID | None
    created_at: datetime
    updated_at: datetime


class SectionAssignmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    student_id: UUID
    section_id: UUID
    academic_year_id: UUID
    assigned_at: datetime
