"""Smoke tests for LaunchLint checks.

Run: python -m pytest tests/  (or python tests/test_checks.py)
"""

from __future__ import annotations

import sys
from pathlib import Path

# Allow running as a plain script without pytest installed.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bs4 import BeautifulSoup

from launchlint import checks
from launchlint.core import Severity


REPO = Path(__file__).resolve().parent.parent
MINIMAL = REPO / "examples" / "minimal.html"
PERFECT = REPO / "examples" / "perfect.html"


def _ctx_for(html: str, kind: str = "path") -> dict:
    return {
        "soup": BeautifulSoup(html, "html.parser"),
        "kind": kind,
        "target": "https://example.com/x",
        "final_url": "https://example.com/x" if kind == "url" else None,
        "timeout": 5.0,
        "max_links": 5,
        "urljoin": __import__("urllib.parse").parse.urljoin,
        "session": None,
    }


def _issues_for(html: str, check: str, kind: str = "path"):
    return list(checks.run_check(check, _ctx_for(html, kind)))


def _assert_no_error(issues, msg=""):
    errs = [i for i in issues if i.severity == Severity.ERROR]
    assert not errs, f"unexpected errors: {[(i.check, i.message) for i in errs]} {msg}"


# ---------- SEO -----------------------------------------------------------

def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_seo_clean():
    html = _read(PERFECT)
    issues = _issues_for(html, "seo")
    _assert_no_error(issues, "perfect page should have no SEO errors")


def test_seo_missing_title():
    html = "<html><body><h1>No title</h1></body></html>"
    issues = _issues_for(html, "seo")
    assert any("title" in i.message.lower() for i in issues if i.severity == Severity.ERROR)


def test_seo_short_title():
    html = "<html><head><title>Hi</title></head><body><h1>x</h1></body></html>"
    issues = _issues_for(html, "seo")
    assert any("too short" in i.message for i in issues)


def test_seo_missing_meta_description():
    html = "<html><head><title>OK length title here for sure</title></head><body><h1>x</h1></body></html>"
    issues = _issues_for(html, "seo")
    assert any("meta description" in i.message.lower() for i in issues)


def test_seo_missing_h1():
    html = "<html><head><title>Long enough title for sure here</title><meta name='description' content='x'></head><body><p>no h1</p></body></html>"
    issues = _issues_for(html, "seo")
    assert any(i.severity == Severity.ERROR and "<h1>" in i.message for i in issues)


# ---------- A11Y ----------------------------------------------------------

def test_a11y_missing_lang():
    html = "<html><body><h1>x</h1></body></html>"
    issues = _issues_for(html, "a11y")
    assert any("lang" in i.message for i in issues if i.severity == Severity.ERROR)


def test_a11y_image_no_alt():
    html = '<html lang="en"><body><img src="/x.png"></body></html>'
    issues = _issues_for(html, "a11y")
    assert any("alt" in i.message for i in issues if i.severity == Severity.ERROR)


def test_a11y_heading_skip():
    html = '<html lang="en"><body><h1>a</h1><h3>b</h3></body></html>'
    issues = _issues_for(html, "a11y")
    assert any("heading skip" in i.message.lower() for i in issues)


def test_a11y_clean():
    html = _read(PERFECT)
    issues = _issues_for(html, "a11y")
    _assert_no_error(issues, "perfect page should have no a11y errors")


# ---------- DOCTOR --------------------------------------------------------

def test_doctor_imports():
    """Verify our deps import cleanly (used by --doctor)."""
    import requests  # noqa: F401
    import bs4  # noqa: F401
    assert True


# ---------- End-to-end audit (local file mode) ---------------------------

def test_end_to_end_minimal_file():
    """Run full audit against the bundled minimal.html — no network needed."""
    from launchlint.core import run_audit
    result = run_audit(
        target=str(MINIMAL),  # pass the file directly
        kind="path",
        checks=["seo", "a11y"],  # skip links (needs network)
        timeout=2.0,
        max_links=0,
    )
    # minimal.html is broken on purpose — should produce at least one issue
    assert len(result.issues) >= 1, "minimal.html should trigger at least one audit issue"
    summary = result.summary()
    assert summary["error"] >= 1, "minimal.html should have at least one error (no alt on img)"


def test_end_to_end_perfect_file():
    """Run full audit against perfect.html — should be clean."""
    from launchlint.core import run_audit
    result = run_audit(
        target=str(PERFECT),
        kind="path",
        checks=["seo", "a11y"],
        timeout=2.0,
        max_links=0,
    )
    _assert_no_error(result.issues, "perfect.html should have no errors")


if __name__ == "__main__":
    # Plain-script runner so tests work without pytest installed.
    import traceback
    funcs = [v for k, v in globals().items() if k.startswith("test_") and callable(v)]
    failures = 0
    for fn in funcs:
        try:
            fn()
            print(f"PASS  {fn.__name__}")
        except Exception:
            failures += 1
            print(f"FAIL  {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(funcs) - failures}/{len(funcs)} passed")
    sys.exit(1 if failures else 0)