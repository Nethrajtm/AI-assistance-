"""
llm.py — Provider-Agnostic LLM Client
=======================================
Abstracts OpenAI, Anthropic, and Ollama behind a unified interface.
Supports both one-shot ``chat()`` and token-streaming ``stream_chat()``
methods.  All HTTP calls use ``httpx.AsyncClient`` for true async I/O.
"""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx

from config import settings
from schemas import Message, ToolDefinition

logger = logging.getLogger(__name__)

# Shared HTTP timeout (connect / read / write / pool)
_TIMEOUT = httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)


# ============================================================
# Base Client
# ============================================================

class LLMClient:
    """
    Provider-agnostic façade.  Instantiate once at app startup and reuse.
    """

    def __init__(self) -> None:
        self._provider = settings.llm_provider.lower()
        self._http = httpx.AsyncClient(timeout=_TIMEOUT)
        logger.info("LLMClient initialised with provider=%s", self._provider)

    async def close(self) -> None:
        await self._http.aclose()

    # ----------------------------------------------------------
    # Non-streaming chat
    # ----------------------------------------------------------
    async def chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> Dict[str, Any]:
        """
        Send a chat request and return the full response dict.

        Returns a dict with at least ``{"content": "...", "role": "assistant"}``.
        May also include ``"tool_calls"`` when the model invokes tools.
        """
        if self._provider == "openai":
            return await self._openai_chat(messages, model, temperature, tools)
        elif self._provider == "anthropic":
            return await self._anthropic_chat(messages, model, temperature, tools)
        elif self._provider == "ollama":
            return await self._ollama_chat(messages, model, temperature)
        else:
            raise ValueError(f"Unsupported LLM provider: {self._provider}")

    # ----------------------------------------------------------
    # Streaming chat  (yields token strings)
    # ----------------------------------------------------------
    async def stream_chat(
        self,
        messages: List[Message],
        model: Optional[str] = None,
        temperature: float = 0.7,
    ) -> AsyncGenerator[str, None]:
        """
        Yield incremental text tokens from the LLM via SSE.
        """
        if self._provider == "openai":
            async for token in self._openai_stream(messages, model, temperature):
                yield token
        elif self._provider == "anthropic":
            async for token in self._anthropic_stream(messages, model, temperature):
                yield token
        elif self._provider == "ollama":
            async for token in self._ollama_stream(messages, model, temperature):
                yield token
        else:
            raise ValueError(f"Unsupported LLM provider: {self._provider}")

    # ============================================================
    # OpenAI Implementation
    # ============================================================

    def _openai_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {settings.openai_api_key}",
            "Content-Type": "application/json",
        }

    def _openai_payload(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
        stream: bool = False,
        tools: Optional[List[ToolDefinition]] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": model or settings.openai_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": temperature,
            "stream": stream,
        }
        if tools:
            payload["tools"] = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ]
        return payload

    async def _openai_chat(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
        tools: Optional[List[ToolDefinition]],
    ) -> Dict[str, Any]:
        url = f"{settings.openai_base_url}/chat/completions"
        payload = self._openai_payload(messages, model, temperature, stream=False, tools=tools)
        try:
            resp = await self._http.post(url, json=payload, headers=self._openai_headers())
            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]
            result: Dict[str, Any] = {
                "role": "assistant",
                "content": choice["message"].get("content", ""),
            }
            # Attach tool calls if present
            if choice["message"].get("tool_calls"):
                result["tool_calls"] = choice["message"]["tool_calls"]
            # Attach usage info
            if data.get("usage"):
                result["usage"] = data["usage"]
            return result
        except httpx.HTTPStatusError as exc:
            logger.error("OpenAI API error: %s — %s", exc.response.status_code, exc.response.text)
            raise
        except httpx.RequestError as exc:
            logger.error("OpenAI connection error: %s", exc)
            raise

    async def _openai_stream(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        url = f"{settings.openai_base_url}/chat/completions"
        payload = self._openai_payload(messages, model, temperature, stream=True)
        try:
            async with self._http.stream(
                "POST", url, json=payload, headers=self._openai_headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[len("data: "):]
                    if data_str.strip() == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data_str)
                        delta = chunk["choices"][0].get("delta", {})
                        if delta.get("content"):
                            yield delta["content"]
                    except (json.JSONDecodeError, KeyError, IndexError):
                        continue
        except httpx.HTTPStatusError as exc:
            logger.error("OpenAI stream error: %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.error("OpenAI stream connection error: %s", exc)
            raise

    # ============================================================
    # Anthropic Implementation
    # ============================================================

    def _anthropic_headers(self) -> Dict[str, str]:
        return {
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        }

    async def _anthropic_chat(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
        tools: Optional[List[ToolDefinition]],
    ) -> Dict[str, Any]:
        url = "https://api.anthropic.com/v1/messages"
        # Anthropic separates system messages
        system_msg = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg += m.content + "\n"
            else:
                api_messages.append({"role": m.role, "content": m.content})

        payload: Dict[str, Any] = {
            "model": model or settings.anthropic_model,
            "max_tokens": 4096,
            "messages": api_messages,
            "temperature": temperature,
        }
        if system_msg.strip():
            payload["system"] = system_msg.strip()
        if tools:
            payload["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]

        try:
            resp = await self._http.post(url, json=payload, headers=self._anthropic_headers())
            resp.raise_for_status()
            data = resp.json()
            # Extract text content
            content_parts = data.get("content", [])
            text = "".join(p.get("text", "") for p in content_parts if p.get("type") == "text")
            result: Dict[str, Any] = {"role": "assistant", "content": text}
            # Tool use
            tool_uses = [p for p in content_parts if p.get("type") == "tool_use"]
            if tool_uses:
                result["tool_calls"] = [
                    {
                        "id": tu["id"],
                        "type": "function",
                        "function": {"name": tu["name"], "arguments": json.dumps(tu["input"])},
                    }
                    for tu in tool_uses
                ]
            if data.get("usage"):
                result["usage"] = {
                    "prompt_tokens": data["usage"].get("input_tokens", 0),
                    "completion_tokens": data["usage"].get("output_tokens", 0),
                }
            return result
        except httpx.HTTPStatusError as exc:
            logger.error("Anthropic API error: %s — %s", exc.response.status_code, exc.response.text)
            raise
        except httpx.RequestError as exc:
            logger.error("Anthropic connection error: %s", exc)
            raise

    async def _anthropic_stream(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        url = "https://api.anthropic.com/v1/messages"
        system_msg = ""
        api_messages = []
        for m in messages:
            if m.role == "system":
                system_msg += m.content + "\n"
            else:
                api_messages.append({"role": m.role, "content": m.content})

        payload: Dict[str, Any] = {
            "model": model or settings.anthropic_model,
            "max_tokens": 4096,
            "messages": api_messages,
            "temperature": temperature,
            "stream": True,
        }
        if system_msg.strip():
            payload["system"] = system_msg.strip()

        try:
            async with self._http.stream(
                "POST", url, json=payload, headers=self._anthropic_headers()
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    try:
                        event = json.loads(line[len("data: "):])
                        if event.get("type") == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("text"):
                                yield delta["text"]
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPStatusError as exc:
            logger.error("Anthropic stream error: %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.error("Anthropic stream connection error: %s", exc)
            raise

    # ============================================================
    # Ollama Implementation (Local)
    # ============================================================

    async def _ollama_chat(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
    ) -> Dict[str, Any]:
        url = f"{settings.ollama_base_url}/api/chat"
        payload = {
            "model": model or settings.ollama_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": False,
            "options": {"temperature": temperature},
        }
        try:
            resp = await self._http.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            return {
                "role": "assistant",
                "content": data.get("message", {}).get("content", ""),
            }
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama API error: %s — %s", exc.response.status_code, exc.response.text)
            raise
        except httpx.RequestError as exc:
            logger.error("Ollama connection error: %s", exc)
            raise

    async def _ollama_stream(
        self,
        messages: List[Message],
        model: Optional[str],
        temperature: float,
    ) -> AsyncGenerator[str, None]:
        url = f"{settings.ollama_base_url}/api/chat"
        payload = {
            "model": model or settings.ollama_model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "stream": True,
            "options": {"temperature": temperature},
        }
        try:
            async with self._http.stream("POST", url, json=payload) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")
                        if token:
                            yield token
                    except json.JSONDecodeError:
                        continue
        except httpx.HTTPStatusError as exc:
            logger.error("Ollama stream error: %s", exc.response.status_code)
            raise
        except httpx.RequestError as exc:
            logger.error("Ollama stream connection error: %s", exc)
            raise
