from sms.core.exceptions import PermissionDeniedError, UnauthorizedError


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


class DisallowedOriginError(PermissionDeniedError):
    # Raised by the cookie-authenticated routes (/auth/refresh, /auth/logout)
    # when a browser says the request came from an origin not in
    # settings.cors_origins — a forged cross-origin request (CSRF). See
    # docs/adr/0027. Not an oracle concern: the Origin is the caller's own.
    message = "Request origin not allowed."
