"""Subjects and classes — one domain, two related aggregates. Class fans
into three other domains (subjects, terms, teachers) for FK-existence
validation — a one-way dependency, not a cycle (see docs/adr/0016).
Mutations are admin-only. Depends on auth for RBAC (see docs/adr/0006)."""

from sms.domains.classes.exceptions import (
    ClassNotFoundError,
    NotYourClassError,
    SubjectAlreadyExistsError,
    SubjectNotFoundError,
)
from sms.domains.classes.models import Class, Subject
from sms.domains.classes.repository import ClassRepository, SubjectRepository
from sms.domains.classes.schemas import (
    ClassCreate,
    ClassRead,
    ClassUpdate,
    SubjectCreate,
    SubjectRead,
    SubjectUpdate,
)
from sms.domains.classes.service import ClassService, SubjectService

__all__ = [
    "ClassNotFoundError",
    "NotYourClassError",
    "SubjectAlreadyExistsError",
    "SubjectNotFoundError",
    "Class",
    "Subject",
    "ClassRepository",
    "SubjectRepository",
    "ClassCreate",
    "ClassRead",
    "ClassUpdate",
    "SubjectCreate",
    "SubjectRead",
    "SubjectUpdate",
    "ClassService",
    "SubjectService",
]
