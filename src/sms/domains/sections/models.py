import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class GradeLevel(Base):
    __tablename__ = "grade_levels"
    __table_args__ = (
        UniqueConstraint("name", name="uq_grade_levels_name"),
        UniqueConstraint("rank", name="uq_grade_levels_rank"),
        # >= 0, not > 0 — a Reception/Kindergarten year sits below Grade 1
        # and needs a rank to order by.
        CheckConstraint("rank >= 0", name="ck_grade_levels_rank_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Orders the levels, and is the basis for a future promotion stage
    # (next grade = rank + 1) — deliberately not inferred from name, which
    # varies by school ("Grade 7", "JSS 1", "Year 8").
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Section(Base):
    __tablename__ = "sections"
    __table_args__ = (
        # "7B" is unique within an academic year, not globally — 7B in
        # 2024-25 is a different cohort from 7B in 2025-26.
        UniqueConstraint(
            "grade_level_id", "academic_year_id", "name", name="uq_sections_grade_year_name"
        ),
        CheckConstraint("capacity > 0", name="ck_sections_capacity_positive"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RESTRICT on both, matching Class's own FKs (docs/adr/0016): a Section
    # carries student-assignment data, so deleting a GradeLevel or
    # AcademicYear out from under it must fail loudly rather than cascade.
    grade_level_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("grade_levels.id", ondelete="RESTRICT"), nullable=False
    )
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    # The homeroom teacher. SET NULL + nullable, same shape and reasoning
    # as Teacher.user_id (docs/adr/0013) — a section can exist before one
    # is assigned, and removing a teacher must not destroy the section.
    class_teacher_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teachers.id", ondelete="SET NULL"), nullable=True
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SectionAssignment(Base):
    __tablename__ = "section_assignments"
    __table_args__ = (
        # The one-section-per-student-per-year rule, as a real DB
        # constraint rather than a service-level check.
        UniqueConstraint(
            "student_id", "academic_year_id", name="uq_section_assignments_student_year"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RESTRICT on both — assignment history is real academic-record data,
    # same protective reasoning as Enrollment's own FKs (docs/adr/0017).
    student_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("students.id", ondelete="RESTRICT"), nullable=False
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sections.id", ondelete="RESTRICT"), nullable=False
    )
    # Deliberately denormalised from sections.academic_year_id: Postgres
    # can't express a uniqueness rule that reaches through a FK, and this
    # codebase prefers DB-enforced invariants over service-level ones
    # (docs/adr/0004's reasoning). Always derived from the section by
    # SectionAssignmentService.assign — never accepted from caller input,
    # and not present on any request schema.
    academic_year_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("academic_years.id", ondelete="RESTRICT"), nullable=False
    )
    # No updated_at, deliberately — an assignment is created and removed,
    # never edited in place. Same shape as Enrollment.enrolled_at.
    assigned_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
