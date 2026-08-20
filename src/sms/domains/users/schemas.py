from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from sms.domains.users.models import UserRole


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    role: UserRole

    @field_validator("email")
    @classmethod
    def _lowercase_email(cls, value: str) -> str:
        # The DB's uniqueness guard is case-insensitive (uq_users_email_lower)
        # — normalizing here too means the stored value is consistently
        # lowercase, not just uniquely constrained regardless of case.
        return value.lower()


class UserUpdate(BaseModel):
    # Deliberately not email/password here — those need their own,
    # more careful flow (email-change verification, password reset)
    # rather than a bare admin PATCH.
    role: UserRole | None = None
    is_active: bool | None = None
