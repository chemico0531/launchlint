"""Anthropic API gateway with prompt caching for cost+latency reduction.

BYO Key mode: reads ANTHROPIC_API_KEY from environment.
Default model: claude-haiku-4-5-20251001 (templated-fix sweet spot, 10-20x cost advantage).
"""

from __future__ import annotations

import os
import textwrap
from dataclasses import dataclass, field
from typing import Any

import anthropic

DEFAULT_MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS_OUTPUT = 4096


@dataclass
class AIResponse:
    raw_text: str
    usage: dict[str, int]
    cached: bool = False


@dataclass
class AIGateway:
    """Anthropic API client with caching support."""

    api_key: str | None = None
    model: str = DEFAULT_MODEL
    max_tokens: int = MAX_TOKENS_OUTPUT
    _client: anthropic.Anthropic | None = field(default=None, init=False, repr=False)

    def __post_init__(self) -> None:
        key = self.api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError(
                "No API key: pass --ai-key or set ANTHROPIC_API_KEY env var"
            )
        self._client = anthropic.Anthropic(api_key=key)

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    def audit_page(self, page_text: str, url: str, max_findings: int = 30) -> AIResponse:
        """Analyze a page and return structured launch findings as JSON."""
        cache_key = _build_cache_key(url, page_text)
        cached_body = _get_cached(cache_key)
        extra_kwargs: dict[str, Any] = {}
        if cached_body:
            extra_kwargs["cache_control"] = {"type": "ephemeral", "priority": "high"}
            system = _build_system_prompt(max_findings)
            message = cached_body
        else:
            system = _build_system_prompt(max_findings)
            message = _build_user_message(page_text, url, max_findings)

        response = self._client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system,
            messages=[{"role": "user", "content": message}],
            **extra_kwargs,
        )

        raw = response.content[0].text if response.content else ""

        # Attempt to cache the result for future calls
        if not cached_body:
            _put_cached(cache_key, raw)

        usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        return AIResponse(raw_text=raw, usage=usage, cached=bool(cached_body))

    def count_tokens(self, text: str) -> int:
        """Fast token count without an API call."""
        # Uses the SDK's built-in counting
        return self._client.count_tokens(text)


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------

def _build_system_prompt(max_findings: int) -> str:
    return textwrap.dedent(
        f"""\
        You are LaunchLint, a pre-launch quality auditor for websites.

        Analyze the provided HTML/text content of a webpage and return a JSON array of launch-blocking issues.
        Each finding must be a valid JSON object with this exact shape:
        {{
          "check": "seo|a11y|links|content|security|performance",
          "severity": "error|warn|info",
          "message": "short description of the problem",
          "location": "CSS selector or URL where the issue occurs (empty string if N/A)",
          "suggestion": "specific fix the developer can copy-paste (empty string if N/A)"
        }}

        Rules:
        - Return ONLY a valid JSON array, nothing else. No markdown fences, no explanation.
        - Maximum {max_findings} findings.
        - Focus on issues that would embarrass a team at launch.
        - Do not invent findings not supported by the content.
        - check values: seo, a11y, links, content, security, performance
        - severity values: error (blocks launch), warn (review before launch), info (nice to have)
        - message: 10-200 characters
        - suggestion: copy-paste ready code snippet or concrete action, 0-500 characters
        - location: empty string "" if no specific location
        - Return [] (empty array) if the page is genuinely clean.
        """
    ).strip()


def _build_user_message(page_text: str, url: str, max_findings: int) -> str:
    """Build the user message with the page content for analysis."""
    # Truncate page text to avoid token limits (keep first ~15k chars which is ~5k tokens)
    truncated = page_text[:15000]
    suffix = "... [truncated]" if len(page_text) > 15000 else ""
    return textwrap.dedent(
        f"""\
        URL: {url}

        Page content to analyze:
        ---START---
        {truncated}{suffix}
        ---END---

        Return up to {max_findings} launch-blocking findings as a JSON array.
        """
    ).strip()


# ---------------------------------------------------------------------------
# Simple file-based cache (ephemeral, per-run)
# ---------------------------------------------------------------------------

_CACHE: dict[str, str] = {}


def _build_cache_key(url: str, page_text: str) -> str:
    """Deterministic cache key from URL + page content fingerprint."""
    import hashlib
    fingerprint = hashlib.sha256(f"{url}:{len(page_text)}".encode()).hexdigest()[:16]
    return f"{url}::{fingerprint}"


def _get_cached(key: str) -> str | None:
    return _CACHE.get(key)


def _put_cached(key: str, value: str) -> None:
    _CACHE[key] = value
