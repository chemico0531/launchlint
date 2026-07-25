"""LaunchLint CLI entry point.

Usage:
    launchlint <url-or-path>           # audit one target
    launchlint <url> --json            # JSON output
    launchlint <url> --fail-on warn    # exit non-zero on warnings
    launchlint <url> --checks seo      # run only specific checks
    launchlint --doctor                # self-diagnose environment
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable

from . import __version__
from .core import AuditResult, Severity, run_audit
from .checks import AVAILABLE_CHECKS
from .reports import (
    BrandConfig,
    default_report_filename,
    generate_html,
    generate_pdf,
    load_brand_config,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="launchlint",
        description="Local-first pre-launch audit. SEO, broken links, a11y, config.",
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="URL (https://...) or local path (./dist, file:///path). Skip when using --doctor.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON report instead of pretty text.",
    )
    parser.add_argument(
        "--fail-on",
        choices=["error", "warn", "info", "never"],
        default="error",
        help="Minimum severity that causes non-zero exit. Default: error.",
    )
    parser.add_argument(
        "--checks",
        help="Comma-separated check names to run. Default: all.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Per-request HTTP timeout (seconds). Default: 10.",
    )
    parser.add_argument(
        "--max-links",
        type=int,
        default=50,
        help="Maximum number of links to probe for broken-link check. Default: 50.",
    )
    parser.add_argument(
        "--doctor",
        action="store_true",
        help="Self-diagnose environment (no audit run).",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"launchlint {__version__}",
    )
    # AI-powered check flags
    parser.add_argument(
        "--ai-key",
        dest="ai_key",
        metavar="KEY",
        default=None,
        help="Anthropic API key. Default: read from ANTHROPIC_API_KEY env var.",
    )
    parser.add_argument(
        "--ai-model",
        dest="ai_model",
        default="claude-haiku-4-5-20251001",
        help="Model ID for AI analysis. Default: claude-haiku-4-5-20251001.",
    )
    parser.add_argument(
        "--ai-max-findings",
        dest="ai_max_findings",
        type=int,
        default=30,
        help="Maximum findings per page from AI. Default: 30.",
    )
    parser.add_argument(
        "--ai-budget",
        dest="ai_budget",
        type=int,
        default=100_000,
        metavar="TOKENS",
        help="Max output tokens for AI analysis (budget guard). Default: 100000.",
    )
    parser.add_argument(
        "--ai-disable",
        action="store_true",
        help="Disable AI-powered check even if --ai-key is available.",
    )
    # Report generation flags
    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate a PDF or HTML report after the audit.",
    )
    parser.add_argument(
        "--report-format",
        dest="report_format",
        choices=["pdf", "html"],
        default="pdf",
        help="Report format. Default: pdf.",
    )
    parser.add_argument(
        "--pdf-output",
        dest="pdf_output",
        metavar="PATH",
        default=None,
        help="Custom report output path. Default: launchlint-<domain>-YYYYMMDD-HHMMSS.<ext>",
    )
    parser.add_argument(
        "--brand-config",
        dest="brand_config",
        metavar="PATH",
        default=None,
        help="JSON brand config file for white-label reports.",
    )
    parser.add_argument(
        "--logo",
        default=None,
        help="Logo path or URL (overrides brand config).",
    )
    parser.add_argument(
        "--agency-name",
        dest="agency_name",
        default=None,
        help="Agency name (overrides brand config).",
    )
    parser.add_argument(
        "--agency-contact",
        dest="agency_contact",
        default=None,
        help="Agency contact line (overrides brand config).",
    )
    parser.add_argument(
        "--accent-color",
        dest="accent_color",
        default=None,
        help="Accent hex color, e.g. #2563EB (overrides brand config).",
    )
    parser.add_argument(
        "--client-name",
        dest="client_name",
        default=None,
        help="Client name shown on the report cover.",
    )
    parser.add_argument(
        "--report-title",
        dest="report_title",
        default=None,
        help="Report title (overrides brand config).",
    )
    parser.add_argument(
        "--hide-branding",
        dest="hide_branding",
        action="store_true",
        help="Hide 'Generated by LaunchLint' footer (white-label).",
    )
    return parser


def _print_text(result: AuditResult) -> None:
    print(f"\nLaunchLint v{__version__}")
    print(f"Target: {result.target}")
    print(f"Checks: {', '.join(result.checks_run)}")
    print(f"Duration: {result.duration_ms}ms\n")
    print(f"{'=' * 60}")
    for issue in result.issues:
        marker = {
            Severity.ERROR: "[X]",
            Severity.WARN: "[!]",
            Severity.INFO: "[i]",
        }[issue.severity]
        loc = f" @ {issue.location}" if issue.location else ""
        print(f"{marker} {issue.severity.value.upper():5s} {issue.check}{loc}")
        print(f"    {issue.message}")
        if issue.suggestion:
            print(f"    -> {issue.suggestion}")
    print(f"{'=' * 60}")
    summary = result.summary()
    print(
        f"  {summary['error']} errors  "
        f"{summary['warn']} warnings  "
        f"{summary['info']} info"
    )
    # Show AI billing summary if available
    billing = result.meta.get("ai_billing")
    if billing:
        print(
            f"  AI: {billing['api_calls']} calls, "
            f"{billing['output_tokens']:,} output tokens, "
            f"${billing['estimated_cost_usd']:.4f} est."
        )
    if summary["error"] == 0 and summary["warn"] == 0:
        print("\n  Clean launch. Ship it.")
    elif summary["error"] == 0:
        print("\n  No blockers, but review warnings before launch.")


def _print_json(result: AuditResult) -> None:
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


def _doctor() -> int:
    """Self-diagnose environment. Used by README quickstart."""
    print(f"LaunchLint v{__version__} — doctor\n")
    ok = True
    # Python version
    py = sys.version_info
    print(f"  Python: {py.major}.{py.minor}.{py.micro}", end="")
    if py >= (3, 10):
        print("  OK")
    else:
        print("  FAIL (need >= 3.10)")
        ok = False
    # Network
    try:
        import requests  # noqa: F401
        print(f"  requests: {requests.__version__}  OK")
    except ImportError:
        print("  requests: NOT INSTALLED  FAIL")
        ok = False
    try:
        import bs4  # noqa: F401
        print(f"  beautifulsoup4: {bs4.__version__}  OK")
    except ImportError:
        print("  beautifulsoup4: NOT INSTALLED  FAIL")
        ok = False
    # Anthropic SDK
    try:
        import anthropic  # noqa: F401
        print(f"  anthropic: {anthropic.__version__}  OK")
    except ImportError:
        print("  anthropic: NOT INSTALLED  FAIL (needed for --checks ai)")
        ok = False
    # API key
    if os.environ.get("ANTHROPIC_API_KEY"):
        print("  ANTHROPIC_API_KEY: set  OK")
    else:
        print("  ANTHROPIC_API_KEY: not set (use --ai-key or set env var)")
    print()
    print("  Checks available:", ", ".join(AVAILABLE_CHECKS))
    print()
    print("  OK — ready to launch." if ok else "  FAIL — fix issues above.")
    return 0 if ok else 1


def _select_checks(names: str | None) -> Iterable[str]:
    if not names:
        return AVAILABLE_CHECKS
    requested = [n.strip() for n in names.split(",") if n.strip()]
    unknown = [n for n in requested if n not in AVAILABLE_CHECKS]
    if unknown:
        raise SystemExit(
            f"Unknown check(s): {', '.join(unknown)}. "
            f"Available: {', '.join(AVAILABLE_CHECKS)}"
        )
    return requested


def _build_brand_config(args: argparse.Namespace) -> BrandConfig:
    """Load brand config from file and apply CLI overrides."""
    brand = load_brand_config(args.brand_config)
    overrides: dict[str, Any] = {
        "logo": args.logo,
        "agency_name": args.agency_name,
        "agency_contact": args.agency_contact,
        "accent_color": args.accent_color,
        "client_name": args.client_name,
        "report_title": args.report_title,
    }
    if args.hide_branding:
        overrides["hide_branding"] = True
    return brand.merge_overrides(**overrides)


def _resolve_target(target: str) -> tuple[str, str]:
    """Return (kind, normalized-target) where kind is 'url' or 'path'."""
    if target.startswith(("http://", "https://")):
        return "url", target
    if target.startswith("file://"):
        return "path", target[len("file://"):]
    p = Path(target).expanduser().resolve()
    if p.exists():
        return "path", str(p)
    raise SystemExit(
        f"Target not found: {target!r}\n"
        f"Pass a URL (https://...) or a local path (./dist)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.doctor:
        return _doctor()
    if not args.target:
        parser.error("target is required (or use --doctor)")

    kind, target = _resolve_target(args.target)
    checks = list(_select_checks(args.checks))

    # AI check requires URL mode (needs actual content to analyze)
    if "ai" in checks and kind != "url":
        print(
            "launchlint: --checks ai only works with URL targets (not local files).\n"
            "  Use: launchlint https://example.com --checks ai",
            file=sys.stderr,
        )
        return 1

    try:
        result = run_audit(
            target=target,
            kind=kind,
            checks=checks,
            timeout=args.timeout,
            max_links=args.max_links,
            ai_key=args.ai_key,
            ai_model=args.ai_model,
            ai_max_findings=args.ai_max_findings,
            ai_budget=args.ai_budget,
        )
    except Exception as exc:  # pragma: no cover — defensive
        print(f"launchlint: audit failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _print_json(result)
    else:
        _print_text(result)

    if args.report:
        try:
            brand = _build_brand_config(args)
            ext = "html" if args.report_format == "html" else "pdf"
            output = Path(args.pdf_output) if args.pdf_output else None
            if output is None:
                output = Path(default_report_filename(result, ext=ext))
            if ext == "html":
                generate_html(result, brand, output)
            else:
                generate_pdf(result, brand, output)
            print(f"\n  Report saved: {output.resolve()}")
        except Exception as exc:  # pragma: no cover — defensive
            print(f"launchlint: report generation failed: {exc}", file=sys.stderr)
            return 2

    threshold = {
        "never": None,
        "info": Severity.INFO,
        "warn": Severity.WARN,
        "error": Severity.ERROR,
    }[args.fail_on]
    if threshold is None:
        return 0
    order = {Severity.INFO: 1, Severity.WARN: 2, Severity.ERROR: 3}
    target_order = order[threshold]
    if any(order[i.severity] >= target_order for i in result.issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())