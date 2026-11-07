from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Known placeholder values that must never be used as a real secret — a
# forgeable JWT_SECRET_KEY is a full auth-bypass, so this fails app startup
# (fail-closed) rather than silently accepting one.
_PLACEHOLDER_SECRETS = {"change-me-in-.env-only", "secret", "changeme"}


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    env: str = "local"
    log_level: str = "INFO"

    database_url: str
    database_url_test: str

    jwt_secret_key: str
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 30
    # The refresh-token cookie's Secure flag (docs/adr/0027). Defaults to
    # True — fail-closed, same posture as the JWT secret check below — so a
    # deployment that forgets to set it never sends the token over plain
    # http. Only a local .env should ever turn it off, and only if a browser
    # refuses Secure cookies on http://127.0.0.1 (Chrome and Firefox accept
    # them there; that's why the default can stay True even locally).
    # Turning it off outside env=local fails startup (validator below).
    refresh_cookie_secure: bool = True

    # Browser origins allowed to call the API with credentials (the refresh
    # cookie). Also the allowlist /auth/refresh and /auth/logout check the
    # Origin header against (CSRF; docs/adr/0027). Set via CORS_ORIGINS as
    # a JSON list. "*" is rejected below.
    cors_origins: list[str] = ["http://127.0.0.1:5173"]

    upload_dir: str = "uploads"

    @field_validator("jwt_secret_key")
    @classmethod
    def _reject_weak_jwt_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")
        if value in _PLACEHOLDER_SECRETS:
            raise ValueError("JWT_SECRET_KEY is still set to a placeholder value.")
        return value

    @field_validator("cors_origins")
    @classmethod
    def _reject_wildcard_origin(cls, value: list[str]) -> list[str]:
        # With allow_credentials=True, Starlette doesn't refuse "*" — it
        # echoes back whatever Origin the request sent, making every site a
        # credentialed origin. Fail startup instead.
        if "*" in value:
            raise ValueError("CORS_ORIGINS may not contain '*' (credentials are enabled).")
        return value

    @model_validator(mode="after")
    def _require_secure_cookie_outside_local(self) -> "Settings":
        if self.env != "local" and not self.refresh_cookie_secure:
            raise ValueError("REFRESH_COOKIE_SECURE may only be false when ENV=local.")
        return self


settings = Settings()
