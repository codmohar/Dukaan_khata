"""Gnani Prisma v3.0 Speech-To-Text (STT) Client Wrapper.

Supports kn-IN, hi-IN, en-IN code-mixed audio (16kHz PCM).
Provides automatic fallback to Sarvam AI (saarika) if Gnani is unconfigured or fails.
"""
import io
import logging
from typing import Optional

import httpx

from ..config import settings
from .speech import pcm16_to_wav

log = logging.getLogger("dukaan.stt.gnani")

# Normalized language mapping for Gnani Prisma
GNANI_LANG_MAP = {
    "kn-IN": "kn-IN",
    "hi-IN": "hi-IN",
    "en-IN": "en-IN",
    "kn": "kn-IN",
    "hi": "hi-IN",
    "en": "en-IN",
}


async def transcribe_gnani(pcm: bytes, language: str = "kn-IN") -> str:
    """Transcribe 16kHz PCM audio using Gnani Prisma v3.0 API.

    Gracefully falls back to Sarvam AI if Gnani keys/endpoint are not configured or request fails.
    """
    if not settings.gnani_api_key or not settings.gnani_stt_url:
        log.info("Gnani credentials missing, falling back to Sarvam AI STT")
        from .speech import sarvam_stt
        return await sarvam_stt(pcm, language)

    target_lang = GNANI_LANG_MAP.get(language, "kn-IN")
    wav_bytes = pcm16_to_wav(pcm, rate=16000)

    headers = {
        "Authorization": f"Bearer {settings.gnani_api_key}",
        "token": settings.gnani_api_key,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            files = {
                "audio": ("audio.wav", io.BytesIO(wav_bytes), "audio/wav"),
            }
            data = {
                "language": target_lang,
                "language_code": target_lang,
                "encoding": "LINEAR16",
                "sample_rate": "16000",
                "audio_format": "wav",
            }

            response = await client.post(
                settings.gnani_stt_url,
                headers=headers,
                files=files,
                data=data,
            )

            if response.status_code == 200:
                res_json = response.json()
                # Parse multiple common Gnani response formats
                transcript = (
                    res_json.get("transcript")
                    or res_json.get("text")
                    or (res_json.get("data") or {}).get("asr_output")
                    or res_json.get("asr_output")
                    or ""
                ).strip()
                if transcript:
                    return transcript

            log.warning("Gnani STT returned status %d: %s; trying fallback", response.status_code, response.text[:200])

    except Exception as e:
        log.warning("Gnani STT call failed: %s; invoking Sarvam fallback", e)

    # Fallback to Sarvam AI
    from .speech import sarvam_stt
    return await sarvam_stt(pcm, language)
