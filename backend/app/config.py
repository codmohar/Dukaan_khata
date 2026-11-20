import os

def _load_env_fallback():
    here = os.path.dirname(os.path.abspath(__file__))
    candidates = [
        os.path.join(here, "..", ".env"),
        os.path.join(here, "..", "..", ".env"),
        ".env",
        "backend/.env",
        "dukaan-ai/backend/.env",
    ]
    for env_path in candidates:
        if os.path.isfile(env_path):
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip().strip("\"'")
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass

_load_env_fallback()

try:
    from pydantic_settings import BaseSettings, SettingsConfigDict

    class Settings(BaseSettings):
        model_config = SettingsConfigDict(extra="ignore")

        database_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/dukaan"
        )
        default_shop_id: str = os.getenv(
            "DEFAULT_SHOP_ID",
            "00000000-0000-0000-0000-000000000001"
        )
        gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

        speech_provider: str = os.getenv("SPEECH_PROVIDER", "sarvam")  # "gnani" | "sarvam" | "mock"
        sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")

        gnani_api_key: str = os.getenv("GNANI_API_KEY", "")
        gnani_stt_url: str = os.getenv("GNANI_STT_URL", "https://api.gnani.ai/v3/speech-to-text")
        gnani_tts_url: str = os.getenv("GNANI_TTS_URL", "https://api.gnani.ai/v3/text-to-speech")

        cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,*")
        port: int = int(os.getenv("PORT", "8000"))

    settings = Settings()

except Exception:
    from pydantic import BaseModel

    class SettingsFallback(BaseModel):
        database_url: str = os.getenv(
            "DATABASE_URL",
            "postgresql+asyncpg://postgres:postgres@localhost:5432/dukaan"
        )
        default_shop_id: str = os.getenv(
            "DEFAULT_SHOP_ID",
            "00000000-0000-0000-0000-000000000001"
        )
        gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
        gemini_model: str = os.getenv("GEMINI_MODEL", "gemini-3-flash-preview")

        speech_provider: str = os.getenv("SPEECH_PROVIDER", "sarvam")
        sarvam_api_key: str = os.getenv("SARVAM_API_KEY", "")

        gnani_api_key: str = os.getenv("GNANI_API_KEY", "")
        gnani_stt_url: str = os.getenv("GNANI_STT_URL", "https://api.gnani.ai/v3/speech-to-text")
        gnani_tts_url: str = os.getenv("GNANI_TTS_URL", "https://api.gnani.ai/v3/text-to-speech")

        cors_origins: str = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000,*")
        port: int = int(os.getenv("PORT", "8000"))

    settings = SettingsFallback()
