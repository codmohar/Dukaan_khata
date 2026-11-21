"""Provider-agnostic STT/TTS. Sarvam is the default; Gnani wrappers live in stt_gnani.py / tts_gnani.py.
Includes fallback support for Gemini speech and graceful tone synthesis.
"""
import base64
import io
import logging
import math
import struct

import httpx

from ..config import settings

log = logging.getLogger("dukaan.speech")

SARVAM_BASE = "https://api.sarvam.ai"
SARVAM_STT_MODEL = "saarika:v2.5"
SARVAM_TTS_MODEL = "bulbul:v3"
SARVAM_SPEAKER = "kavya"


def pcm16_to_wav(pcm: bytes, rate: int = 16000) -> bytes:
    """Pack raw 16-bit mono PCM into standard RIFF WAV format. If already WAV, return as is."""
    if len(pcm) >= 12 and pcm[:4] == b"RIFF" and pcm[8:12] == b"WAVE":
        return pcm
    hdr = (
        b"RIFF"
        + struct.pack("<I", 36 + len(pcm))
        + b"WAVEfmt "
        + struct.pack("<IHHIIHH", 16, 1, 1, rate, rate * 2, 2, 16)
        + b"data"
        + struct.pack("<I", len(pcm))
    )
    return hdr + pcm


def generate_beep_wav(duration_s: float = 0.25, freq: float = 440.0, rate: int = 16000) -> bytes:
    """Generate a clean sinusoidal WAV tone as reliable fallback."""
    num_samples = int(rate * duration_s)
    pcm = bytearray()
    for i in range(num_samples):
        sample = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * (i / rate)))
        pcm += struct.pack("<h", max(-32768, min(32767, sample)))
    return pcm16_to_wav(bytes(pcm), rate=rate)


async def _sarvam_stt(pcm: bytes, language: str) -> str:
    """Transcribe audio via Sarvam Saarika v2.5."""
    if not settings.sarvam_api_key:
        return ""
    lang_code = language if "-" in language else f"{language}-IN"
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{SARVAM_BASE}/speech-to-text",
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={"file": ("audio.wav", io.BytesIO(pcm16_to_wav(pcm)), "audio/wav")},
                data={"model": SARVAM_STT_MODEL, "language_code": lang_code},
            )
            if r.status_code == 200:
                return r.json().get("transcript", "").strip()
            else:
                log.warning("Sarvam STT returned status %d: %s", r.status_code, r.text[:200])
    except Exception as ex:
        log.warning("Sarvam STT error: %s", ex)
    return ""


async def _sarvam_tts(text: str, language: str) -> bytes:
    """Synthesize text to speech via Sarvam Bulbul."""
    if not settings.sarvam_api_key:
        return generate_beep_wav()
    lang_code = language if "-" in language else f"{language}-IN"
    clean_text = text[:500].strip()
    if not clean_text:
        return generate_beep_wav()
    try:
        async with httpx.AsyncClient(timeout=10) as c:
            r = await c.post(
                f"{SARVAM_BASE}/text-to-speech",
                headers={"api-subscription-key": settings.sarvam_api_key},
                json={
                    "inputs": [clean_text],
                    "target_language_code": lang_code,
                    "speaker": SARVAM_SPEAKER,
                    "model": SARVAM_TTS_MODEL,
                },
            )
            if r.status_code == 200:
                return base64.b64decode(r.json()["audios"][0])
            else:
                log.warning("Sarvam TTS returned status %d: %s", r.status_code, r.text[:200])
    except Exception as ex:
        log.warning("Sarvam TTS error: %s", ex)
    return generate_beep_wav()


async def _gemini_stt(pcm: bytes, language: str) -> str:
    """Transcribe audio via Gemini Multimodal STT."""
    try:
        from google import genai
        from google.genai import types
        client = genai.Client(api_key=settings.gemini_api_key)
        wav_data = pcm16_to_wav(pcm)
        prompt = (
            f"Listen carefully to this Indian Kirana shop audio ({language}). "
            "Transcribe the EXACT words spoken into Latin/English or native script. "
            "Return ONLY the plain transcript text, nothing else."
        )
        resp = await client.aio.models.generate_content(
            model=settings.gemini_model,
            contents=[
                types.Part.from_bytes(data=wav_data, mime_type="audio/wav"),
                prompt,
            ],
        )
        return (resp.text or "").strip()
    except Exception as e:
        log.warning("Gemini STT notice: %s", e)
        return ""


async def transcribe(pcm: bytes, language: str = "kn-IN") -> str:
    """Transcribe audio with configured provider and fallback."""
    provider = (settings.speech_provider or "sarvam").lower()

    if provider == "gnani":
        try:
            from .stt_gnani import transcribe_gnani
            res = await transcribe_gnani(pcm, language)
            if res:
                return res
        except Exception as e:
            log.warning("Gnani STT failed, falling back: %s", e)

    # 1. Try Sarvam
    res = await _sarvam_stt(pcm, language)
    if res:
        return res

    # 2. Fallback to Gemini
    if settings.gemini_api_key:
        gem_text = await _gemini_stt(pcm, language)
        if gem_text:
            return gem_text

    return ""


async def synthesize(text: str, language: str = "kn-IN") -> bytes:
    """Synthesize speech with configured provider and graceful fallback."""
    provider = (settings.speech_provider or "sarvam").lower()

    if provider == "gnani":
        try:
            from .tts_gnani import synthesize_gnani
            return await synthesize_gnani(text, language)
        except Exception as e:
            log.warning("Gnani TTS failed: %s", e)

    # Attempt Sarvam
    try:
        wav = await _sarvam_tts(text, language)
        if wav and len(wav) > 100:
            return wav
    except Exception as e:
        log.warning("Sarvam TTS notice: %s", e)

    return generate_beep_wav()
