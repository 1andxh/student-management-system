"""Academic years and terms — one domain, two related aggregates (Term
belongs to an AcademicYear, has no independent meaning without one).
Foundation for Classes (Stage 5), which belong to a Term. Mutations are
admin-only. Depends on auth for RBAC (see docs/adr/0006)."""

from sms.domains.academic_years.exceptions import (
    AcademicYearAlreadyExistsError,
    AcademicYearNotFoundError,
    TermAlreadyExistsError,
    TermNotFoundError,
    TermOutsideAcademicYearError,
)
from sms.domains.academic_years.models import AcademicYear, Term
from sms.domains.academic_years.repository import AcademicYearRepository, TermRepository
from sms.domains.academic_years.schemas import (
    AcademicYearCreate,
    AcademicYearRead,
    AcademicYearUpdate,
    TermCreate,
    TermRead,
    TermUpdate,
)
from sms.domains.academic_years.service import AcademicYearService, TermService

__all__ = [
    "AcademicYearAlreadyExistsError",
    "AcademicYearNotFoundError",
    "TermAlreadyExistsError",
    "TermNotFoundError",
    "TermOutsideAcademicYearError",
    "AcademicYear",
    "Term",
    "AcademicYearRepository",
    "TermRepository",
    "AcademicYearCreate",
    "AcademicYearRead",
    "AcademicYearUpdate",
    "TermCreate",
    "TermRead",
    "TermUpdate",
    "AcademicYearService",
    "TermService",
]
