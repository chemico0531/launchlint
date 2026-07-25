"""PDF report generation using ReportLab Platypus."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, LETTER
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    Image,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from .. import __version__
from ..core import AuditResult, Severity
from .brand import BrandConfig
from .templates import (
    calculate_score,
    format_datetime,
    hex_to_rgb,
    issues_by_severity,
    score_interpretation,
    severity_label,
)


def _escape_xml(text: str) -> str:
    """Escape text for ReportLab Paragraph XML/HTML subset."""
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _page_size(name: str) -> tuple[float, float]:
    return {"A4": A4, "LETTER": LETTER}[name.upper()]


def _maybe_load_logo(logo: str, max_width: float, max_height: float) -> Image | None:
    """Load a logo from local path or URL into a ReportLab Image."""
    if not logo:
        return None

    try:
        if logo.startswith(("http://", "https://")):
            import requests

            resp = requests.get(logo, timeout=15)
            resp.raise_for_status()
            img_bytes = io.BytesIO(resp.content)
        else:
            p = Path(logo)
            if not p.exists():
                return None
            img_bytes = io.BytesIO(p.read_bytes())

        img = Image(img_bytes)
        # Preserve aspect ratio
        ratio = min(max_width / img.imageWidth, max_height / img.imageHeight, 1.0)
        img.drawWidth = img.imageWidth * ratio
        img.drawHeight = img.imageHeight * ratio
        return img
    except Exception:
        # Logo is optional; fail gracefully
        return None


def _make_styles(accent_rgb: tuple[float, float, float]) -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    accent = colors.Color(*accent_rgb)
    dark = colors.HexColor("#1F2937")
    muted = colors.HexColor("#6B7280")
    return {
        "title": ParagraphStyle(
            "ReportTitle",
            parent=base["Heading1"],
            fontSize=24,
            leading=30,
            textColor=accent,
            alignment=1,  # center
            spaceAfter=12,
        ),
        "subtitle": ParagraphStyle(
            "ReportSubtitle",
            parent=base["Normal"],
            fontSize=12,
            leading=16,
            textColor=dark,
            alignment=1,
        ),
        "muted": ParagraphStyle(
            "Muted",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=muted,
            alignment=1,
        ),
        "section": ParagraphStyle(
            "SectionHeading",
            parent=base["Heading2"],
            fontSize=16,
            leading=20,
            textColor=accent,
            spaceAfter=10,
            spaceBefore=14,
        ),
        "body": ParagraphStyle(
            "Body",
            parent=base["Normal"],
            fontSize=10,
            leading=14,
            textColor=dark,
        ),
        "card_title": ParagraphStyle(
            "CardTitle",
            parent=base["Normal"],
            fontSize=11,
            leading=14,
            textColor=dark,
        ),
        "card_meta": ParagraphStyle(
            "CardMeta",
            parent=base["Normal"],
            fontSize=9,
            leading=12,
            textColor=muted,
        ),
    }


def generate_pdf(
    result: AuditResult,
    brand: BrandConfig,
    output_path: str | Path,
) -> Path:
    """Generate a white-label PDF report and write it to output_path."""
    output_path = Path(output_path)
    page_size = _page_size(brand.page_size)
    margin = brand.margin_mm * mm
    accent_rgb = hex_to_rgb(brand.accent_color)
    accent = colors.Color(*accent_rgb)

    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=page_size,
        rightMargin=margin,
        leftMargin=margin,
        topMargin=margin,
        bottomMargin=margin,
    )

    styles = _make_styles(accent_rgb)
    story: list[Any] = []
    width, _ = page_size
    usable_width = width - 2 * margin

    # ---- Cover page ---------------------------------------------------------
    logo = _maybe_load_logo(brand.logo, max_width=80 * mm, max_height=25 * mm)
    if logo:
        story.append(logo)
        story.append(Spacer(1, 8 * mm))
    else:
        story.append(Spacer(1, 25 * mm))

    story.append(Paragraph(_escape_xml(brand.report_title), styles["title"]))
    if brand.client_name:
        story.append(Paragraph(f"Prepared for {_escape_xml(brand.client_name)}", styles["subtitle"]))
    story.append(Spacer(1, 6 * mm))
    story.append(Paragraph(f"Target: <b>{_escape_xml(result.target)}</b>", styles["subtitle"]))
    story.append(Paragraph(f"Generated: {format_datetime()}", styles["muted"]))

    if brand.agency_name or brand.agency_contact:
        story.append(Spacer(1, 20 * mm))
        agency_lines = [_escape_xml(brand.agency_name)]
        if brand.agency_contact:
            agency_lines.append(_escape_xml(brand.agency_contact))
        story.append(Paragraph("<br/>".join(agency_lines), styles["muted"]))

    story.append(Spacer(1, 15 * mm))

    # ---- Executive summary --------------------------------------------------
    story.append(Paragraph("Executive Summary", styles["section"]))
    score = calculate_score(result)
    summary = result.summary()

    score_table = Table(
        [[
            _score_cell(score, accent, styles),
            _summary_cell(summary, styles),
        ]],
        colWidths=[usable_width * 0.35, usable_width * 0.65],
    )
    score_table.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#E5E7EB")),
        ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#F9FAFB")),
    ]))
    story.append(score_table)
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph(score_interpretation(score), styles["subtitle"]))

    # ---- Findings -----------------------------------------------------------
    story.append(Paragraph("Findings", styles["section"]))
    grouped = issues_by_severity(result)
    for severity in (Severity.ERROR, Severity.WARN, Severity.INFO):
        items = grouped[severity]
        if not items:
            continue
        story.append(Paragraph(f"{severity_label(severity)} ({len(items)})", styles["section"]))
        for issue in items:
            story.append(_finding_card(issue, severity, styles, usable_width))

    # ---- Appendix -----------------------------------------------------------
    story.append(Paragraph("Appendix", styles["section"]))
    appendix = [
        ["Target", result.target],
        ["Checks run", ", ".join(result.checks_run)],
        ["Duration", f"{result.duration_ms} ms"],
        ["Final URL", result.meta.get("final_url", "—")],
        ["Content type", result.meta.get("content_type", "—")],
        ["Size", f"{result.meta.get('size_bytes', 0):,} bytes"],
    ]
    appendix_table = Table(appendix, colWidths=[usable_width * 0.35, usable_width * 0.65])
    appendix_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#F9FAFB")),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    story.append(appendix_table)
    story.append(Spacer(1, 6 * mm))
    if not brand.hide_branding:
        story.append(
            Paragraph(
                f"Generated by LaunchLint v{__version__}",
                styles["muted"],
            )
        )

    doc.build(story)
    return output_path


def _score_cell(score: int, accent: colors.Color, styles: dict[str, ParagraphStyle]) -> Paragraph:
    color = _score_color(score)
    return Paragraph(
        f"<font size='36' color='{color.hexval()}'><b>{score}</b></font><br/>"
        f"<font size='9' color='#6B7280'>/ 100</font>",
        ParagraphStyle(
            "ScoreCell",
            parent=styles["body"],
            alignment=1,
            leading=30,
        ),
    )


def _summary_cell(summary: dict[str, int], styles: dict[str, ParagraphStyle]) -> Paragraph:
    lines = [
        f"<font color='#DC2626'><b>{summary['error']}</b> errors</font>",
        f"<font color='#D97706'><b>{summary['warn']}</b> warnings</font>",
        f"<font color='#2563EB'><b>{summary['info']}</b> info</font>",
    ]
    return Paragraph("<br/>".join(lines), ParagraphStyle(
        "SummaryCell",
        parent=styles["body"],
        leading=18,
    ))


def _score_color(score: int) -> colors.Color:
    if score >= 90:
        return colors.HexColor("#16A34A")
    if score >= 70:
        return colors.HexColor("#D97706")
    return colors.HexColor("#DC2626")


def _severity_badge_color(severity: Severity) -> str:
    return {
        Severity.ERROR: "#FEE2E2",
        Severity.WARN: "#FEF3C7",
        Severity.INFO: "#DBEAFE",
    }[severity]


def _severity_text_color(severity: Severity) -> str:
    return {
        Severity.ERROR: "#991B1B",
        Severity.WARN: "#92400E",
        Severity.INFO: "#1E40AF",
    }[severity]


def _finding_card(
    issue: Any,
    severity: Severity,
    styles: dict[str, ParagraphStyle],
    usable_width: float,
) -> KeepTogether:
    badge = Table(
        [[Paragraph(severity_label(severity), styles["card_title"])]],
        colWidths=[usable_width * 0.22],
    )
    badge.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(_severity_badge_color(severity))),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))

    title = Paragraph(
        f"<font color='{_severity_text_color(severity)}'><b>{_escape_xml(issue.check)}</b></font>",
        styles["card_title"],
    )
    body_parts = [_escape_xml(issue.message)]
    if issue.location:
        body_parts.append(
            f"<br/><font color='#6B7280'>Location:</font> {_escape_xml(issue.location)}"
        )
    if issue.suggestion:
        body_parts.append(
            f"<br/><font color='#6B7280'>Suggestion:</font> {_escape_xml(issue.suggestion)}"
        )
    body = Paragraph("".join(body_parts), styles["body"])

    card = Table(
        [[badge, title], ["", body]],
        colWidths=[usable_width * 0.24, usable_width * 0.76],
    )
    card.setStyle(TableStyle([
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#E5E7EB")),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
    ]))
    return KeepTogether([card, Spacer(1, 3 * mm)])
