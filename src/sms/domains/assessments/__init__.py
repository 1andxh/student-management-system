"""Assessments and grades — one domain, two related aggregates. Grade fans
into students and enrollments (for the enrollment-check and self-view
scoping) alongside its own AssessmentRepository — a one-way fan-in, same
shape as ClassService/EnrollmentService (docs/adr/0016, 0017). Mutations
are ADMIN+TEACHER. A STUDENT caller only sees their own grades — enforced
in GradeService, not the router — via Student.user_id (added in this
stage specifically to support this, see docs/adr/0018). Depends on auth
for RBAC (see docs/adr/0006)."""

from sms.domains.assessments.exceptions import (
    AssessmentNotFoundError,
    GradeAlreadyExistsError,
    GradeNotFoundError,
    ScoreExceedsMaxScoreError,
    StudentNotEnrolledError,
)
from sms.domains.assessments.models import Assessment, AssessmentType, Grade
from sms.domains.assessments.repository import AssessmentRepository, GradeRepository
from sms.domains.assessments.schemas import (
    AssessmentCreate,
    AssessmentRead,
    AssessmentUpdate,
    GradeCreate,
    GradeRead,
    GradeUpdate,
)
from sms.domains.assessments.service import AssessmentService, GradeService

__all__ = [
    "AssessmentNotFoundError",
    "GradeAlreadyExistsError",
    "GradeNotFoundError",
    "ScoreExceedsMaxScoreError",
    "StudentNotEnrolledError",
    "Assessment",
    "AssessmentType",
    "Grade",
    "AssessmentRepository",
    "GradeRepository",
    "AssessmentCreate",
    "AssessmentRead",
    "AssessmentUpdate",
    "GradeCreate",
    "GradeRead",
    "GradeUpdate",
    "AssessmentService",
    "GradeService",
]
