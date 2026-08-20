import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import CheckConstraint, Date, DateTime, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class AssessmentType(str, Enum):
    EXAM = "exam"
    QUIZ = "quiz"
    ASSIGNMENT = "assignment"
    PROJECT = "project"


class Assessment(Base):
    __tablename__ = "assessments"
    __table_args__ = (
        CheckConstraint("max_score > 0", name="ck_assessments_max_score_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    class_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("classes.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    type: Mapped[AssessmentType] = mapped_column(
        SAEnum(
            AssessmentType,
            name="assessment_type",
            native_enum=True,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    max_score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Grade(Base):
    __tablename__ = "grades"
    __table_args__ = (
        UniqueConstraint("assessment_id", "student_id", name="uq_grades_assessment_student"),
        CheckConstraint("score >= 0", name="ck_grades_score_nonnegative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    assessment_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("assessments.id", ondelete="RESTRICT"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    score: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    # No updated_at, deliberately — matches the plan's data model for this
    # table (same as Enrollment.enrolled_at).
    graded_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
