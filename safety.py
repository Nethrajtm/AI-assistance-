"""
safety.py — Jailbreak Detection, Prompt Sanitisation & Output Filtering
=========================================================================
Three‑layer safety system:
  1. **Pre-processor** — scans user prompts for known jailbreak patterns.
  2. **Post-processor** — scans assistant responses for harmful content.
  3. **Rate limiter** — per‑session sliding‑window counter to detect abuse.

All flagged events are logged at WARNING level for monitoring dashboards.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from config import settings

logger = logging.getLogger(__name__)

# ============================================================
# 1. Jailbreak Pattern Definitions
# ============================================================

# Each tuple: (human-readable label, compiled regex)
_JAILBREAK_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("ignore_previous", re.compile(
        r"ignore\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules|directives)",
        re.IGNORECASE,
    )),
    ("act_as_dan", re.compile(
        r"(act\s+as\s+DAN|do\s+anything\s+now|you\s+are\s+now\s+DAN)",
        re.IGNORECASE,
    )),
    ("jailbreak_explicit", re.compile(
        r"(jailbreak|jail\s*break|bypass\s+(safety|filter|content\s+policy|restriction))",
        re.IGNORECASE,
    )),
    ("developer_mode", re.compile(
        r"(developer\s+mode|enable\s+developer|sudo\s+mode|god\s+mode|admin\s+mode)",
        re.IGNORECASE,
    )),
    ("pretend_no_rules", re.compile(
        r"(pretend\s+(you\s+)?(have|has)\s+no\s+(rules|restrictions|limits|guidelines))",
        re.IGNORECASE,
    )),
    ("roleplay_unrestricted", re.compile(
        r"(you\s+are\s+an?\s+(evil|unrestricted|unfiltered|uncensored)\s+(AI|assistant|model|bot))",
        re.IGNORECASE,
    )),
    ("system_prompt_leak", re.compile(
        r"(reveal|show|repeat|print|output)\s+(your\s+)?(system\s+prompt|initial\s+instructions|hidden\s+instructions)",
        re.IGNORECASE,
    )),
    ("token_smuggling", re.compile(
        r"(\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>|<<SYS>>|<</SYS>>)",
        re.IGNORECASE,
    )),
]

# ============================================================
# 2. Harmful Output Categories
# ============================================================

_HARMFUL_OUTPUT_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("violence_instructions", re.compile(
        r"(how\s+to\s+(make|build|create)\s+(a\s+)?(bomb|explosive|weapon|poison))",
        re.IGNORECASE,
    )),
    ("illegal_activity", re.compile(
        r"(how\s+to\s+(hack|break\s+into|steal|forge|counterfeit))",
        re.IGNORECASE,
    )),
    ("self_harm", re.compile(
        r"(kill\s+yourself|commit\s+suicide|ways\s+to\s+(hurt|harm)\s+yourself)",
        re.IGNORECASE,
    )),
    ("hate_speech", re.compile(
        r"(exterminate|ethnic\s+cleansing|genocide\s+is\s+(good|justified|necessary))",
        re.IGNORECASE,
    )),
    ("doxxing", re.compile(
        r"(here\s+is\s+(their|his|her)\s+(home\s+)?address|social\s+security\s+number\s+is)",
        re.IGNORECASE,
    )),
]

# ============================================================
# 3. Rate Limiter
# ============================================================

@dataclass
class _RateBucket:
    """Sliding window for one session."""
    timestamps: List[float] = field(default_factory=list)


class RateLimiter:
    """Per-session sliding-window rate limiter."""

    def __init__(
        self,
        max_requests: int = settings.rate_limit_max_requests,
        window_seconds: int = settings.rate_limit_window_seconds,
    ) -> None:
        self._max = max_requests
        self._window = window_seconds
        self._buckets: Dict[str, _RateBucket] = defaultdict(_RateBucket)

    def is_rate_limited(self, session_id: str) -> bool:
        """Return True if *session_id* has exceeded the request limit."""
        now = time.time()
        bucket = self._buckets[session_id]
        # Prune timestamps outside the window
        bucket.timestamps = [t for t in bucket.timestamps if now - t < self._window]
        if len(bucket.timestamps) >= self._max:
            logger.warning(
                "Rate limit exceeded for session=%s (%d reqs in %ds)",
                session_id, len(bucket.timestamps), self._window,
            )
            return True
        bucket.timestamps.append(now)
        return False

    def reset(self, session_id: str) -> None:
        """Reset the counter for a session (e.g. after a cool‑down)."""
        self._buckets.pop(session_id, None)


# ============================================================
# 4. Public API
# ============================================================

# Module‑level singleton
_rate_limiter = RateLimiter()


def check_prompt_safety(text: str, session_id: str = "unknown") -> Tuple[bool, str]:
    """
    Scan a user prompt for jailbreak patterns.

    Returns
    -------
    (is_safe, reason)
        ``is_safe`` is True when the prompt passes all checks.
        ``reason`` contains a human-readable label when flagged.
    """
    for label, pattern in _JAILBREAK_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "Jailbreak detected [%s] session=%s prompt_snippet='%s'",
                label, session_id, text[:120],
            )
            return False, f"Prompt blocked: jailbreak pattern detected ({label})"
    return True, ""


def check_output_safety(text: str, session_id: str = "unknown") -> Tuple[bool, str]:
    """
    Post-process assistant output for harmful content.

    Returns
    -------
    (is_safe, reason)
        ``is_safe`` is True when the output passes all checks.
    """
    for label, pattern in _HARMFUL_OUTPUT_PATTERNS:
        if pattern.search(text):
            logger.warning(
                "Harmful output detected [%s] session=%s output_snippet='%s'",
                label, session_id, text[:120],
            )
            return False, f"Response filtered: potentially harmful content ({label})"
    return True, ""


def check_rate_limit(session_id: str) -> Tuple[bool, str]:
    """
    Enforce per-session rate limiting.

    Returns
    -------
    (is_allowed, reason)
    """
    if _rate_limiter.is_rate_limited(session_id):
        return False, "Rate limit exceeded. Please wait before sending more requests."
    return True, ""


def sanitise_prompt(text: str) -> str:
    """
    Light-touch sanitisation — strips common token-smuggling markers
    without altering normal user text.
    """
    # Remove special tokens that could manipulate chat templates
    cleaned = re.sub(r"(\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>|<<SYS>>|<</SYS>>)", "", text)
    return cleaned.strip()
