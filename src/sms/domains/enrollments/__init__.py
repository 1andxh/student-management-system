"""Enrollments — the first aggregate spanning two other domains at once
(Student, Class) in a single transaction. Capacity enforcement uses a
locking read (Class.get_for_update) rather than a Unit-of-Work wrapper —
one READ+one WRITE doesn't need one; see docs/adr/0017. Mutations are
ADMIN+TEACHER (day-to-day record-keeping, not structural/HR data).
Depends on auth for RBAC (see docs/adr/0006)."""

from sms.domains.enrollments.exceptions import (
    ClassFullError,
    EnrollmentAlreadyExistsError,
    EnrollmentNotActiveError,
    EnrollmentNotFoundError,
)
from sms.domains.enrollments.models import Enrollment, EnrollmentStatus
from sms.domains.enrollments.repository import EnrollmentRepository
from sms.domains.enrollments.schemas import EnrollmentCreate, EnrollmentRead
from sms.domains.enrollments.service import EnrollmentService

__all__ = [
    "ClassFullError",
    "EnrollmentAlreadyExistsError",
    "EnrollmentNotActiveError",
    "EnrollmentNotFoundError",
    "Enrollment",
    "EnrollmentStatus",
    "EnrollmentRepository",
    "EnrollmentCreate",
    "EnrollmentRead",
    "EnrollmentService",
]
