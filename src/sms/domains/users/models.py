import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, Index, String, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class UserRole(str, Enum):
    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    TEACHER = "teacher"
    STUDENT = "student"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    email: Mapped[str] = mapped_column(String, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(
        SAEnum(
            UserRole,
            name="user_role",
            native_enum=True,
            # See docs/adr/0005 — SQLAlchemy's Enum type stores the member
            # *name* by default, not its value; every Enum column in this
            # project must set this explicitly.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    # A plain UniqueConstraint("email") is case-sensitive, but
    # get_by_email's lookup is deliberately case-insensitive
    # (func.lower(...)) — a bare column constraint would let
    # "Admin@x.com" and "admin@x.com" both get created, and a later
    # get_by_email for that address would match two rows, raising
    # MultipleResultsFound on every future login. The functional index
    # makes the DB enforce the same "email" the read path means. Defined
    # after the columns (not alongside __tablename__) since it must
    # reference the already-bound `email` column object. See docs/adr/0010.
    __table_args__ = (Index("uq_users_email_lower", func.lower(email), unique=True),)
