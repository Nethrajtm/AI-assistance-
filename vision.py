"""
vision.py — Multimodal Vision LLM Integration
===============================================
Accepts an image (file upload or URL) together with a text prompt
and routes the request to a vision-capable model:
  - **OpenAI GPT-4o** (default)
  - **Anthropic Claude 3**
  - **Ollama** (llava, bakllava, etc.)

Images are base64-encoded before being sent to the API.
"""

from __future__ import annotations

import base64
import logging
from typing import Any, Dict, Optional

import httpx

from config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=10.0)


async def analyse_image(
    prompt: str,
    image_bytes: Optional[bytes] = None,
    image_url: Optional[str] = None,
    mime_type: str = "image/jpeg",
) -> Dict[str, Any]:
    """
    Send an image + text prompt to a vision LLM and return the analysis.

    Exactly one of ``image_bytes`` or ``image_url`` must be provided.

    Returns
    -------
    dict
        ``{"description": "...", "model": "..."}``
    """
    if not image_bytes and not image_url:
        raise ValueError("Either image_bytes or image_url must be provided.")

    provider = settings.vision_provider.lower()

    if provider == "openai":
        return await _openai_vision(prompt, image_bytes, image_url, mime_type)
    elif provider == "anthropic":
        return await _anthropic_vision(prompt, image_bytes, image_url, mime_type)
    elif provider == "ollama":
        return await _ollama_vision(prompt, image_bytes, image_url, mime_type)
    else:
        raise ValueError(f"Unsupported vision provider: {provider}")


# ============================================================
# OpenAI GPT-4o Vision
# ============================================================

async def _openai_vision(
    prompt: str,
    image_bytes: Optional[bytes],
    image_url: Optional[str],
    mime_type: str,
) -> Dict[str, Any]:
    """Use the OpenAI chat/completions endpoint with image content."""
    url = f"{settings.openai_base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openai_api_key}",
        "Content-Type": "application/json",
    }

    # Build the image content part
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_part = {
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{b64}"},
        }
    else:
        image_part = {
            "type": "image_url",
            "image_url": {"url": image_url},
        }

    payload = {
        "model": settings.vision_model,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    image_part,
                ],
            }
        ],
        "max_tokens": 2048,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return {"description": content, "model": settings.vision_model}
    except httpx.HTTPStatusError as exc:
        logger.error("OpenAI Vision error: %s — %s", exc.response.status_code, exc.response.text)
        raise
    except httpx.RequestError as exc:
        logger.error("OpenAI Vision connection error: %s", exc)
        raise


# ============================================================
# Anthropic Claude 3 Vision
# ============================================================

async def _anthropic_vision(
    prompt: str,
    image_bytes: Optional[bytes],
    image_url: Optional[str],
    mime_type: str,
) -> Dict[str, Any]:
    """Use the Anthropic messages endpoint with image content."""
    url = "https://api.anthropic.com/v1/messages"
    headers = {
        "x-api-key": settings.anthropic_api_key,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }

    # Build image source
    if image_bytes:
        b64 = base64.b64encode(image_bytes).decode("utf-8")
        image_source = {
            "type": "base64",
            "media_type": mime_type,
            "data": b64,
        }
    else:
        # Anthropic requires base64; download the URL first
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            b64 = base64.b64encode(img_resp.content).decode("utf-8")
            image_source = {
                "type": "base64",
                "media_type": mime_type,
                "data": b64,
            }

    payload = {
        "model": settings.anthropic_model,
        "max_tokens": 2048,
        "messages": [
            {
                "role": "user",
                "content": [
                    {"type": "image", "source": image_source},
                    {"type": "text", "text": prompt},
                ],
            }
        ],
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            text = "".join(
                p.get("text", "") for p in data.get("content", []) if p.get("type") == "text"
            )
            return {"description": text, "model": settings.anthropic_model}
    except httpx.HTTPStatusError as exc:
        logger.error("Anthropic Vision error: %s — %s", exc.response.status_code, exc.response.text)
        raise
    except httpx.RequestError as exc:
        logger.error("Anthropic Vision connection error: %s", exc)
        raise


# ============================================================
# Ollama (local multimodal — e.g. llava)
# ============================================================

async def _ollama_vision(
    prompt: str,
    image_bytes: Optional[bytes],
    image_url: Optional[str],
    mime_type: str,
) -> Dict[str, Any]:
    """
    Use Ollama's /api/chat with image data.
    Ollama accepts images as base64-encoded strings in the ``images`` field.
    """
    url = f"{settings.ollama_base_url}/api/chat"

    # Get image bytes if only URL was provided
    if not image_bytes and image_url:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            img_resp = await client.get(image_url)
            img_resp.raise_for_status()
            image_bytes = img_resp.content

    b64 = base64.b64encode(image_bytes).decode("utf-8") if image_bytes else ""

    payload = {
        "model": settings.ollama_model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64] if b64 else [],
            }
        ],
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
            resp = await client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            return {"description": content, "model": settings.ollama_model}
    except httpx.HTTPStatusError as exc:
        logger.error("Ollama Vision error: %s — %s", exc.response.status_code, exc.response.text)
        raise
    except httpx.RequestError as exc:
        logger.error("Ollama Vision connection error: %s", exc)
        raise
