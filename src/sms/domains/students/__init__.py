"""Students domain — the first domain slice, establishing the
models/schemas/repository/service/router/exceptions pattern every later
domain follows. Depends on auth for RBAC (see docs/adr/0006), and on users
(for StudentService.generate_pin's linked-account creation)."""

from sms.domains.students.exceptions import (
    StudentAlreadyExistsError,
    StudentHasNoLinkedRecordError,
    StudentNotFoundError,
)
from sms.domains.students.models import EnrollmentStatus, Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import (
    StudentCreate,
    StudentCredentialsRead,
    StudentRead,
    StudentUpdate,
)
from sms.domains.students.service import StudentService

__all__ = [
    "StudentAlreadyExistsError",
    "StudentHasNoLinkedRecordError",
    "StudentNotFoundError",
    "EnrollmentStatus",
    "Student",
    "StudentRepository",
    "StudentCreate",
    "StudentCredentialsRead",
    "StudentRead",
    "StudentUpdate",
    "StudentService",
]
