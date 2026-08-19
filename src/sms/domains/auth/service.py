from datetime import datetime, timedelta, timezone

from sms.core.config import settings
from sms.core.security import (
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_token,
    verify_password,
)
from sms.domains.auth.exceptions import InvalidCredentialsError, InvalidRefreshTokenError
from sms.domains.auth.models import Session, User
from sms.domains.auth.repository import SessionRepository, UserRepository
from sms.domains.auth.schemas import LoginRequest, TokenResponse


class AuthService:
    def __init__(
        self, user_repository: UserRepository, session_repository: SessionRepository
    ) -> None:
        self._users = user_repository
        self._sessions = session_repository

    async def login(
        self,
        data: LoginRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        user = await self._users.get_by_email(data.email)

        # Always verify against *some* hash, even for a nonexistent email,
        # and always raise the same error either way — otherwise "unknown
        # email" responds faster than "wrong password", and a distinct
        # "inactive account" message leaks account state. See docs/adr/0008.
        hashed_password = user.hashed_password if user is not None else DUMMY_PASSWORD_HASH
        password_ok = verify_password(data.password, hashed_password)

        if user is None or not password_ok or not user.is_active:
            raise InvalidCredentialsError()

        access_token = create_access_token(user.id)
        refresh_token = await self._issue_session(user, user_agent, ip_address)
        return TokenResponse(access_token=access_token, refresh_token=refresh_token)

    async def refresh(
        self,
        raw_refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenResponse:
        session = await self._sessions.get_by_token_hash(hash_token(raw_refresh_token))

        now = datetime.now(timezone.utc)
        # Same error for "no such token", "expired", and "revoked" —
        # distinguishing them would leak session state. See docs/adr/0008's
        # login-oracle fix, applied here for the same reason.
        if session is None or session.revoked_at is not None or session.expires_at < now:
            raise InvalidRefreshTokenError()

        # Re-check the account, not just the session — without this, a
        # deactivated user's still-valid refresh token would keep minting
        # access tokens, and the fact that refresh "succeeds then everything
        # else fails" vs. "session revoked, refresh fails immediately" is
        # itself an oracle leaking account state. Same error either way.
        user = await self._users.get(session.user_id)
        if user is None or not user.is_active:
            raise InvalidRefreshTokenError()

        access_token = create_access_token(user.id)
        new_refresh_token = await self._rotate_session(session, user_agent, ip_address)
        return TokenResponse(access_token=access_token, refresh_token=new_refresh_token)

    async def logout(self, raw_refresh_token: str) -> None:
        session = await self._sessions.get_by_token_hash(hash_token(raw_refresh_token))
        if session is None or session.revoked_at is not None:
            return  # Idempotent — an unknown or already-revoked token is not an error.

        session.revoked_at = datetime.now(timezone.utc)
        await self._sessions.add(session)

    async def _issue_session(
        self, user: User, user_agent: str | None, ip_address: str | None
    ) -> str:
        raw_token = generate_refresh_token()
        now = datetime.now(timezone.utc)
        session = Session(
            user_id=user.id,
            refresh_token_hash=hash_token(raw_token),
            expires_at=now + timedelta(days=settings.refresh_token_expire_days),
            last_used_at=now,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        await self._sessions.add(session)
        return raw_token

    async def _rotate_session(
        self, session: Session, user_agent: str | None, ip_address: str | None
    ) -> str:
        raw_token = generate_refresh_token()
        now = datetime.now(timezone.utc)
        rotated = await self._sessions.rotate(
            session.refresh_token_hash,
            hash_token(raw_token),
            now,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        if not rotated:
            # Someone else (a concurrent refresh, or a logout) won the race
            # for this session between our validation check above and now.
            raise InvalidRefreshTokenError()
        return raw_token
