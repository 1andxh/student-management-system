from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class PinLoginRequest(BaseModel):
    student_number: str
    pin: str


class TokenPair(BaseModel):
    """What AuthService returns: both tokens, as a pair. Deliberately not
    named *Response* and not exported from the package: it must never be a
    route's response_model, or the refresh token is back in a body
    JavaScript can read. Never sent to a client as-is — the router splits it, putting the access token in the
    body (AccessTokenResponse) and the refresh token in an HttpOnly cookie
    (docs/adr/0027). Keeping the service transport-agnostic is deliberate:
    cookies are an HTTP concern, so they stay at the HTTP boundary."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class AccessTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
