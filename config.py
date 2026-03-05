"""
config.py — Centralised Configuration
======================================
Loads environment variables from a .env file and exposes them as a
validated Pydantic Settings singleton.  Every other module imports
``settings`` from here instead of reading os.environ directly.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import List

from dotenv import load_dotenv
from pydantic_settings import BaseSettings
from pydantic import Field

# Load .env file before settings class is instantiated
load_dotenv()

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    """Application-wide settings — sourced from environment variables."""

    # ---- LLM Provider ----
    llm_provider: str = Field("openai", description="openai | anthropic | ollama")

    # OpenAI
    openai_api_key: str = Field("", description="OpenAI API key")
    openai_model: str = Field("gpt-4o", description="OpenAI model name")
    openai_base_url: str = Field("https://api.openai.com/v1")

    # Anthropic
    anthropic_api_key: str = Field("", description="Anthropic API key")
    anthropic_model: str = Field("claude-3-5-sonnet-20241022")

    # Ollama (local)
    ollama_base_url: str = Field("http://localhost:11434")
    ollama_model: str = Field("llama3.2")

    # ---- Vision ----
    vision_provider: str = Field("openai")
    vision_model: str = Field("gpt-4o")

    # ---- TTS ----
    tts_provider: str = Field("openai", description="openai | elevenlabs")
    tts_model: str = Field("tts-1")
    tts_voice: str = Field("alloy")
    elevenlabs_api_key: str = Field("")
    elevenlabs_voice_id: str = Field("")

    # ---- STT ----
    stt_provider: str = Field("openai")
    stt_model: str = Field("whisper-1")

    # ---- Memory ----
    short_term_memory_limit: int = Field(50, ge=1, le=500)
    chroma_persist_dir: str = Field("./chroma_data")
    embedding_model: str = Field("all-MiniLM-L6-v2")

    # ---- Safety ----
    rate_limit_max_requests: int = Field(30, ge=1)
    rate_limit_window_seconds: int = Field(60, ge=1)

    # ---- Tools ----
    tool_workspace_dir: str = Field("./workspace")
    search_api_key: str = Field("")

    # ---- Camera ----
    camera_index: int = Field(0)
    camera_url: str = Field("")

    # ---- Server ----
    host: str = Field("0.0.0.0")
    port: int = Field(8000)
    cors_origins: str = Field('["http://localhost:3000","http://localhost:5173"]')
    log_level: str = Field("INFO")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def get_cors_origins_list(self) -> List[str]:
        """Parse CORS_ORIGINS JSON string into a Python list."""
        try:
            return json.loads(self.cors_origins)
        except json.JSONDecodeError:
            logger.warning("Failed to parse CORS_ORIGINS, falling back to ['*']")
            return ["*"]

    def get_workspace_path(self) -> Path:
        """Return an absolute, existing workspace directory for tools."""
        p = Path(self.tool_workspace_dir).resolve()
        p.mkdir(parents=True, exist_ok=True)
        return p


# ----- Singleton instance used across the application -----
settings = Settings()


def configure_logging() -> None:
    """Set up root logger based on settings.log_level."""
    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    logger.info("Logging configured at %s level", settings.log_level.upper())
