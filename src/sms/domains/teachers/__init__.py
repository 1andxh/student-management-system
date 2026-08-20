"""Teachers domain — staff/HR records, optionally linked to a User login.
Mutations are admin-only (see docs/adr/0010's precedent for why staff/account
data gets a stricter tier than academic content). Depends on auth for RBAC
(see docs/adr/0006)."""

from sms.domains.teachers.exceptions import (
    ChangeRequestNotPendingError,
    PendingChangeRequestExistsError,
    TeacherAlreadyExistsError,
    TeacherChangeRequestNotFoundError,
    TeacherHasNoLinkedRecordError,
    TeacherNotFoundError,
)
from sms.domains.teachers.models import ChangeRequestStatus, Teacher, TeacherChangeRequest
from sms.domains.teachers.repository import TeacherChangeRequestRepository, TeacherRepository
from sms.domains.teachers.schemas import (
    TeacherChangeRequestCreate,
    TeacherChangeRequestRead,
    TeacherCreate,
    TeacherRead,
    TeacherUpdate,
)
from sms.domains.teachers.service import TeacherChangeRequestService, TeacherService

__all__ = [
    "ChangeRequestNotPendingError",
    "PendingChangeRequestExistsError",
    "TeacherAlreadyExistsError",
    "TeacherChangeRequestNotFoundError",
    "TeacherHasNoLinkedRecordError",
    "TeacherNotFoundError",
    "ChangeRequestStatus",
    "Teacher",
    "TeacherChangeRequest",
    "TeacherChangeRequestRepository",
    "TeacherRepository",
    "TeacherChangeRequestCreate",
    "TeacherChangeRequestRead",
    "TeacherCreate",
    "TeacherRead",
    "TeacherUpdate",
    "TeacherChangeRequestService",
    "TeacherService",
]
