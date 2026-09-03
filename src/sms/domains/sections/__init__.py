"""Sections — grade levels, sections (form/homeroom groups), and the
student-to-section assignment that drives auto-enrollment. Fans into
academic_years, classes, enrollments, students and teachers; nothing
depends back on this domain, so the one-way shape every other domain
follows (docs/adr/0016, 0017) holds.

This domain deliberately owns attaching a Class to a Section rather than
ClassService doing it: the back-fill needs the enrollments domain, which
already imports classes, and both packages re-export their services here —
so putting it the other way round would be a circular import."""

from sms.domains.sections.exceptions import (
    ClassAlreadyAttachedError,
    ClassNotAttachedError,
    ClassYearMismatchError,
    GradeLevelAlreadyExistsError,
    GradeLevelNotFoundError,
    SectionAlreadyExistsError,
    SectionAssignmentNotFoundError,
    SectionFullError,
    SectionNotFoundError,
    StudentAlreadyAssignedError,
)
from sms.domains.sections.models import GradeLevel, Section, SectionAssignment
from sms.domains.sections.repository import (
    GradeLevelRepository,
    SectionAssignmentRepository,
    SectionRepository,
)
from sms.domains.sections.schemas import (
    GradeLevelCreate,
    GradeLevelRead,
    GradeLevelUpdate,
    SectionAssignmentRead,
    SectionCreate,
    SectionRead,
    SectionUpdate,
)
from sms.domains.sections.service import (
    GradeLevelService,
    SectionAssignmentService,
    SectionService,
)

__all__ = [
    "ClassAlreadyAttachedError",
    "ClassNotAttachedError",
    "ClassYearMismatchError",
    "GradeLevelAlreadyExistsError",
    "GradeLevelNotFoundError",
    "SectionAlreadyExistsError",
    "SectionAssignmentNotFoundError",
    "SectionFullError",
    "SectionNotFoundError",
    "StudentAlreadyAssignedError",
    "GradeLevel",
    "Section",
    "SectionAssignment",
    "GradeLevelRepository",
    "SectionAssignmentRepository",
    "SectionRepository",
    "GradeLevelCreate",
    "GradeLevelRead",
    "GradeLevelUpdate",
    "SectionAssignmentRead",
    "SectionCreate",
    "SectionRead",
    "SectionUpdate",
    "GradeLevelService",
    "SectionAssignmentService",
    "SectionService",
]
