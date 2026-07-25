"""AI-powered check using Anthropic + verification gates.

Integrates: ai_gateway + verification_gates + billing_guard
to provide a safe, cost-controlled AI auditing layer.
"""

from __future__ import annotations

import logging
from typing import Any, Iterator

from .ai_gateway import AIGateway, AIResponse
from .billing_guard import BillingGuard, BillingExceeded
from .core import Issue, Severity
from .verification_gates import run_all_gates

logger = logging.getLogger(__name__)


def check_ai(
    ctx: dict[str, Any],
    gateway: AIGateway,
    billing: BillingGuard,
) -> Iterator[Issue]:
    """AI-powered launch audit — returns issues found by the LLM.

    This check wraps the AI gateway with 6 verification gates and billing guards.
    If any gate fails or billing is exceeded, the check yields a WARN and logs
    the failure reason — it never silently discards a page.
    """
    soup = ctx["soup"]
    target = ctx["target"]
    final_url = ctx.get("final_url") or target
    max_findings = ctx.get("ai_max_findings", 30)

    # Get page text for analysis
    page_text = _extract_page_text(soup)

    if len(page_text) < 100:
        yield Issue(
            "ai",
            Severity.INFO,
            "Page too small to analyze meaningfully.",
        )
        return

    try:
        response: AIResponse = gateway.audit_page(page_text, final_url, max_findings)
    except Exception as exc:
        billing.record_call(0, 0, 0, gate_failed=True)
        billing.assert_within_budget()
        yield Issue(
            "ai",
            Severity.WARN,
            f"AI analysis failed: {exc}",
        )
        return

    # Record usage
    billing.record_call(
        input_tokens=response.usage.get("input_tokens", 0),
        output_tokens=response.usage.get("output_tokens", 0),
        findings_count=0,  # will update after gates
        gate_failed=False,
    )

    # Run all 6 gates
    all_passed, outcomes, validated_findings = run_all_gates(response.raw_text, final_url)

    if not all_passed:
        failed = [o.gate_name for o in outcomes if not o.passed]
        billing.record_call(0, 0, 0, gate_failed=True)
        billing.assert_within_budget()
        logger.warning(
            "AI output failed verification gates: %s. First failure: %s",
            failed,
            next(o.reason for o in outcomes if not o.passed),
        )
        yield Issue(
            "ai",
            Severity.WARN,
            f"AI output failed verification ({failed[0]}). Results discarded.",
            suggestion="Check --ai-key and network connectivity.",
        )
        return

    # Update billing with actual findings count
    billing.record_call(0, 0, len(validated_findings), gate_failed=False)

    # Budget assertion
    try:
        billing.assert_within_budget()
    except BillingExceeded as exc:
        yield Issue(
            "ai",
            Severity.ERROR,
            str(exc),
        )
        return

    # Convert findings to Issue objects
    for f in validated_findings:
        severity = _map_severity(f.get("severity", "info"))
        yield Issue(
            check=f.get("check", "ai"),
            severity=severity,
            message=f.get("message", "(no message)"),
            location=f.get("location", ""),
            suggestion=f.get("suggestion", ""),
        )


def _extract_page_text(soup: Any) -> str:
    """Get meaningful text content from BeautifulSoup."""
    # Remove script and style elements
    for tag in soup.find_all(["script", "style", "noscript"]):
        tag.decompose()

    text = soup.get_text(separator=" ", strip=True)
    # Collapse whitespace
    import re
    text = re.sub(r"\s+", " ", text)
    return text


def _map_severity(value: str) -> Severity:
    mapping = {
        "error": Severity.ERROR,
        "warn": Severity.WARN,
        "info": Severity.INFO,
    }
    return mapping.get(value.lower(), Severity.WARN)
