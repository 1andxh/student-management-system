"""Audit domain — records who did what to admin-tier accounts. Deliberately
dependency-free (imports nothing from sms.domains.auth) so auth can depend
on it without a circular reference; only audit's router (not re-exported
here) reaches into auth, for RBAC gating, same as every other domain's
router. See docs/adr/0011."""

from sms.domains.audit.models import AuditLog
from sms.domains.audit.repository import AuditLogRepository
from sms.domains.audit.schemas import AuditLogRead
from sms.domains.audit.service import AuditService

__all__ = ["AuditLog", "AuditLogRepository", "AuditLogRead", "AuditService"]
