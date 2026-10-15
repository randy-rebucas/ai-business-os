from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """All configuration comes from ABOS_* environment variables (or backend/.env). See backend/.env.example.

    Environments: `development` (local defaults, labelled dev adapters allowed), `test` (pinned by tests/conftest.py),
    `production` (guards below refuse unsafe values at startup).
    """

    model_config = SettingsConfigDict(env_prefix="ABOS_", env_file=".env", extra="ignore")

    env: Literal["development", "test", "production"] = "development"
    # Contains the DB password: kept out of repr() so it never lands in logs or tracebacks.
    database_url: str = Field(default="postgresql+psycopg://abos:abos_dev_password@127.0.0.1:55470/abos", repr=False)
    # The app switches every pooled connection to this role (SET ROLE) so Postgres row-level security applies even
    # when the login user owns the tables (ADR-003). Migrations run as the login user.
    db_app_role: str = "abos_app"
    redis_url: str = "redis://127.0.0.1:56470/0"
    app_base_url: str = "http://localhost:3470"

    session_ttl_hours: int = 24 * 7
    cookie_secure: bool = False
    session_cookie_name: str = "abos_session"

    password_reset_ttl_minutes: int = 30
    email_verify_ttl_hours: int = 48
    login_failure_limit: int = 10
    login_failure_window_minutes: int = 15

    # ---- Rate limits. "<count>/<seconds>" per key; DB-backed fixed windows shared by all instances ----
    rate_limits_enabled: bool = True
    rl_login_ip: str = "60/900"
    rl_register_ip: str = "20/3600"
    rl_password_reset_ip: str = "10/3600"  # noqa: S105 (a rate, not a secret)
    rl_password_reset_email: str = "3/3600"  # noqa: S105
    rl_verify_resend_user: str = "5/3600"
    rl_sensitive_user: str = "20/3600"
    rl_ask_user: str = "120/3600"
    # Work that costs model calls or worker time: generation, simulations, runs, reports, extraction, ingestion.
    rl_ai_work_user: str = "60/3600"
    rl_ai_work_org: str = "300/3600"
    rl_export_user: str = "5/86400"

    # ---- Data retention & deletion (Phase 7, docs/OPERATIONS.md) ----
    # The worker (housekeeping) connects as the table owner for organization deletion and purges: the app role
    # can't delete write-once evidence or insert-only ledgers. Empty = ABOS_DATABASE_URL without SET ROLE (dev).
    maintenance_database_url: SecretStr | None = None
    org_deletion_grace_hours: int = 72
    export_ttl_hours: int = 72
    job_runs_retention_days: int = 90
    sessions_retention_days: int = 30
    auth_events_retention_days: int = 365
    outbox_retention_days: int = 90

    # ---- Observability ----
    # GET /api/metrics (Prometheus text) needs `Authorization: Bearer <token>`; unset = endpoint disabled (404).
    metrics_token: SecretStr | None = None
    error_reporter: Literal["log", "sentry"] = "log"
    sentry_dsn: SecretStr | None = None

    # ---- Mail ----
    mailer: Literal["dev_outbox", "smtp"] = "dev_outbox"
    mail_from: str = "AI Business OS <no-reply@localhost>"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: SecretStr | None = None
    smtp_starttls: bool = True
    smtp_timeout_seconds: float = 10.0

    # ---- Notifications (Phase 6). SMS goes through a provider adapter; "dev" stores messages, "none" disables SMS.
    sms_provider: Literal["dev", "none"] = "dev"
    notify_email_per_hour: int = 20   # immediate emails per user per hour; more wait for the digest
    notify_sms_per_day: int = 10      # SMS per user per day
    notify_max_attempts: int = 5      # delivery attempts before a delivery is abandoned (backoff 2, 4, 8, … minutes)

    # ---- Object storage (ADR-011). local = files under storage_dir (dev); s3 = any S3-compatible bucket ----
    storage_backend: Literal["local", "s3"] = "local"
    storage_dir: str = "storage"
    s3_bucket: str | None = None
    s3_endpoint_url: str | None = None
    s3_region: str | None = None
    upload_max_bytes: int = 20 * 1024 * 1024
    url_fetch_max_bytes: int = 5 * 1024 * 1024
    url_fetch_timeout_seconds: float = 10.0

    # ---- Background jobs (ADR-008) ----
    jobs_eager: bool = False  # run jobs inline after commit (tests, single-process dev without a worker)
    job_max_attempts: int = 3
    job_timeout_seconds: int = 600  # a running job with no heartbeat for this long is considered lost

    # ---- AI layer (ADR-012). "dev" providers are deterministic, labelled, and never call a model. ----
    llm_provider: Literal["dev", "anthropic"] = "dev"
    anthropic_api_key: SecretStr | None = None
    llm_model: str = "claude-opus-5-5"            # reasoning / answers
    llm_analysis_model: str = "claude-opus-5-5"   # document analysis (summaries, classification)
    llm_effort: Literal["low", "medium", "high", "xhigh", "max"] = "medium"
    llm_max_output_tokens: int = 16000
    llm_timeout_seconds: float = 120.0
    embedding_provider: Literal["hash", "voyage", "openai"] = "hash"
    embedding_model: str = "voyage-3.5"
    embedding_api_key: SecretStr | None = None
    embedding_base_url: str | None = None  # openai-compatible endpoint override
    embedding_dimensions: int = 1024  # fixed by the vector(1024) column (migration 0002)

    # ---- Retrieval ----
    retrieval_top_k: int = 8
    retrieval_candidates: int = 40   # per retriever, before fusion
    retrieval_min_vector_score: float = 0.25  # cosine similarity below which a vector-only hit doesn't count

    # Only used by `python -m abos.seed`, which refuses to run in production.
    seed_password: str = "dev-password-change-me"  # noqa: S105
    log_level: str = "INFO"

    @property
    def smtp_configured(self) -> bool:
        return bool(self.smtp_host)

    @property
    def llm_configured(self) -> bool:
        return self.llm_provider == "dev" or bool(self.anthropic_api_key and self.anthropic_api_key.get_secret_value())

    @property
    def embeddings_configured(self) -> bool:
        return self.embedding_provider == "hash" or bool(
            self.embedding_api_key and self.embedding_api_key.get_secret_value())

    @model_validator(mode="after")
    def _production_guards(self) -> "Settings":
        if self.env == "production":
            if not self.cookie_secure:
                raise ValueError("ABOS_COOKIE_SECURE must be true in production")
            if not self.session_cookie_name.startswith("__Host-"):
                raise ValueError("ABOS_SESSION_COOKIE_NAME must use the __Host- prefix in production")
            if "abos_dev_password" in self.database_url:
                raise ValueError("ABOS_DATABASE_URL uses the development password in production")
            if not self.app_base_url.startswith("https://"):
                raise ValueError("ABOS_APP_BASE_URL must be https in production")
            if self.mailer == "dev_outbox":
                raise ValueError("ABOS_MAILER=dev_outbox stores mail instead of sending it; configure smtp")
            if self.mailer == "smtp" and not self.smtp_configured:
                raise ValueError("ABOS_MAILER=smtp needs ABOS_SMTP_HOST")
            if self.llm_provider == "dev" or self.embedding_provider == "hash":
                raise ValueError("Development AI adapters (llm dev / embeddings hash) are not allowed in production")
            if self.sms_provider == "dev":
                raise ValueError("ABOS_SMS_PROVIDER=dev stores SMS instead of sending them; use none or a provider")
            if self.storage_backend == "local":
                raise ValueError("ABOS_STORAGE_BACKEND=local is for development; use s3 in production")
            if self.jobs_eager:
                raise ValueError("ABOS_JOBS_EAGER must be false in production (run a worker)")
            if not self.rate_limits_enabled:
                raise ValueError("ABOS_RATE_LIMITS_ENABLED must stay true in production")
            if self.error_reporter == "sentry" and not self.sentry_dsn:
                raise ValueError("ABOS_ERROR_REPORTER=sentry needs ABOS_SENTRY_DSN")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
