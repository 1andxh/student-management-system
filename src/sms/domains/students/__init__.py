"""Students domain — the first domain slice, establishing the
models/schemas/repository/service/router/exceptions pattern every later
domain follows. Depends on auth for RBAC (see docs/adr/0006)."""

from sms.domains.students.exceptions import StudentAlreadyExistsError, StudentNotFoundError
from sms.domains.students.models import EnrollmentStatus, Student
from sms.domains.students.repository import StudentRepository
from sms.domains.students.schemas import StudentCreate, StudentRead, StudentUpdate
from sms.domains.students.service import StudentService

__all__ = [
    "StudentAlreadyExistsError",
    "StudentNotFoundError",
    "EnrollmentStatus",
    "Student",
    "StudentRepository",
    "StudentCreate",
    "StudentRead",
    "StudentUpdate",
    "StudentService",
]
