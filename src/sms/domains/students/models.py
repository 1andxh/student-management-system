import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    GRADUATED = "graduated"
    WITHDRAWN = "withdrawn"


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        UniqueConstraint("student_number", name="uq_students_student_number"),
        UniqueConstraint("email", name="uq_students_email"),
        UniqueConstraint("user_id", name="uq_students_user_id"),
        CheckConstraint("date_of_birth <= CURRENT_DATE", name="ck_students_dob_not_future"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Same shape and reasoning as Teacher.user_id (docs/adr/0013): SET NULL,
    # nullable — a Student can exist with no linked login, and the record
    # should outlive the login account if it's ever removed. Added in
    # Stage 7 specifically to support "a student sees only their own
    # grades" (docs/adr/0018) — Student predates auth/users entirely
    # (Stage 1), so this link never existed until it was actually needed.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    student_number: Mapped[str] = mapped_column(String, nullable=False)
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    date_of_birth: Mapped[date] = mapped_column(Date, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    enrollment_status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(
            EnrollmentStatus,
            name="student_enrollment_status",
            native_enum=True,
            # SQLAlchemy's Enum type stores the Python member *name* by
            # default (e.g. "ACTIVE"), not its value ("active") — without
            # this, the DB-stored labels would silently diverge from the
            # lowercase values the API contract and plan's data model use.
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EnrollmentStatus.ACTIVE,
    )
    guardian_name: Mapped[str] = mapped_column(String, nullable=False)
    guardian_phone: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
