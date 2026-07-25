"""6 AI output verification gates.

Each gate validates a specific failure mode. All gates must pass for
the AI output to be accepted. If any gate fails, findings are discarded
and the issue is logged as a warning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Gate 1 — Rejection mechanism: safety word filter + length check
# ---------------------------------------------------------------------------

# Words that, if present, indicate the model is refusing or hallucinating
_REJECTION_PATTERNS = [
    re.compile(r"\bi cannot\b", re.IGNORECASE),
    re.compile(r"\bi'm sorry\b", re.IGNORECASE),
    re.compile(r"\bsorry,?\s*i\b", re.IGNORECASE),
    re.compile(r"\bunderstood\b", re.IGNORECASE),
    re.compile(r"\bhere('s| is) (a|my|the) (answer|response|output)\b", re.IGNORECASE),
    re.compile(r"```json", re.IGNORECASE),  # model wrapped in code fences
]


@dataclass
class Gate1Result:
    passed: bool
    reason: str = ""


def gate1_rejection(text: str) -> Gate1Result:
    """Gate 1: Check for refusal/hallucination signals."""
    if not text or len(text.strip()) < 5:
        return Gate1Result(passed=False, reason="empty or near-empty response")

    for pattern in _REJECTION_PATTERNS:
        if pattern.search(text):
            return Gate1Result(passed=False, reason=f"rejection pattern matched: {pattern.pattern}")

    return Gate1Result(passed=True)


# ---------------------------------------------------------------------------
# Gate 2 — JSON parse validation
# ---------------------------------------------------------------------------

BLOCKLIST_PREFIXES = ["Access", "An error", "Permission", "Forbidden", "Unauthorized"]


@dataclass
class Gate2Result:
    passed: bool
    findings: list[dict[str, Any]] = field(default_factory=list)
    reason: str = ""


def gate2_json_parse(text: str) -> Gate2Result:
    """Gate 2: Ensure AI returns a valid JSON array."""
    # Strip markdown fences if present
    cleaned = re.sub(r"^```json\s*", "", text.strip(), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s*```$", "", cleaned.strip())

    for prefix in BLOCKLIST_PREFIXES:
        if cleaned.startswith(prefix):
            return Gate2Result(passed=False, reason=f"blocked prefix: {prefix!r}")

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        return Gate2Result(passed=False, reason=f"JSON parse failed: {exc}")

    if not isinstance(parsed, list):
        # Try to find a JSON array in the text
        match = re.search(r"\[\s*\{.*\}\s*\]", cleaned, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except json.JSONDecodeError:
                return Gate2Result(passed=False, reason="response is not a JSON array")
        else:
            return Gate2Result(passed=False, reason="response is not a JSON array")

    # Validate each finding has required fields
    valid_findings = []
    for item in parsed:
        if isinstance(item, dict) and all(
            k in item for k in ("check", "severity", "message")
        ):
            valid_findings.append(item)

    if not valid_findings and parsed:
        return Gate2Result(passed=False, reason="no valid findings in response")

    return Gate2Result(passed=True, findings=valid_findings)


# ---------------------------------------------------------------------------
# Gate 3 — Off-topic detection (URL subject vs content)
# ---------------------------------------------------------------------------

_OFFTOPIC_KEYWORDS = {
    "login": ["sign in", "log in", "username", "password", "email", "account"],
    "generic": ["click here", "contact us", "subscribe", "newsletter", "sign up"],
}


@dataclass
class Gate3Result:
    passed: bool
    reason: str = ""


def gate3_offtopic(text: str, url: str) -> Gate3Result:
    """Gate 3: Detect if AI output is unrelated to the target URL."""
    # Extract domain/key terms from URL
    parsed_url = url.lower()
    url_terms = set(re.findall(r"[a-z]{4,}", parsed_url))

    # Count how many URL terms appear in the response
    text_lower = text.lower()
    matched = sum(1 for term in url_terms if term in text_lower)

    # If URL has meaningful terms but none appear, flag as suspicious
    if len(url_terms) >= 3 and matched == 0:
        return Gate3Result(passed=False, reason="AI output appears unrelated to URL")

    return Gate3Result(passed=True)


# ---------------------------------------------------------------------------
# Gate 4 — Length overflow check
# ---------------------------------------------------------------------------

MAX_MESSAGE_CHARS = 500
MAX_SUGGESTION_CHARS = 500


@dataclass
class Gate4Result:
    passed: bool
    reason: str = ""


def gate4_length_overflow(findings: list[dict[str, Any]]) -> Gate4Result:
    """Gate 4: Reject findings with message or suggestion exceeding limits."""
    for i, f in enumerate(findings):
        msg = f.get("message", "")
        sug = f.get("suggestion", "")
        if len(msg) > MAX_MESSAGE_CHARS:
            return Gate4Result(
                passed=False,
                reason=f"finding[{i}] message too long: {len(msg)} chars (max {MAX_MESSAGE_CHARS})",
            )
        if len(sug) > MAX_SUGGESTION_CHARS:
            return Gate4Result(
                passed=False,
                reason=f"finding[{i}] suggestion too long: {len(sug)} chars (max {MAX_SUGGESTION_CHARS})",
            )
    return Gate4Result(passed=True)


# ---------------------------------------------------------------------------
# Gate 5 — Empty response detection
# ---------------------------------------------------------------------------

@dataclass
class Gate5Result:
    passed: bool
    reason: str = ""


def gate5_empty_response(findings: list[dict[str, Any]], raw_text: str) -> Gate5Result:
    """Gate 5: Reject if response is empty or trivially small."""
    if not findings and raw_text.strip():
        # Non-empty text but no valid findings — likely a refusal or incomplete response
        return Gate5Result(passed=False, reason="non-empty text produced no valid findings")

    if not raw_text.strip():
        return Gate5Result(passed=False, reason="completely empty response")

    return Gate5Result(passed=True)


# ---------------------------------------------------------------------------
# Gate 6 — URL hallucination detection
# ---------------------------------------------------------------------------

# Known-fake URL patterns (simplified check — not exhaustive)
_HALLUCINATED_DOMAINS = re.compile(
    r"(example\.(com|org|net)|"
    r"test\d*\.com|"
    r"foo\.bar|"
    r"localhost|"
    r"\d+\.\d+\.\d+\.\d+)",
    re.IGNORECASE,
)
_ABSOLUTE_URL_RE = re.compile(r"https?://[^\s\"'<>]+")


@dataclass
class Gate6Result:
    passed: bool
    reason: str = ""


def gate6_url_hallucination(findings: list[dict[str, Any]]) -> Gate6Result:
    """Gate 6: Reject findings that contain fake/hallucinated URLs."""
    for i, f in enumerate(findings):
        msg = f.get("message", "")
        loc = f.get("location", "")
        for url in _ABSOLUTE_URL_RE.findall(msg + loc):
            if _HALLUCINATED_DOMAINS.search(url):
                return Gate6Result(
                    passed=False,
                    reason=f"finding[{i}] contains hallucinated URL: {url[:50]}",
                )
    return Gate6Result(passed=True)


# ---------------------------------------------------------------------------
# Composite gate runner
# ---------------------------------------------------------------------------

ALL_GATES = [
    ("rejection", gate1_rejection),
    ("json_parse", gate2_json_parse),
    ("offtopic", gate3_offtopic),
    ("length_overflow", gate4_length_overflow),
    ("empty_response", gate5_empty_response),
    ("url_hallucination", gate6_url_hallucination),
]


@dataclass
class GateOutcome:
    gate_name: str
    passed: bool
    reason: str = ""


def run_all_gates(raw_text: str, url: str) -> tuple[bool, list[GateOutcome], list[dict[str, Any]]]:
    """Run all 6 gates. Returns (all_passed, outcomes, validated_findings)."""
    outcomes: list[GateOutcome] = []
    findings: list[dict[str, Any]] = []

    # Gate 1
    r = gate1_rejection(raw_text)
    outcomes.append(GateOutcome("rejection", r.passed, r.reason))
    if not r.passed:
        return False, outcomes, []

    # Gate 2
    r2 = gate2_json_parse(raw_text)
    outcomes.append(GateOutcome("json_parse", r2.passed, r2.reason))
    if not r2.passed:
        return False, outcomes, []
    findings = r2.findings

    # Gate 3
    r3 = gate3_offtopic(raw_text, url)
    outcomes.append(GateOutcome("offtopic", r3.passed, r3.reason))
    if not r3.passed:
        return False, outcomes, []

    # Gate 4
    r4 = gate4_length_overflow(findings)
    outcomes.append(GateOutcome("length_overflow", r4.passed, r4.reason))
    if not r4.passed:
        return False, outcomes, []

    # Gate 5
    r5 = gate5_empty_response(findings, raw_text)
    outcomes.append(GateOutcome("empty_response", r5.passed, r5.reason))
    if not r5.passed:
        return False, outcomes, []

    # Gate 6
    r6 = gate6_url_hallucination(findings)
    outcomes.append(GateOutcome("url_hallucination", r6.passed, r6.reason))
    if not r6.passed:
        return False, outcomes, []

    return True, outcomes, findings
