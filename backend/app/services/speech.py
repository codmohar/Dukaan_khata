"""Provider-agnostic Speech Layer: Gnani Prisma v3.0 / Sarvam AI / Mock.

Handles conversion of 16kHz PCM16 audio to standard RIFF WAV, calls upstream
speech APIs, and handles graceful fallbacks.
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
    """Pack raw 16-bit mono PCM into standard RIFF WAV format."""
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
    """Generate a clean sinusoidal WAV tone for testing or fallback when TTS keys are unavailable."""
    num_samples = int(rate * duration_s)
    pcm = bytearray()
    for i in range(num_samples):
        sample = int(32767.0 * 0.3 * math.sin(2.0 * math.pi * freq * (i / rate)))
        pcm += struct.pack("<h", max(-32768, min(32767, sample)))
    return pcm16_to_wav(bytes(pcm), rate=rate)


async def sarvam_stt(pcm: bytes, language: str = "kn-IN") -> str:
    """Transcribe 16kHz PCM audio using Sarvam AI Saarika."""
    if not settings.sarvam_api_key:
        log.warning("Sarvam API key not configured; returning mock transcription")
        return ""

    # Map language if necessary (Sarvam accepts kn-IN, hi-IN, en-IN)
    lang_code = language if "-" in language else f"{language}-IN"

    # Support already-encoded mobile audio (WAV, M4A/MP4, WebM, OGG) as well as raw 16kHz PCM16
    if pcm[:4] == b"RIFF":
        filename, mime, payload = "audio.wav", "audio/wav", pcm
    elif len(pcm) > 12 and pcm[4:8] == b"ftyp":
        filename, mime, payload = "audio.m4a", "audio/mp4", pcm
    elif pcm[:4] == b"OggS":
        filename, mime, payload = "audio.ogg", "audio/ogg", pcm
    elif pcm[:4] == b"\x1a\x45\xdf\xa3":
        filename, mime, payload = "audio.webm", "audio/webm", pcm
    else:
        filename, mime, payload = "audio.wav", "audio/wav", pcm16_to_wav(pcm, rate=16000)

    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{SARVAM_BASE}/speech-to-text",
                headers={"api-subscription-key": settings.sarvam_api_key},
                files={"file": (filename, io.BytesIO(payload), mime)},
                data={"model": SARVAM_STT_MODEL, "language_code": lang_code},
            )
            response.raise_for_status()
            res_data = response.json()
            return res_data.get("transcript", "").strip()
    except Exception as e:
        log.warning("Sarvam STT failed: %s", e)
        return ""


async def sarvam_tts(text: str, language: str = "kn-IN") -> bytes:
    """Synthesize text into speech audio WAV bytes using Sarvam AI Bulbul."""
    if not settings.sarvam_api_key:
        log.info("Sarvam API key not configured; returning fallback audio tone")
        return generate_beep_wav(0.2)

    lang_code = language if "-" in language else f"{language}-IN"
    try:
        async with httpx.AsyncClient(timeout=8.0) as client:
            response = await client.post(
                f"{SARVAM_BASE}/text-to-speech",
                headers={"api-subscription-key": settings.sarvam_api_key},
                json={
                    "inputs": [text[:500]],
                    "target_language_code": lang_code,
                    "speaker": SARVAM_SPEAKER,
                    "model": SARVAM_TTS_MODEL,
                },
            )
            response.raise_for_status()
            audios = response.json().get("audios", [])
            if audios:
                return base64.b64decode(audios[0])
    except Exception as e:
        log.warning("Sarvam TTS failed: %s; using fallback tone", e)

    return generate_beep_wav(0.2)


async def transcribe(pcm: bytes, language: str = "kn-IN") -> str:
    """Route STT to configured provider (Gnani Prisma with Sarvam fallback, or Sarvam)."""
    provider = settings.speech_provider.lower()
    if provider == "gnani":
        from .stt_gnani import transcribe_gnani
        return await transcribe_gnani(pcm, language)
    elif provider == "sarvam":
        return await sarvam_stt(pcm, language)
    else:
        # Mock mode
        return ""


async def synthesize(text: str, language: str = "kn-IN") -> bytes:
    """Route TTS to configured provider (Gnani Timbre with Sarvam fallback, or Sarvam)."""
    provider = settings.speech_provider.lower()
    if provider == "gnani":
        from .tts_gnani import synthesize_gnani
        return await synthesize_gnani(text, language)
    elif provider == "sarvam":
        return await sarvam_tts(text, language)
    else:
        # Mock mode
        return generate_beep_wav(0.2)
