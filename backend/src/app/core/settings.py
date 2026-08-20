from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    # ── Runtime ───────────────────────────────────────────────────────────────
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    SECRET_KEY: str = "default_secret_key_override_in_env"
    APP_NAME: str = "Enterprise Platform"
    APP_BASE_URL: str = "http://localhost:8000"

    # ── Database ──────────────────────────────────────────────────────────────
    DATABASE_URL: str = "postgresql+asyncpg://app_user:secure_dev_password@localhost:5432/app_db"
    DB_POOL_SIZE: int = 20
    DB_MAX_OVERFLOW: int = 10

    # ── Cache (Valkey) ────────────────────────────────────────────────────────
    VALKEY_HOST: str = "localhost"
    VALKEY_PORT: int = 6379

    # ── Token TTLs ────────────────────────────────────────────────────────────
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    RESET_TOKEN_EXPIRE_MINUTES: int = 60
    VERIFY_TOKEN_EXPIRE_MINUTES: int = 1440  # 24 h

    # ── SMTP / Mail ───────────────────────────────────────────────────────────
    # All SMTP fields are Optional so the mailer degrades gracefully to
    # structlog mock mode when not configured.
    SMTP_HOST: str | None = None
    SMTP_PORT: int = 587
    SMTP_USER: str | None = None
    SMTP_PASSWORD: str | None = None
    SMTP_TLS: bool = True
    EMAILS_FROM_ADDRESS: str = "noreply@platform.internal"
    EMAILS_FROM_NAME: str = "Enterprise Platform"

    # ── Initial Superuser Seeding ─────────────────────────────────────────────
    FIRST_SUPERUSER_EMAIL: str = "admin@platform.internal"
    FIRST_SUPERUSER_PASSWORD: str = "AdminSecurePassword2026!"
    FIRST_SUPERUSER_NAME: str = "Platform Administrator"

    # ── Observability & Crash Reporting ───────────────────────────────────────
    SENTRY_DSN: str | None = None
    SENTRY_TRACES_SAMPLE_RATE: float = 1.0

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def smtp_configured(self) -> bool:
        """True only when all required SMTP credentials are present."""
        return bool(self.SMTP_HOST and self.SMTP_USER and self.SMTP_PASSWORD)


settings = AppSettings()
