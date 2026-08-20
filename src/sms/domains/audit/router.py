from fastapi import APIRouter, Depends, Response
from sqlalchemy.ext.asyncio import AsyncSession

from sms.core.pagination import Pagination, pagination_params
from sms.db.session import get_db
from sms.domains.audit.models import AuditLog
from sms.domains.audit.repository import AuditLogRepository
from sms.domains.audit.schemas import AuditLogRead
from sms.domains.audit.service import AuditService
# Router-level dependency on auth for RBAC gating — expected, matches every
# other domain's router (see docs/adr/0006, 0011). Only audit's own
# models/repository/service stay dependency-free.
from sms.domains.auth.dependencies import require_role
from sms.domains.users.models import UserRole

router = APIRouter(prefix="/audit-log", tags=["audit"])
# Audit visibility is super-admin-exclusive, not plain-admin — it records
# admin-tier account changes, so access to it is itself admin-tier-protected.
_super_admin_only = require_role(UserRole.SUPER_ADMIN)


def get_audit_service(session: AsyncSession = Depends(get_db)) -> AuditService:
    return AuditService(AuditLogRepository(session))


@router.get("", response_model=list[AuditLogRead], dependencies=[Depends(_super_admin_only)])
async def list_audit_log(
    response: Response,
    pagination: Pagination = Depends(pagination_params),
    service: AuditService = Depends(get_audit_service),
) -> list[AuditLog]:
    items, total = await service.list_all(limit=pagination.limit, offset=pagination.offset)
    response.headers["X-Total-Count"] = str(total)
    return items
