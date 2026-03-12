from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    openai_api_key: str = ""
    openai_model: str = "gpt-4o"
    log_level: str = "INFO"

    @property
    def sync_database_url(self) -> str:
        """Alembic needs a synchronous driver, so we swap asyncpg for psycopg2."""
        return self.database_url.replace("postgresql+asyncpg", "postgresql+psycopg2")


settings = Settings()
