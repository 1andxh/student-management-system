from sms.core.exceptions import UnauthorizedError


class InvalidCredentialsError(UnauthorizedError):
    message = "Invalid email or password."


class InactiveUserError(UnauthorizedError):
    message = "This account is inactive."


class InvalidRefreshTokenError(UnauthorizedError):
    # Deliberately the same message/behavior whether the token is unknown,
    # expired, or revoked — mirrors the login-oracle fix in AuthService
    # (docs/adr/0008): distinguishing these would leak session state to an
    # unauthenticated caller.
    message = "Invalid or expired refresh token."
