"""
tools.py — Tool Registry & Built-in Implementations
=====================================================
Provides a framework for the LLM to invoke Python functions:
  1. **Calculator** — safe math via ``simpleeval``.
  2. **Web Search** — DuckDuckGo instant-answer API.
  3. **File Read/Write** — sandboxed to a workspace directory.

Tools are registered with JSON-Schema descriptions so they can be
serialised and sent to the LLM as function-call definitions.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import httpx
from simpleeval import simple_eval, InvalidExpression

from config import settings
from schemas import ToolDefinition, ToolResult

logger = logging.getLogger(__name__)


# ============================================================
# Tool Registry
# ============================================================

class ToolRegistry:
    """
    In‑memory registry of tool functions keyed by name.
    Each tool has a callable, a description, and a JSON‑Schema
    for its parameters.
    """

    def __init__(self) -> None:
        self._tools: Dict[str, Dict[str, Any]] = {}

    def register(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
        func: Callable[..., Any],
    ) -> None:
        """Register a new tool."""
        self._tools[name] = {
            "description": description,
            "parameters": parameters,
            "func": func,
        }
        logger.info("Tool registered: %s", name)

    def get_definitions(self) -> List[ToolDefinition]:
        """Return ToolDefinition schemas suitable for the LLM."""
        return [
            ToolDefinition(
                name=name,
                description=info["description"],
                parameters=info["parameters"],
            )
            for name, info in self._tools.items()
        ]

    async def execute(self, name: str, arguments: Dict[str, Any], call_id: str = "") -> ToolResult:
        """
        Execute a tool by name with the given arguments.

        Returns a ``ToolResult`` that can be fed back to the LLM.
        """
        if name not in self._tools:
            logger.warning("Tool not found: %s", name)
            return ToolResult(
                tool_call_id=call_id,
                name=name,
                result=None,
                error=f"Unknown tool: {name}",
            )
        try:
            func = self._tools[name]["func"]
            # Support both sync and async callables
            import asyncio
            if asyncio.iscoroutinefunction(func):
                result = await func(**arguments)
            else:
                result = func(**arguments)
            logger.info("Tool executed: %s → success", name)
            return ToolResult(tool_call_id=call_id, name=name, result=result)
        except Exception as exc:
            logger.error("Tool execution failed: %s — %s", name, exc)
            return ToolResult(
                tool_call_id=call_id,
                name=name,
                result=None,
                error=str(exc),
            )


# ============================================================
# Built-in Tool Implementations
# ============================================================

# 1. Calculator -------------------------------------------------

def calculator(expression: str) -> str:
    """
    Evaluate a mathematical expression safely using ``simpleeval``.
    No access to builtins, imports, or the OS — only pure math.
    """
    try:
        result = simple_eval(expression)
        return str(result)
    except InvalidExpression as exc:
        return f"Invalid expression: {exc}"
    except Exception as exc:
        return f"Calculation error: {exc}"


CALCULATOR_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "expression": {
            "type": "string",
            "description": "Mathematical expression to evaluate, e.g. '2 + 3 * 4'",
        },
    },
    "required": ["expression"],
}


# 2. Web Search --------------------------------------------------

async def web_search(query: str) -> str:
    """
    Search the web using the DuckDuckGo Instant Answer API.
    Returns a concise textual summary.
    """
    url = "https://api.duckduckgo.com/"
    params = {"q": query, "format": "json", "no_html": 1, "skip_disambig": 1}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        # Try abstract first, then related topics
        abstract = data.get("AbstractText", "")
        if abstract:
            return abstract

        answer = data.get("Answer", "")
        if answer:
            return answer

        # Fallback: first related topic
        topics = data.get("RelatedTopics", [])
        if topics and isinstance(topics[0], dict):
            return topics[0].get("Text", "No results found.")

        return "No results found for the given query."
    except Exception as exc:
        logger.error("Web search failed: %s", exc)
        return f"Search error: {exc}"


WEB_SEARCH_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "description": "The search query string",
        },
    },
    "required": ["query"],
}


# 3. File Read / Write -------------------------------------------

_WORKSPACE = settings.get_workspace_path()


def file_read(filename: str) -> str:
    """
    Read a text file from the sandboxed workspace directory.
    Path traversal attempts are blocked.
    """
    target = (_WORKSPACE / filename).resolve()
    # Sandbox check
    if not str(target).startswith(str(_WORKSPACE)):
        return "Error: path traversal detected — access denied."
    if not target.is_file():
        return f"Error: file '{filename}' not found in workspace."
    try:
        return target.read_text(encoding="utf-8")
    except Exception as exc:
        return f"Error reading file: {exc}"


def file_write(filename: str, content: str) -> str:
    """
    Write content to a text file inside the sandboxed workspace directory.
    Creates parent directories as needed. Path traversal is blocked.
    """
    target = (_WORKSPACE / filename).resolve()
    if not str(target).startswith(str(_WORKSPACE)):
        return "Error: path traversal detected — access denied."
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        return f"Successfully wrote {len(content)} characters to '{filename}'."
    except Exception as exc:
        return f"Error writing file: {exc}"


FILE_READ_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the file to read (relative to workspace)",
        },
    },
    "required": ["filename"],
}

FILE_WRITE_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "filename": {
            "type": "string",
            "description": "Name of the file to write (relative to workspace)",
        },
        "content": {
            "type": "string",
            "description": "Content to write into the file",
        },
    },
    "required": ["filename", "content"],
}


# ============================================================
# Default Registry Factory
# ============================================================

def create_default_registry() -> ToolRegistry:
    """
    Build a registry pre-loaded with the three built-in tools.
    Called once at application startup.
    """
    registry = ToolRegistry()
    registry.register("calculator", "Evaluate a mathematical expression safely.", CALCULATOR_SCHEMA, calculator)
    registry.register("web_search", "Search the web for information.", WEB_SEARCH_SCHEMA, web_search)
    registry.register("file_read", "Read a text file from the workspace.", FILE_READ_SCHEMA, file_read)
    registry.register("file_write", "Write content to a text file in the workspace.", FILE_WRITE_SCHEMA, file_write)
    return registry
