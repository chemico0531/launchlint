"""Shared helpers for report generation (PDF + HTML)."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from urllib.parse import urlparse

from ..core import AuditResult, Severity


def calculate_score(result: AuditResult) -> int:
    """Score from 0-100 based on issue severity counts.

    error: -15, warn: -5, info: -1, minimum 0.
    """
    summary = result.summary()
    raw = 100 - summary["error"] * 15 - summary["warn"] * 5 - summary["info"] * 1
    return max(0, raw)


def score_interpretation(score: int) -> str:
    """Short interpretation of the launch-readiness score."""
    if score >= 90:
        return "Clean launch. Ship it."
    if score >= 70:
        return "No blockers, but review warnings before launch."
    if score >= 50:
        return "Issues should be fixed before launch."
    return "Significant blockers. Do not launch."


def severity_label(severity: Severity) -> str:
    return {Severity.ERROR: "ERROR", Severity.WARN: "WARNING", Severity.INFO: "INFO"}[
        severity
    ]


def issues_by_severity(result: AuditResult) -> dict[Severity, list[Any]]:
    grouped: dict[Severity, list[Any]] = {
        Severity.ERROR: [],
        Severity.WARN: [],
        Severity.INFO: [],
    }
    for issue in result.issues:
        grouped[issue.severity].append(issue)
    return grouped


def default_report_filename(result: AuditResult, ext: str = "pdf") -> str:
    """Generate default filename like launchlint-example.com-20260726-143052.pdf."""
    domain = _extract_domain(result.target)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"launchlint-{domain}-{timestamp}.{ext.lstrip('.')}"


def _extract_domain(target: str) -> str:
    if target.startswith(("http://", "https://")):
        parsed = urlparse(target)
        return parsed.netloc.replace(":", "_")
    from pathlib import Path

    p = Path(target)
    name = p.stem if p.suffix else p.name
    return name or "local"


def hex_to_rgb(color: str) -> tuple[float, float, float]:
    """Convert #RRGGBB to ReportLab-compatible 0-1 RGB tuple."""
    color = color.lstrip("#")
    return tuple(int(color[i : i + 2], 16) / 255.0 for i in (0, 2, 4))


def format_datetime() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
