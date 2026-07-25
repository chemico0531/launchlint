"""Core data types and audit orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


class Severity(str, Enum):
    ERROR = "error"
    WARN = "warn"
    INFO = "info"


@dataclass
class Issue:
    check: str
    severity: Severity
    message: str
    location: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["severity"] = self.severity.value
        return d


@dataclass
class AuditResult:
    target: str
    checks_run: list[str]
    issues: list[Issue] = field(default_factory=list)
    duration_ms: int = 0
    meta: dict[str, Any] = field(default_factory=dict)

    def summary(self) -> dict[str, int]:
        out = {"error": 0, "warn": 0, "info": 0}
        for issue in self.issues:
            out[issue.severity.value] += 1
        return out

    def to_dict(self) -> dict[str, Any]:
        return {
            "target": self.target,
            "checks_run": self.checks_run,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary(),
            "duration_ms": self.duration_ms,
            "meta": self.meta,
        }


def _fetch_url(url: str, timeout: float) -> tuple[BeautifulSoup, str, dict[str, Any]]:
    """Fetch URL. Return (parsed html, final url, response meta)."""
    resp = requests.get(
        url,
        timeout=timeout,
        allow_redirects=True,
        headers={"User-Agent": f"LaunchLint/{__import__('launchlint').__version__}"},
    )
    resp.raise_for_status()
    meta = {
        "status_code": resp.status_code,
        "final_url": resp.url,
        "content_type": resp.headers.get("Content-Type", ""),
        "size_bytes": len(resp.content),
    }
    soup = BeautifulSoup(resp.text, "html.parser")
    return soup, resp.url, meta


def _load_path(path: str) -> tuple[BeautifulSoup, dict[str, Any]]:
    """Load local file or index.html from directory."""
    from pathlib import Path

    p = Path(path)
    if p.is_dir():
        index = p / "index.html"
        if not index.exists():
            raise FileNotFoundError(f"No index.html in {p}")
        p = index
    html = p.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "html.parser")
    return soup, {"file": str(p), "size_bytes": p.stat().st_size}


def run_audit(
    target: str,
    kind: str,
    checks: list[str],
    timeout: float = 10.0,
    max_links: int = 50,
    # AI check parameters
    ai_key: str | None = None,
    ai_model: str = "claude-haiku-4-5-20251001",
    ai_max_findings: int = 30,
    ai_budget: int = 100_000,
) -> AuditResult:
    """Run all requested checks against target. Returns AuditResult."""
    started = time.time()
    result = AuditResult(target=target, checks_run=checks)

    if kind == "url":
        soup, final_url, meta = _fetch_url(target, timeout)
        result.meta.update({"kind": "url", **meta})
    else:
        soup, meta = _load_path(target)
        result.meta.update({"kind": "path", **meta})
        final_url = None

    # Lazy import to avoid circular dependency
    from .checks import run_check, AVAILABLE_CHECKS

    ctx = {
        "soup": soup,
        "kind": kind,
        "target": target,
        "final_url": final_url,
        "timeout": timeout,
        "max_links": max_links,
        "urljoin": urljoin,
        "session": requests.Session(),
    }

    # AI check is special — handled separately with its own gateway
    ai_requested = "ai" in checks
    regular_checks = [c for c in checks if c != "ai"]

    # Run regular checks
    for check_name in regular_checks:
        if check_name not in AVAILABLE_CHECKS:
            result.issues.append(
                Issue(
                    check=check_name,
                    severity=Severity.WARN,
                    message=f"Unknown check skipped: {check_name}",
                )
            )
            continue
        try:
            for issue in run_check(check_name, ctx):
                result.issues.append(issue)
        except Exception as exc:  # pragma: no cover — defensive
            result.issues.append(
                Issue(
                    check=check_name,
                    severity=Severity.WARN,
                    message=f"Check crashed: {exc}",
                    suggestion="Open an issue with the target URL.",
                )
            )

    # Run AI check if requested
    if ai_requested:
        _run_ai_check(ctx, result, ai_key, ai_model, ai_max_findings, ai_budget)

    result.duration_ms = int((time.time() - started) * 1000)
    return result


def _run_ai_check(
    ctx: dict[str, Any],
    result: AuditResult,
    ai_key: str | None,
    ai_model: str,
    ai_max_findings: int,
    ai_budget: int,
) -> None:
    """Run the AI-powered check and append issues to result."""
    import os

    from .ai_gateway import AIGateway
    from .ai_check import check_ai
    from .billing_guard import BillingGuard

    key = ai_key or os.environ.get("ANTHROPIC_API_KEY")
    if not key:
        result.issues.append(
            Issue(
                check="ai",
                severity=Severity.WARN,
                message="AI check requested but no API key (--ai-key or ANTHROPIC_API_KEY).",
                suggestion="Get an API key from console.anthropic.com or use --ai-disable.",
            )
        )
        return

    try:
        gateway = AIGateway(api_key=key, model=ai_model)
    except Exception as exc:
        result.issues.append(
            Issue(check="ai", severity=Severity.WARN, message=f"AI gateway init failed: {exc}")
        )
        return

    billing = BillingGuard(max_findings=ai_max_findings, budget_tokens=ai_budget)
    ctx["ai_max_findings"] = ai_max_findings

    try:
        for issue in check_ai(ctx, gateway, billing):
            result.issues.append(issue)
    except Exception as exc:
        result.issues.append(
            Issue(
                check="ai",
                severity=Severity.WARN,
                message=f"AI check crashed: {exc}",
                suggestion="Open an issue with the target URL.",
            )
        )
        return

    # Store billing summary in meta
    result.meta["ai_billing"] = billing.summary()
