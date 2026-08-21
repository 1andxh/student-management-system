import uuid
from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, UniqueConstraint, func, text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class Teacher(Base):
    __tablename__ = "teachers"
    __table_args__ = (
        UniqueConstraint("email", name="uq_teachers_email"),
        UniqueConstraint("user_id", name="uq_teachers_user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # SET NULL, not CASCADE — a teacher's HR record should outlive the login
    # account it happens to be linked to (same reasoning as AuditLog's
    # actor_user_id; there's no DELETE /users/{id} today, but the FK
    # shouldn't assume that stays true forever). Nullable: a Teacher can
    # exist with no linked login yet.
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    first_name: Mapped[str] = mapped_column(String, nullable=False)
    last_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False)
    hire_date: Mapped[date] = mapped_column(Date, nullable=False)
    profile_picture_path: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChangeRequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


class TeacherChangeRequest(Base):
    __tablename__ = "teacher_change_requests"
    __table_args__ = (
        # Partial unique index, not a plain UniqueConstraint — only one
        # PENDING request per teacher counts; approved/rejected rows don't
        # block a later resubmission. This is the actual race-proof guard
        # (the service's pre-check narrows the window but doesn't close it,
        # same pattern as every other domain's create() — see docs/adr/0004).
        Index(
            "uq_teacher_change_requests_one_pending_per_teacher",
            "teacher_id",
            unique=True,
            postgresql_where=text("status = 'pending'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # CASCADE, unlike Teacher.user_id's SET NULL — a change request has no
    # meaning once the Teacher it targets is gone.
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teachers.id", ondelete="CASCADE"), nullable=False
    )
    requested_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    proposed_changes: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[ChangeRequestStatus] = mapped_column(
        SAEnum(
            ChangeRequestStatus,
            name="teacher_change_request_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ChangeRequestStatus.PENDING,
    )
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
