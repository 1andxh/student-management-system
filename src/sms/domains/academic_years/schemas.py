from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class AcademicYearBase(BaseModel):
    name: str
    start_date: date
    end_date: date


class AcademicYearCreate(AcademicYearBase):
    pass


class AcademicYearUpdate(BaseModel):
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class AcademicYearRead(AcademicYearBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime


class TermBase(BaseModel):
    academic_year_id: UUID
    name: str
    start_date: date
    end_date: date


class TermCreate(TermBase):
    pass


class TermUpdate(BaseModel):
    # academic_year_id is deliberately not here — a term's year is
    # permanent; reassigning one isn't supported, delete+recreate instead.
    name: str | None = None
    start_date: date | None = None
    end_date: date | None = None


class TermRead(TermBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
