from pydantic import field_validator
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

    @field_validator("jwt_secret_key")
    @classmethod
    def _reject_weak_jwt_secret(cls, value: str) -> str:
        if len(value) < 32:
            raise ValueError("JWT_SECRET_KEY must be at least 32 characters.")
        if value in _PLACEHOLDER_SECRETS:
            raise ValueError("JWT_SECRET_KEY is still set to a placeholder value.")
        return value


settings = Settings()
