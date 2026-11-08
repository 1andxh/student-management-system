import base64
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from sms.core.config import settings

_password_hasher = PasswordHasher()

# A real Argon2 hash of a value nobody will ever type, used so login can pay
# the same hashing cost for a nonexistent email as for a real one — without
# this, "unknown email" returns faster than "wrong password", letting an
# attacker enumerate valid emails by timing alone. See docs/adr/0008.
DUMMY_PASSWORD_HASH = PasswordHasher().hash("dummy-password-for-constant-time-login")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    try:
        _password_hasher.verify(hashed_password, password)
        return True
    except VerifyMismatchError:
        return False


def create_access_token(subject: UUID) -> str:
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.jwt_access_token_expire_minutes
    )
    payload = {"sub": str(subject), "exp": expires_at}
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> UUID | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError:
        return None

    subject = payload.get("sub")
    if subject is None:
        return None
    try:
        return UUID(subject)
    except ValueError:
        return None


def generate_refresh_token() -> str:
    """A high-entropy opaque secret (not a JWT) — this is what makes a
    session actually revocable, unlike a bearer JWT that stays valid until
    it naturally expires. See docs/adr/0009."""
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    """Plain SHA-256, deliberately not Argon2 — the input already has ~256
    bits of entropy from generate_refresh_token, so a slow KDF (meant for
    low-entropy human passwords) buys no security here, only latency."""
    return hashlib.sha256(raw_token.encode()).hexdigest()


# Domain separation: the JWT secret also signs access tokens (HS256 over
# "header.payload"), so derivations made with it are labelled and can never
# collide with, or stand in for, a JWT signature.
_ROTATION_LABEL = b"sms/refresh-rotation/v1\x00"


def derive_successor_token(raw_token: str) -> str:
    """The refresh token that replaces `raw_token` on rotation: an HMAC of
    it under a server secret, so it is unpredictable without the secret but
    the *same* every time (docs/adr/0031).

    That determinism is what makes rotation safe to replay: a reload's
    aborted refresh still running on the server and the new page's refresh
    both compute the same next token, so whichever finishes last can't
    retire the cookie the browser actually kept. With a random successor,
    each replay minted a different one and the last writer won.

    Keyed from JWT_SECRET_KEY (decided over a separate secret, to avoid
    another env var): anyone holding that secret can already mint access
    tokens, so deriving refresh successors from it adds no new exposure.
    Rotating JWT_SECRET_KEY ends every session's chain, as it already ends
    every access token. Same shape as generate_refresh_token: 256 bits,
    base64url, no padding."""
    digest = hmac.new(
        settings.jwt_secret_key.encode(), _ROTATION_LABEL + raw_token.encode(), hashlib.sha256
    ).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
