"""Core data types and audit orchestration."""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

# Import checks lazily inside run_audit to avoid circular import
# (checks.py imports Issue/Severity from this module).


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

    # Lazy import — checks.py depends on Issue/Severity from this module.
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

    for check_name in checks:
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

    result.duration_ms = int((time.time() - started) * 1000)
    return result