"""Gnani Timbre v3.0 Text-To-Speech (TTS) Client Wrapper.

Synthesizes natural regional voice readbacks for kn-IN, hi-IN, en-IN.
Provides automatic fallback to Sarvam AI (bulbul) if Gnani is unconfigured or fails.
"""
import base64
import logging

import httpx

from ..config import settings

log = logging.getLogger("dukaan.tts.gnani")

GNANI_TTS_LANG_MAP = {
    "kn-IN": "kn-IN",
    "hi-IN": "hi-IN",
    "en-IN": "en-IN",
    "kn": "kn-IN",
    "hi": "hi-IN",
    "en": "en-IN",
}


async def synthesize_gnani(text: str, language: str = "kn-IN") -> bytes:
    """Synthesize speech using Gnani Timbre v3.0 API.

    Gracefully falls back to Sarvam AI if Gnani is unconfigured or request fails.
    """
    if not settings.gnani_api_key or not settings.gnani_tts_url:
        log.info("Gnani TTS credentials missing, falling back to Sarvam AI TTS")
        from .speech import sarvam_tts
        return await sarvam_tts(text, language)

    target_lang = GNANI_TTS_LANG_MAP.get(language, "kn-IN")
    headers = {
        "Authorization": f"Bearer {settings.gnani_api_key}",
        "token": settings.gnani_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text[:500],
        "language": target_lang,
        "language_code": target_lang,
        "audio_format": "wav",
        "speed": 1.0,
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                settings.gnani_tts_url,
                headers=headers,
                json=payload,
            )

            if response.status_code == 200:
                ct = response.headers.get("content-type", "")
                if "audio" in ct or response.content.startswith(b"RIFF"):
                    return response.content
                # Check for base64 JSON response
                try:
                    data = response.json()
                    b64_audio = data.get("audio") or data.get("audio_content") or data.get("data")
                    if b64_audio:
                        return base64.b64decode(b64_audio)
                except Exception:
                    pass
                if len(response.content) > 100:
                    return response.content

            log.warning("Gnani TTS status %d: %s; invoking Sarvam fallback", response.status_code, response.text[:200])

    except Exception as e:
        log.warning("Gnani TTS call failed: %s; invoking Sarvam fallback", e)

    # Fallback to Sarvam AI
    from .speech import sarvam_tts
    return await sarvam_tts(text, language)
