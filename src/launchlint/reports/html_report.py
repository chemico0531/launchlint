"""Simple HTML report fallback for LaunchLint."""

from __future__ import annotations

from html import escape
from pathlib import Path

from .. import __version__
from ..core import AuditResult, Severity
from .brand import BrandConfig
from .templates import (
    calculate_score,
    format_datetime,
    issues_by_severity,
    score_interpretation,
    severity_label,
)


HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>{title}</title>
<style>
:root {{ --accent: {accent}; --error: #DC2626; --warn: #D97706; --info: #2563EB; }}
body {{ font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 0; color: #1F2937; line-height: 1.5; }}
.container {{ max-width: 760px; margin: 0 auto; padding: 40px 24px; }}
header {{ text-align: center; margin-bottom: 48px; }}
.logo {{ max-width: 220px; max-height: 80px; margin-bottom: 16px; }}
h1 {{ color: var(--accent); margin: 0 0 8px; font-size: 2rem; }}
h2 {{ color: var(--accent); margin-top: 40px; font-size: 1.4rem; }}
.score {{ font-size: 4rem; font-weight: bold; text-align: center; margin: 16px 0; }}
.score.good {{ color: #16A34A; }} .score.ok {{ color: var(--warn); }} .score.bad {{ color: var(--error); }}
.summary {{ text-align: center; margin-bottom: 24px; }}
.badge {{ display: inline-block; padding: 4px 10px; border-radius: 4px; font-weight: 600; font-size: 0.85rem; margin: 0 4px; }}
.badge.error {{ background: #FEE2E2; color: #991B1B; }}
.badge.warn {{ background: #FEF3C7; color: #92400E; }}
.badge.info {{ background: #DBEAFE; color: #1E40AF; }}
.card {{ border: 1px solid #E5E7EB; border-radius: 6px; padding: 16px; margin-bottom: 16px; }}
.card-header {{ display: flex; align-items: center; gap: 12px; margin-bottom: 8px; }}
.card-title {{ font-weight: 700; margin: 0; }}
.meta {{ color: #6B7280; font-size: 0.9rem; }}
table {{ width: 100%; border-collapse: collapse; margin-top: 12px; }}
td {{ border: 1px solid #E5E7EB; padding: 8px; }}
td:first-child {{ background: #F9FAFB; width: 35%; font-weight: 500; }}
footer {{ text-align: center; color: #6B7280; margin-top: 48px; font-size: 0.9rem; }}
</style>
</head>
<body>
<div class="container">
{body}
{footer}
</div>
</body>
</html>
"""


def _score_class(score: int) -> str:
    if score >= 90:
        return "good"
    if score >= 70:
        return "ok"
    return "bad"


def generate_html(
    result: AuditResult,
    brand: BrandConfig,
    output_path: str | Path,
) -> Path:
    """Generate a white-label HTML report and write it to output_path."""
    output_path = Path(output_path)
    score = calculate_score(result)
    summary = result.summary()

    parts: list[str] = []
    parts.append('<header>')
    if brand.logo:
        parts.append(f'<img class="logo" src="{escape(brand.logo)}" alt="Logo">')
    parts.append(f'<h1>{escape(brand.report_title)}</h1>')
    if brand.client_name:
        parts.append(f'<p>Prepared for {escape(brand.client_name)}</p>')
    parts.append(f'<p>Target: <strong>{escape(result.target)}</strong></p>')
    parts.append(f'<p class="meta">Generated: {format_datetime()}</p>')
    if brand.agency_name:
        parts.append(f'<p class="meta">{escape(brand.agency_name)}')
        if brand.agency_contact:
            parts.append(f' · {escape(brand.agency_contact)}')
        parts.append('</p>')
    parts.append('</header>')

    parts.append('<h2>Executive Summary</h2>')
    parts.append(f'<div class="score {_score_class(score)}">{score}<span style="font-size:1.5rem;color:#6B7280">/100</span></div>')
    parts.append(
        f'<div class="summary">'
        f'<span class="badge error">{summary["error"]} errors</span>'
        f'<span class="badge warn">{summary["warn"]} warnings</span>'
        f'<span class="badge info">{summary["info"]} info</span>'
        f'</div>'
    )
    parts.append(f'<p class="summary">{escape(score_interpretation(score))}</p>')

    parts.append('<h2>Findings</h2>')
    grouped = issues_by_severity(result)
    any_findings = False
    for severity in (Severity.ERROR, Severity.WARN, Severity.INFO):
        items = grouped[severity]
        if not items:
            continue
        any_findings = True
        parts.append(f'<h3>{escape(severity_label(severity))} ({len(items)})</h3>')
        for issue in items:
            parts.append('<div class="card">')
            parts.append('<div class="card-header">')
            parts.append(f'<span class="badge {severity.value}">{escape(severity_label(severity))}</span>')
            parts.append(f'<span class="card-title">{escape(issue.check)}</span>')
            parts.append('</div>')
            parts.append(f'<p>{escape(issue.message)}</p>')
            if issue.location:
                parts.append(f'<p class="meta">Location: {escape(issue.location)}</p>')
            if issue.suggestion:
                parts.append(f'<p class="meta">Suggestion: {escape(issue.suggestion)}</p>')
            parts.append('</div>')
    if not any_findings:
        parts.append('<p>No findings. Clean launch!</p>')

    parts.append('<h2>Appendix</h2>')
    parts.append('<table>')
    rows = [
        ("Target", result.target),
        ("Checks run", ", ".join(result.checks_run)),
        ("Duration", f"{result.duration_ms} ms"),
        ("Final URL", result.meta.get("final_url", "—")),
        ("Content type", result.meta.get("content_type", "—")),
        ("Size", f"{result.meta.get('size_bytes', 0):,} bytes"),
    ]
    for key, value in rows:
        parts.append(f'<tr><td>{escape(key)}</td><td>{escape(str(value))}</td></tr>')
    parts.append('</table>')

    html = HTML_TEMPLATE.format(
        title=escape(brand.report_title),
        accent=brand.accent_color,
        body="\n".join(parts),
        version=__version__,
        footer=(
            '<footer>Generated by LaunchLint v{version}</footer>'
            if not brand.hide_branding
            else ""
        ),
    )
    output_path.write_text(html, encoding="utf-8")
    return output_path
