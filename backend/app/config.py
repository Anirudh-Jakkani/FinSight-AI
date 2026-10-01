"""Central settings, read from environment / .env. Secrets never live in code."""
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg2://finsight:finsight@localhost:5432/finsight"

    # Phase 8.9: Render (and Heroku-style platforms generally) hand out connection
    # strings as postgres://... — SQLAlchemy has not recognized that bare "postgres"
    # dialect name since 1.4 and raises NoSuchModuleError on it. A bare postgresql://
    # (no driver suffix) would work today since psycopg2 is the only driver installed,
    # but only by implicit default; normalizing it too makes the driver explicit
    # rather than an accident of what else happens to be installed. Existing
    # configuration already using postgresql+psycopg2:// (local .env, docker-compose)
    # is untouched by this — it's a no-op for anything already in that form.
    @field_validator("database_url")
    @classmethod
    def _normalize_database_url(cls, v: str) -> str:
        for scheme in ("postgres://", "postgresql://"):
            if v.startswith(scheme):
                return "postgresql+psycopg2://" + v[len(scheme):]
        return v
    llm_provider: str = ""
    llm_api_key: str = ""   # never log or return this value
    llm_model: str = ""
    max_upload_mb: int = 10

    # Phase 4.1: AI financial assistant, routed through OpenRouter (openrouter.ai)
    # rather than calling a model provider's API directly — Gemini's direct API kept
    # retiring models / hitting free-tier quota limits for this project, and
    # OpenRouter's one endpoint fronts many providers/models instead.
    openrouter_api_key: str = ""   # never log or return this value
    openrouter_model: str = "nvidia/nemotron-3-ultra-550b-a55b:free"

    # Phase 7.1: user authentication (signup/login). JWT_SECRET_KEY signs access
    # tokens — unlike the AI provider keys above, this isn't an external credential
    # the user brings; it's generated once for this deployment and must never be
    # empty in practice (an empty secret would make tokens forgeable), so the auth
    # service refuses to issue/verify tokens if it's unset rather than falling back
    # to a guessable default.
    jwt_secret_key: str = ""   # never log or return this value
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 1440  # 24h

    # Phase 8.2: production-readiness fixes (audit: no CORS policy, no logging).
    # Comma-separated, not a JSON list — easier to edit by hand in a plain .env
    # file. Defaults cover the local dev proxy (frontend/serve.py) on port 5500;
    # a real deployment should set this to its actual frontend origin(s) and
    # must never use "*" here (this app sends an Authorization header, and a
    # wildcard origin is bad practice regardless of whether credentials are used).
    cors_allowed_origins: str = "http://localhost:5500,http://127.0.0.1:5500"
    log_level: str = "INFO"


settings = Settings()
