"""
schemas.py — Pydantic Models for Requests & Responses
======================================================
Every endpoint validates its input / output through these models,
ensuring type safety and automatic OpenAPI documentation.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ============================================================
# Common / Shared
# ============================================================

class Message(BaseModel):
    """A single chat message (user, assistant, system, or tool)."""
    role: str = Field(..., description="One of: system, user, assistant, tool")
    content: str = Field(..., description="Text content of the message")
    name: Optional[str] = Field(None, description="Optional speaker name")
    image_url: Optional[str] = Field(None, description="Optional image URL for vision")
    tool_call_id: Optional[str] = Field(None, description="ID linking to a tool invocation")


class ToolDefinition(BaseModel):
    """Schema describing a tool the LLM may invoke."""
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="Human-readable description")
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON Schema of the tool's parameters",
    )


class ToolCall(BaseModel):
    """Represents the LLM's decision to invoke a specific tool."""
    id: str = Field(..., description="Unique call identifier")
    name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class ToolResult(BaseModel):
    """Result returned after executing a tool."""
    tool_call_id: str
    name: str
    result: Any
    error: Optional[str] = None


# ============================================================
# Chat Endpoint
# ============================================================

class ChatRequest(BaseModel):
    """POST /chat request body."""
    session_id: str = Field(..., description="Unique session identifier for memory isolation")
    messages: List[Message] = Field(..., min_length=1, description="Conversation messages")
    stream: bool = Field(False, description="Enable Server-Sent Events streaming")
    tools: Optional[List[ToolDefinition]] = Field(
        None, description="Tools available for the LLM to invoke"
    )
    model: Optional[str] = Field(None, description="Override default model name")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="Sampling temperature")


class ChatResponse(BaseModel):
    """POST /chat response body (non-streaming)."""
    session_id: str
    message: Message
    tool_calls: Optional[List[ToolCall]] = None
    tool_results: Optional[List[ToolResult]] = None
    usage: Optional[Dict[str, int]] = None  # e.g. {"prompt_tokens": 100, "completion_tokens": 50}


# ============================================================
# Speech-to-Text
# ============================================================

class STTResponse(BaseModel):
    """POST /stt response body."""
    text: str = Field(..., description="Transcribed text from the audio input")
    language: Optional[str] = Field(None, description="Detected language code")
    duration_seconds: Optional[float] = Field(None, description="Audio duration")


# ============================================================
# Text-to-Speech
# ============================================================

class TTSRequest(BaseModel):
    """POST /tts request body."""
    text: str = Field(..., min_length=1, max_length=4096, description="Text to convert to speech")
    voice: Optional[str] = Field(None, description="Voice identifier override")
    model: Optional[str] = Field(None, description="TTS model override")


# ============================================================
# Vision
# ============================================================

class VisionRequest(BaseModel):
    """POST /vision request body (when sent as JSON with image_url)."""
    prompt: str = Field(..., min_length=1, description="Text prompt for the vision model")
    image_url: Optional[str] = Field(None, description="URL of the image to analyse")
    session_id: Optional[str] = Field(None, description="Optional session for memory")


class VisionResponse(BaseModel):
    """POST /vision response body."""
    description: str = Field(..., description="Vision model's analysis of the image")
    model: str = Field(..., description="Model that produced the response")


# ============================================================
# Health
# ============================================================

class HealthResponse(BaseModel):
    """GET /health response body."""
    status: str = Field("ok")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    version: str = Field("1.0.0")
    provider: str = Field(..., description="Active LLM provider")


# ============================================================
# Safety / Admin
# ============================================================

class SafetyFlag(BaseModel):
    """Logged when a safety filter triggers."""
    session_id: str
    flag_type: str = Field(..., description="jailbreak | harmful_output | rate_limit")
    detail: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ============================================================
# Error
# ============================================================

class ErrorResponse(BaseModel):
    """Standard error envelope returned on failures."""
    error: str
    detail: Optional[str] = None
    status_code: int = 500
