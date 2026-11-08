from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sms.core.config import settings
from sms.core.security import (
    derive_successor_token,
    DUMMY_PASSWORD_HASH,
    create_access_token,
    generate_refresh_token,
    hash_token,
    verify_password,
)
from sms.domains.auth.exceptions import InvalidCredentialsError, InvalidRefreshTokenError
from sms.domains.auth.models import Session
from sms.domains.auth.repository import SessionRepository
from sms.domains.auth.schemas import LoginRequest, PinLoginRequest, TokenPair
from sms.domains.students.repository import StudentRepository
from sms.domains.users.models import User, UserRole
from sms.domains.users.repository import UserRepository


class AuthService:
    """Self-service login/refresh/logout. Depends on the users domain's
    model and repository (to look up who's logging in) — see docs/adr/0012
    for why this is a one-way dependency, not a reason to fold users into
    this domain. Also depends on students (for the PIN login path) — a
    second one-way fan-in dependency, same non-circular shape as every
    other cross-domain dependency in this codebase (students doesn't
    depend back on auth for its own core logic)."""

    def __init__(
        self,
        user_repository: UserRepository,
        session_repository: SessionRepository,
        student_repository: StudentRepository,
    ) -> None:
        self._users = user_repository
        self._sessions = session_repository
        self._students = student_repository

    async def login(
        self,
        data: LoginRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
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
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    async def login_with_pin(
        self,
        data: PinLoginRequest,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        student = await self._students.get_by_student_number(data.student_number)

        # Always look up a user, on every branch — a random nonexistent id
        # when there's no real linked user — so this performs the same
        # number of DB round-trips regardless of whether student_number or
        # the link exists. A conditional second query here would be a
        # timing side-channel letting an attacker distinguish "no such
        # student_number" from "student_number exists" before ever
        # touching the PIN, undermining the oracle defense below the same
        # way a distinguishing error message would.
        lookup_user_id = (
            student.user_id if (student is not None and student.user_id is not None) else uuid4()
        )
        user = await self._users.get(lookup_user_id)

        # Same oracle-defense shape as login(): always verify against
        # *some* hash regardless of whether the student/pin/link exists,
        # and raise the identical error for every failure branch — no
        # student, no pin set, no linked user, wrong pin, inactive
        # account. See docs/adr/0008.
        hashed_pin = (
            student.pin_hash if (student is not None and student.pin_hash) else DUMMY_PASSWORD_HASH
        )
        pin_ok = verify_password(data.pin, hashed_pin)

        if (
            student is None
            or student.pin_hash is None
            or user is None
            or user.role != UserRole.STUDENT
            or not pin_ok
            or not user.is_active
        ):
            raise InvalidCredentialsError()

        access_token = create_access_token(user.id)
        refresh_token = await self._issue_session(user, user_agent, ip_address)
        return TokenPair(access_token=access_token, refresh_token=refresh_token)

    async def refresh(
        self,
        raw_refresh_token: str,
        user_agent: str | None = None,
        ip_address: str | None = None,
    ) -> TokenPair:
        presented = hash_token(raw_refresh_token)
        # Deterministic (docs/adr/0031): every refresh with this token, and
        # every replay of it, computes the same next token.
        successor = derive_successor_token(raw_refresh_token)
        successor_hash = hash_token(successor)

        # Two attempts, not one: a reload can abort a refresh in the browser
        # while the server is still processing it, so the next page's
        # refresh arrives with the same token. It may read that token as
        # *current*, then lose the compare-and-swap to the first request.
        # Re-reading then finds it in the grace slot, already rotated to the
        # very successor this request would have produced.
        for _ in range(2):
            now = datetime.now(timezone.utc)
            session = await self._sessions.get_for_refresh(
                presented, now - timedelta(seconds=settings.refresh_grace_seconds)
            )

            # Same error for "no such token", "past its grace window",
            # "expired" and "revoked" — distinguishing them would leak
            # session state. See docs/adr/0008's login-oracle fix.
            if session is None or session.revoked_at is not None or session.expires_at < now:
                raise InvalidRefreshTokenError()

            # Re-check the account, not just the session — without this, a
            # deactivated user's still-valid refresh token would keep minting
            # access tokens, and "refresh succeeds then everything else
            # fails" vs. "refresh fails" would itself leak account state.
            user = await self._users.get(session.user_id)
            if user is None or not user.is_active:
                raise InvalidRefreshTokenError()

            if session.refresh_token_hash == presented:
                # Normal rotation: the presented token becomes the previous
                # one, and its grace window starts now.
                rotated = await self._sessions.rotate(
                    session.id,
                    presented,
                    successor_hash,
                    presented,
                    now,
                    now,
                    user_agent=user_agent,
                    ip_address=ip_address,
                )
                if not rotated:
                    continue  # a concurrent request moved it first; re-read
            elif session.refresh_token_hash != successor_hash:
                # The previous token, but the session has since moved past
                # its successor: this replay can't be honoured.
                raise InvalidRefreshTokenError()
            # else: a replay of the previous token within its window. Its
            # successor is already current, so answer with it and write
            # nothing — no second token minted, nothing retired, and the
            # window stays anchored to the original rotation by construction.

            return TokenPair(access_token=create_access_token(user.id), refresh_token=successor)

        # Lost the race twice: something else (a logout, more concurrent
        # refreshes) keeps moving the session. Treat as any invalid token.
        raise InvalidRefreshTokenError()

    async def logout(self, raw_refresh_token: str) -> None:
        # Honours the grace slot too: a browser that lost a rotation response
        # holds the *previous* token, and logging out with it must still end
        # the session — not leave it alive under a token nobody has.
        now = datetime.now(timezone.utc)
        session = await self._sessions.get_for_refresh(
            hash_token(raw_refresh_token), now - timedelta(seconds=settings.refresh_grace_seconds)
        )
        if session is None or session.revoked_at is not None:
            return  # Idempotent — an unknown or already-revoked token is not an error.

        session.revoked_at = now
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
