from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class SubjectBase(BaseModel):
    name: str
    code: str


class SubjectCreate(SubjectBase):
    pass


class SubjectUpdate(BaseModel):
    name: str | None = None
    code: str | None = None


class SubjectRead(SubjectBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class ClassBase(BaseModel):
    subject_id: UUID
    term_id: UUID
    teacher_id: UUID
    capacity: int = Field(gt=0)
    room: str | None = None


class ClassCreate(ClassBase):
    pass


class ClassUpdate(BaseModel):
    subject_id: UUID | None = None
    term_id: UUID | None = None
    teacher_id: UUID | None = None
    capacity: int | None = Field(default=None, gt=0)
    room: str | None = None


class ClassRead(ClassBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    # Read-only here by design — set only via the sections domain's
    # attach/detach routes, which also back-fill the section's roster.
    section_id: UUID | None
    created_at: datetime
    updated_at: datetime
