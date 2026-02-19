from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field


class Settings(BaseSettings):
    """App settings loaded from environment / .env file."""

    # ── Database ────────────────────────────────────────────────────────────
    db_host: str = Field(..., env="DB_HOST")
    db_port: int = Field(..., env="DB_PORT")
    db_name: str = Field(..., env="DB_NAME")
    db_user: str = Field(..., env="DB_USER")
    db_password: str = Field(..., env="DB_PASSWORD")

    # ── OpenAI ──────────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", env="OPENAI_MODEL")
    # Optional: override to use a custom / proxy OpenAI-compatible base URL.
    # Leave unset (or empty string) to use the official OpenAI endpoint.
    openai_base_url: str | None = Field(None, env="OPENAI_BASE_URL")

    # ── App ─────────────────────────────────────────────────────────────────
    log_level: str = Field("INFO", env="LOG_LEVEL")
    # Maximum JSON payload size accepted by /enrich-lead (bytes). Default 64 KB.
    max_payload_bytes: int = Field(65536, env="MAX_PAYLOAD_BYTES")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )


settings = Settings()