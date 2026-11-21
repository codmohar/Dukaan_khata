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
        log.warning("Sarvam STT failed: %s; falling back to Gemini audio understanding", e)
        return ""


async def gemini_stt(pcm: bytes, language: str = "kn-IN") -> str:
    """Transcribe audio using Gemini multimodal understanding as high-accuracy fallback."""
    if not settings.gemini_api_key:
        return ""
    try:
        if pcm[:4] == b"RIFF":
            payload, mime = pcm, "audio/wav"
        elif len(pcm) > 12 and pcm[4:8] == b"ftyp":
            payload, mime = pcm, "audio/mp4"
        elif pcm[:4] == b"OggS":
            payload, mime = pcm, "audio/ogg"
        elif pcm[:4] == b"\x1a\x45\xdf\xa3":
            payload, mime = pcm, "audio/webm"
        else:
            payload, mime = pcm16_to_wav(pcm, rate=16000), "audio/wav"

        wav_b64 = base64.b64encode(payload).decode("ascii")
        prompt = (
            f"You are a speech-to-text transcriber for an Indian Kirana grocery shop assistant. "
            f"Transcribe the following spoken audio accurately into text in {language} (Kannada, Hindi, or Indian English). "
            f"Only return the exact spoken words as plain text. Do not add quotes, notes, formatting, or timestamps. "
            f"If there is only background silence, ambient static, music tone, or no human speech, reply with [SILENT]."
        )
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.5-flash-lite:generateContent?key={settings.gemini_api_key}"
        async with httpx.AsyncClient(timeout=10.0) as client:
            res = await client.post(
                url,
                json={
                    "contents": [{
                        "parts": [
                            {"inline_data": {"mime_type": mime, "data": wav_b64}},
                            {"text": prompt}
                        ]
                    }],
                    "generationConfig": {"temperature": 0.0}
                }
            )
            if res.status_code == 200:
                data = res.json()
                candidates = data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts:
                        text = parts[0].get("text", "").strip()
                        if text and text != "[SILENT]":
                            log.info("Gemini audio STT transcribed successfully: '%s'", text)
                            return text
    except Exception as e:
        log.warning("Gemini audio STT fallback failed: %s", e)
    return ""


async def sarvam_tts(text: str, language: str = "kn-IN") -> bytes:
    """Synthesize text into speech audio WAV bytes using Sarvam AI Bulbul, with Google TTS fallback."""
    if settings.sarvam_api_key:
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
                if response.status_code == 200:
                    audios = response.json().get("audios", [])
                    if audios:
                        return base64.b64decode(audios[0])
        except Exception as e:
            log.warning("Sarvam TTS failed: %s; trying Google TTS fallback", e)

    # Google TTS fallback for natural spoken voice if Sarvam quota is exhausted
    try:
        short_lang = language.split("-")[0] if "-" in language else language
        tts_url = f"https://translate.google.com/translate_tts?ie=UTF-8&q={httpx.URL('', params={'q': text[:200]}).params['q']}&tl={short_lang}&client=tw-ob"
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(tts_url, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200 and len(resp.content) > 100:
                return resp.content
    except Exception as e:
        log.warning("Google TTS fallback failed: %s", e)

    return generate_beep_wav(0.2)


async def transcribe(pcm: bytes, language: str = "kn-IN") -> str:
    """Route STT to configured provider with automatic Gemini audio fallback."""
    result = ""
    provider = settings.speech_provider.lower()
    if provider == "gnani":
        from .stt_gnani import transcribe_gnani
        result = await transcribe_gnani(pcm, language)
    elif provider == "sarvam":
        result = await sarvam_stt(pcm, language)

    # If primary provider returned empty (e.g. quota exhausted or no key), use Gemini Multimodal STT
    if not result:
        result = await gemini_stt(pcm, language)

    return result


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
