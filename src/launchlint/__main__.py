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
import sys
from pathlib import Path
from typing import Iterable

from . import __version__
from .core import AuditResult, Severity, run_audit
from .checks import AVAILABLE_CHECKS


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

    try:
        result = run_audit(
            target=target,
            kind=kind,
            checks=checks,
            timeout=args.timeout,
            max_links=args.max_links,
        )
    except Exception as exc:  # pragma: no cover — defensive
        print(f"launchlint: audit failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        _print_json(result)
    else:
        _print_text(result)

    threshold = {
        "never": None,
        "info": Severity.INFO,
        "warn": Severity.WARN,
        "error": Severity.ERROR,
    }[args.fail_on]
    if threshold is None:
        return 0
    counts = result.summary()
    order = {Severity.INFO: 1, Severity.WARN: 2, Severity.ERROR: 3}
    target_order = order[threshold]
    if any(order[i.severity] >= target_order for i in result.issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())