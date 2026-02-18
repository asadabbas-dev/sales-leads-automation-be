"""Application configuration."""

from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,  # so DB_HOST works regardless of case
    )

    # Database fields (read from .env)
    db_host: str = "localhost"
    db_port: int = 5432
    db_name: str = "lead_ops"
    db_user: str = "postgres"
    db_password: str = "postgres"

    # Construct database URL dynamically
    @property
    def database_url(self) -> str:
        return f"postgresql+asyncpg://{self.db_user}:{self.db_password}@{self.db_host}:{self.db_port}/{self.db_name}"

    # OpenAI (or compatible API)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None  # For Azure/OpenRouter

    # App
    log_level: str = "INFO"


settings = Settings()
