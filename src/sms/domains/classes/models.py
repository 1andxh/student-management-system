import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class Subject(Base):
    __tablename__ = "subjects"
    __table_args__ = (UniqueConstraint("code", name="uq_subjects_code"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    code: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class Class(Base):
    __tablename__ = "classes"
    __table_args__ = (CheckConstraint("capacity > 0", name="ck_classes_capacity_positive"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # RESTRICT on all three, deliberately not CASCADE — Class is an
    # aggregate later stages (Enrollment, Assessment) reference, so
    # deleting a Subject/Term/Teacher must not silently destroy scheduling
    # data. Forces an explicit reassignment/cleanup first.
    subject_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("subjects.id", ondelete="RESTRICT"), nullable=False
    )
    term_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("terms.id", ondelete="RESTRICT"), nullable=False
    )
    teacher_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("teachers.id", ondelete="RESTRICT"), nullable=False
    )
    # Null = an individually-enrolled class (the original behavior). Set =
    # taught to a whole section, so assigning a student to that section
    # auto-creates their Enrollment row here.
    #
    # Deliberately absent from ClassCreate/ClassUpdate: attaching a class
    # to a section must back-fill Enrollment rows for the section's current
    # members, which would make classes/service.py import the enrollments
    # domain while enrollments/service.py already imports classes — a real
    # circular-import risk given both packages' __init__.py re-export their
    # services. The sections domain owns attachment instead, so there is
    # exactly one path that can set this.
    section_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("sections.id", ondelete="RESTRICT"), nullable=True
    )
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    room: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
