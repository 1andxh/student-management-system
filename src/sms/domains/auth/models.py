import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from sms.db.base import Base


class Session(Base):
    """A logged-in device/browser. Owns the current refresh token for that
    login — revoking this (logout) is what actually invalidates a session
    early, unlike the short-lived access JWT which can't be revoked before
    it naturally expires. See docs/adr/0009.

    user_id references sms.domains.users.models.User's table by name only
    (a plain FK string, "users.id") — this domain never imports the User
    class itself; see docs/adr/0012 for why auth and users are split."""

    __tablename__ = "sessions"
    __table_args__ = (UniqueConstraint("refresh_token_hash", name="uq_sessions_refresh_token_hash"),)

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    # SHA-256 hex digest of the raw opaque token — the raw value is only
    # ever returned to the client once, at issuance/rotation, never stored.
    refresh_token_hash: Mapped[str] = mapped_column(String, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # Captured but not acted on yet (no anomaly detection, no sessions-list
    # UI) — cheap to record now, can't be backfilled onto sessions created
    # before the field existed if a future stage wants it.
    user_agent: Mapped[str | None] = mapped_column(String, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String, nullable=True)
