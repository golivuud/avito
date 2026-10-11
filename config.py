from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    BOT_TOKEN: SecretStr
    ADMIN_ID: int

    DB_NAME: str = "avito_db"
    DB_USER: str = "bot_user"
    DB_PASSWORD: str = "123"
    DB_HOST: str = "localhost"
    DB_PORT: int = 5432

    GMAIL_USER: str = ""
    GMAIL_APP_PASSWORD: SecretStr = SecretStr("")
    IMAP_SERVER: str = "imap.gmail.com"
    CHECK_INTERVAL: int = 15

    PROXY_URL: str | None = None

    @property
    def db_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASSWORD}@"
            f"{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"
        )


settings = Settings()
