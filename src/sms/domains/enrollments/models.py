import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class EnrollmentStatus(str, Enum):
    ACTIVE = "active"
    DROPPED = "dropped"
    COMPLETED = "completed"


class Enrollment(Base):
    __tablename__ = "enrollments"
    __table_args__ = (
        UniqueConstraint("student_id", "class_id", name="uq_enrollments_student_class"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RESTRICT on both — enrollment history is real academic-record data,
    # same protective reasoning as Class's own FKs (docs/adr/0016): an
    # unrelated Student/Class deletion must not silently wipe it out.
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[EnrollmentStatus] = mapped_column(
        SAEnum(
            EnrollmentStatus,
            name="enrollment_status",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EnrollmentStatus.ACTIVE,
    )
    # No updated_at, deliberately — matches the plan's data model for this
    # table.
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
