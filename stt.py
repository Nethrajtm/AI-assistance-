"""
stt.py — Speech-to-Text Processing
====================================
Accepts audio uploads (WAV, MP3, etc.) and transcribes them to text.
Currently supports:
  - **OpenAI Whisper API** (default)
  - **Ollama** (local whisper-compatible endpoint)

Audio bytes are read from FastAPI's ``UploadFile``, forwarded to the
chosen provider, and the transcription is returned.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


async def transcribe_audio(
    audio_bytes: bytes,
    filename: str = "audio.wav",
    language: Optional[str] = None,
) -> dict:
    """
    Transcribe audio bytes to text.

    Parameters
    ----------
    audio_bytes : bytes
        Raw audio file content (WAV, MP3, M4A, etc.).
    filename : str
        Original filename — used for MIME type inference.
    language : str, optional
        ISO-639-1 language hint (e.g. ``"en"``).

    Returns
    -------
    dict
        ``{"text": "...", "language": "...", "duration_seconds": ...}``
    """
    provider = settings.stt_provider.lower()

    if provider == "openai":
        return await _openai_transcribe(audio_bytes, filename, language)
    elif provider == "ollama":
        return await _ollama_transcribe(audio_bytes, filename, language)
    else:
        raise ValueError(f"Unsupported STT provider: {provider}")


# ============================================================
# OpenAI Whisper
# ============================================================

async def _openai_transcribe(
    audio_bytes: bytes,
    filename: str,
    language: Optional[str],
) -> dict:
    """Call the OpenAI /audio/transcriptions endpoint."""
    url = f"{settings.openai_base_url}/audio/transcriptions"
    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}

    # Build multipart form data
    files = {"file": (filename, audio_bytes)}
    data: dict = {
        "model": settings.stt_model,
        "response_format": "verbose_json",
    }
    if language:
        data["language"] = language

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, headers=headers, files=files, data=data)
            resp.raise_for_status()
            result = resp.json()
            return {
                "text": result.get("text", ""),
                "language": result.get("language"),
                "duration_seconds": result.get("duration"),
            }
    except httpx.HTTPStatusError as exc:
        logger.error("OpenAI STT error: %s — %s", exc.response.status_code, exc.response.text)
        raise
    except httpx.RequestError as exc:
        logger.error("OpenAI STT connection error: %s", exc)
        raise


# ============================================================
# Ollama (local)
# ============================================================

async def _ollama_transcribe(
    audio_bytes: bytes,
    filename: str,
    language: Optional[str],
) -> dict:
    """
    Placeholder for local Ollama-based STT.
    Ollama doesn't natively support audio transcription yet,
    so this falls back to an error message.
    """
    logger.warning("Ollama STT is not natively supported; returning error.")
    return {
        "text": "[Ollama STT not available — configure OpenAI Whisper instead]",
        "language": language,
        "duration_seconds": None,
    }
