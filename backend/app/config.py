import os
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env", "backend/.env", "dukaan-ai/.env", "dukaan-ai/backend/.env"),
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/postgres"
    default_shop_id: str = "00000000-0000-0000-0000-000000000001"
    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash-lite"
    speech_provider: str = "gemini"  # "gemini" | "sarvam" | "gnani"
    sarvam_api_key: str = ""
    gnani_api_key: str = ""
    gnani_stt_url: str = "https://api.gnani.ai/v3/speech-to-text"
    gnani_tts_url: str = "https://api.gnani.ai/v3/text-to-speech"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000,*"
    port: int = 8000

    @property
    def async_database_url(self) -> str:
        url = (
            os.getenv("DATABASE_URL")
            or os.getenv("DATABASE_PUBLIC_URL")
            or os.getenv("DATABASE_PRIVATE_URL")
            or os.getenv("POSTGRES_URL")
            or self.database_url
        )
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgresql://") and not url.startswith("postgresql+asyncpg://"):
            url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
        return url


settings = Settings()
