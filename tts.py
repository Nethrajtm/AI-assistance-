"""
tts.py — Text-to-Speech Conversion
====================================
Converts assistant text responses to audio.
Supported providers:
  - **OpenAI TTS** (tts-1, tts-1-hd)
  - **ElevenLabs** (streaming audio)

Returns raw audio bytes (MP3) suitable for a ``StreamingResponse``.
"""

from __future__ import annotations

import logging
from typing import AsyncGenerator, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)


async def synthesise_speech(
    text: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
) -> bytes:
    """
    Convert text to speech audio bytes (MP3).

    Parameters
    ----------
    text : str
        The text to convert.
    voice : str, optional
        Voice identifier override.
    model : str, optional
        TTS model override.

    Returns
    -------
    bytes
        MP3 audio content.
    """
    provider = settings.tts_provider.lower()

    if provider == "openai":
        return await _openai_tts(text, voice, model)
    elif provider == "elevenlabs":
        return await _elevenlabs_tts(text, voice)
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")


async def stream_speech(
    text: str,
    voice: Optional[str] = None,
    model: Optional[str] = None,
) -> AsyncGenerator[bytes, None]:
    """
    Yield audio chunks for streaming playback.
    """
    provider = settings.tts_provider.lower()

    if provider == "openai":
        async for chunk in _openai_tts_stream(text, voice, model):
            yield chunk
    elif provider == "elevenlabs":
        async for chunk in _elevenlabs_tts_stream(text, voice):
            yield chunk
    else:
        raise ValueError(f"Unsupported TTS provider: {provider}")


# ============================================================
# OpenAI TTS
# ============================================================

async def _openai_tts(
    text: str,
    voice: Optional[str],
    model: Optional[str],
) -> bytes:
    """Call the OpenAI /audio/speech endpoint and return full MP3 bytes."""
    url = f"{settings.openai_base_url}/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or settings.tts_model,
        "input": text,
        "voice": voice or settings.tts_voice,
        "response_format": "mp3",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        logger.error("OpenAI TTS error: %s — %s", exc.response.status_code, exc.response.text)
        raise
    except httpx.RequestError as exc:
        logger.error("OpenAI TTS connection error: %s", exc)
        raise


async def _openai_tts_stream(
    text: str,
    voice: Optional[str],
    model: Optional[str],
) -> AsyncGenerator[bytes, None]:
    """Stream audio chunks from OpenAI TTS."""
    url = f"{settings.openai_base_url}/audio/speech"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model or settings.tts_model,
        "input": text,
        "voice": voice or settings.tts_voice,
        "response_format": "mp3",
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    yield chunk
    except httpx.HTTPStatusError as exc:
        logger.error("OpenAI TTS stream error: %s", exc.response.status_code)
        raise
    except httpx.RequestError as exc:
        logger.error("OpenAI TTS stream connection error: %s", exc)
        raise


# ============================================================
# ElevenLabs TTS
# ============================================================

async def _elevenlabs_tts(
    text: str,
    voice: Optional[str],
) -> bytes:
    """Call the ElevenLabs text-to-speech API and return MP3 bytes."""
    voice_id = voice or settings.elevenlabs_voice_id
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            return resp.content
    except httpx.HTTPStatusError as exc:
        logger.error("ElevenLabs TTS error: %s — %s", exc.response.status_code, exc.response.text)
        raise
    except httpx.RequestError as exc:
        logger.error("ElevenLabs TTS connection error: %s", exc)
        raise


async def _elevenlabs_tts_stream(
    text: str,
    voice: Optional[str],
) -> AsyncGenerator[bytes, None]:
    """Stream audio chunks from ElevenLabs."""
    voice_id = voice or settings.elevenlabs_voice_id
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream"
    headers = {
        "xi-api-key": settings.elevenlabs_api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": "eleven_monolingual_v1",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as resp:
                resp.raise_for_status()
                async for chunk in resp.aiter_bytes(chunk_size=4096):
                    yield chunk
    except httpx.HTTPStatusError as exc:
        logger.error("ElevenLabs TTS stream error: %s", exc.response.status_code)
        raise
    except httpx.RequestError as exc:
        logger.error("ElevenLabs TTS stream connection error: %s", exc)
        raise
