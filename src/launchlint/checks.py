"""All check implementations in one module for v0.1 simplicity.

Adding a new check = add function + add name to AVAILABLE_CHECKS.
Each check yields Issue objects; never raises (errors yield WARN).
"""

from __future__ import annotations

from typing import Any, Callable, Iterator
from urllib.parse import urljoin, urlparse

from .core import Issue, Severity


AVAILABLE_CHECKS = ["seo", "links", "a11y", "config", "ai"]


# ---------- SEO -----------------------------------------------------------

def check_seo(ctx: dict[str, Any]) -> Iterator[Issue]:
    soup = ctx["soup"]

    title = soup.find("title")
    title_text = title.get_text(strip=True) if title else ""
    if not title_text:
        yield Issue("seo", Severity.ERROR, "Missing <title> tag.")
    elif len(title_text) < 10:
        yield Issue(
            "seo", Severity.WARN,
            f"Title too short ({len(title_text)} chars).",
            location="<title>",
            suggestion="Aim for 30-60 characters with primary keyword.",
        )
    elif len(title_text) > 70:
        yield Issue(
            "seo", Severity.WARN,
            f"Title too long ({len(title_text)} chars).",
            location="<title>",
            suggestion="Google truncates around 60 chars in SERPs.",
        )

    meta_desc = soup.find("meta", attrs={"name": "description"})
    desc = meta_desc.get("content", "").strip() if meta_desc else ""
    if not desc:
        yield Issue("seo", Severity.WARN, "Missing meta description.")
    elif len(desc) < 70:
        yield Issue(
            "seo", Severity.INFO,
            f"Meta description short ({len(desc)} chars).",
            location='meta[name="description"]',
            suggestion="Aim for 120-160 chars. Include value prop + CTA.",
        )
    elif len(desc) > 160:
        yield Issue(
            "seo", Severity.WARN,
            f"Meta description too long ({len(desc)} chars).",
            location='meta[name="description"]',
            suggestion="Google truncates around 155-160 chars.",
        )

    h1s = soup.find_all("h1")
    if not h1s:
        yield Issue("seo", Severity.ERROR, "No <h1> tag on page.")
    elif len(h1s) > 1:
        yield Issue(
            "seo", Severity.WARN,
            f"Multiple <h1> tags ({len(h1s)}).",
            suggestion="Use one <h1> per page. Demote others to <h2>.",
        )

    canonical = soup.find("link", rel="canonical")
    if not canonical and ctx["kind"] == "url":
        yield Issue(
            "seo", Severity.INFO,
            "Missing canonical link.",
            suggestion='<link rel="canonical" href="..."> prevents duplicate-content dilution.',
        )

    # Open Graph
    og_title = soup.find("meta", attrs={"property": "og:title"})
    og_image = soup.find("meta", attrs={"property": "og:image"})
    og_desc = soup.find("meta", attrs={"property": "og:description"})
    if not (og_title or og_image or og_desc):
        yield Issue(
            "seo", Severity.INFO,
            "Missing Open Graph tags.",
            suggestion='og:title, og:description, og:image improve social sharing previews.',
        )

    # JSON-LD
    jsonld = soup.find_all("script", attrs={"type": "application/ld+json"})
    if not jsonld:
        yield Issue(
            "seo", Severity.INFO,
            "No JSON-LD structured data.",
            suggestion="Add schema.org markup for richer SERP features.",
        )


# ---------- LINKS ---------------------------------------------------------

def check_links(ctx: dict[str, Any]) -> Iterator[Issue]:
    """Detect broken internal + outbound links. Limited by max_links."""
    soup = ctx["soup"]
    base = ctx.get("final_url") or ctx["target"]
    parsed_base = urlparse(base)
    session: Any = ctx["session"]
    timeout = ctx["timeout"]
    max_links = ctx["max_links"]

    anchors = soup.find_all("a", href=True)
    seen: set[str] = set()
    broken = 0
    checked = 0
    for a in anchors:
        href = a.get("href", "").strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        absolute = urljoin(base, href)
        if absolute in seen:
            continue
        seen.add(absolute)
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            continue
        # Only probe when in URL mode, or local file with relative links
        if checked >= max_links:
            break
        checked += 1
        try:
            r = session.head(
                absolute,
                timeout=timeout,
                allow_redirects=True,
                headers={"User-Agent": "LaunchLint/0.1"},
            )
            if r.status_code in (405, 403):
                # Some servers reject HEAD — fall back to GET range request
                r = session.get(
                    absolute,
                    timeout=timeout,
                    allow_redirects=True,
                    stream=True,
                    headers={"User-Agent": "LaunchLint/0.1", "Range": "bytes=0-0"},
                )
            if r.status_code >= 400:
                broken += 1
                same_origin = parsed.netloc == parsed_base.netloc
                yield Issue(
                    "links",
                    Severity.ERROR if same_origin else Severity.WARN,
                    f"Broken link ({r.status_code}): {absolute}",
                    location=f'<a href="{href}">',
                    suggestion="Fix or remove the link before launch.",
                )
        except Exception as exc:
            yield Issue(
                "links",
                Severity.WARN,
                f"Link check failed ({type(exc).__name__}): {absolute}",
                location=f'<a href="{href}">',
            )

    if checked == 0:
        yield Issue(
            "links", Severity.INFO,
            "No external links to probe.",
            suggestion="(Local file mode skips outbound probes.)",
        )


# ---------- ACCESSIBILITY -------------------------------------------------

def check_a11y(ctx: dict[str, Any]) -> Iterator[Issue]:
    soup = ctx["soup"]

    html = soup.find("html")
    if html is None:
        yield Issue("a11y", Severity.ERROR, "No <html> root element.")
    elif not html.get("lang"):
        yield Issue(
            "a11y", Severity.ERROR,
            "Missing lang attribute on <html>.",
            location="<html>",
            suggestion='Add lang="en" (or appropriate locale) for screen readers.',
        )

    images = soup.find_all("img")
    missing_alt = [img for img in images if not img.get("alt")]
    if missing_alt:
        yield Issue(
            "a11y", Severity.ERROR,
            f"{len(missing_alt)} image(s) missing alt text.",
            suggestion='Add alt="" (decorative) or descriptive alt.',
        )

    # Heading hierarchy: should not skip levels (h1 -> h3 without h2)
    headings = []
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        headings.append(int(tag.name[1]))
    for i in range(1, len(headings)):
        if headings[i] > headings[i - 1] + 1:
            yield Issue(
                "a11y", Severity.WARN,
                f"Heading skip: jumped from h{headings[i-1]} to h{headings[i]}.",
                suggestion="Don't skip heading levels for screen reader navigation.",
            )

    # Form inputs without labels
    inputs = soup.find_all(["input", "textarea", "select"])
    for inp in inputs:
        inp_type = (inp.get("type") or "text").lower()
        if inp_type in ("hidden", "submit", "button", "reset"):
            continue
        input_id = inp.get("id")
        has_label = False
        if input_id:
            has_label = soup.find("label", attrs={"for": input_id}) is not None
        if not has_label and not inp.find_parent("label"):
            yield Issue(
                "a11y", Severity.WARN,
                "Form input without associated <label>.",
                location=inp.get("name") or "<unnamed input>",
                suggestion='Wrap with <label> or use for/id association.',
            )

    # Viewport meta for mobile
    viewport = soup.find("meta", attrs={"name": "viewport"})
    if not viewport:
        yield Issue(
            "a11y", Severity.WARN,
            "Missing viewport meta tag.",
            suggestion='<meta name="viewport" content="width=device-width, initial-scale=1">',
        )


# ---------- CONFIG --------------------------------------------------------

def check_config(ctx: dict[str, Any]) -> Iterator[Issue]:
    """Verify presence of robots.txt and sitemap.xml at site root."""
    target = ctx["target"]
    if ctx["kind"] != "url":
        yield Issue(
            "config", Severity.INFO,
            "Skipping robots.txt / sitemap.xml probes in local-file mode.",
        )
        return

    parsed = urlparse(target)
    base = f"{parsed.scheme}://{parsed.netloc}"
    session = ctx["session"]
    timeout = ctx["timeout"]

    robots_url = f"{base}/robots.txt"
    try:
        r = session.get(
            robots_url,
            timeout=timeout,
            headers={"User-Agent": "LaunchLint/0.1"},
        )
        if r.status_code == 200:
            text = r.text.lower()
            if "sitemap" not in text:
                yield Issue(
                    "config", Severity.INFO,
                    "robots.txt found but does not reference a sitemap.",
                    suggestion="Add 'Sitemap: <url>' line.",
                )
        elif r.status_code == 404:
            yield Issue(
                "config", Severity.WARN,
                "No robots.txt at site root.",
                suggestion=f"Create {robots_url} (even an empty one helps SEO).",
            )
        else:
            yield Issue(
                "config", Severity.WARN,
                f"robots.txt returned HTTP {r.status_code}.",
            )
    except Exception as exc:
        yield Issue(
            "config", Severity.INFO,
            f"Could not fetch robots.txt ({type(exc).__name__}).",
        )

    sitemap_url = f"{base}/sitemap.xml"
    try:
        r = session.get(
            sitemap_url,
            timeout=timeout,
            headers={"User-Agent": "LaunchLint/0.1"},
        )
        if r.status_code == 404:
            yield Issue(
                "config", Severity.WARN,
                "No sitemap.xml at site root.",
                suggestion=f"Create {sitemap_url} listing your canonical URLs.",
            )
    except Exception:
        pass


# ---------- Dispatcher ----------------------------------------------------

_CHECKS: dict[str, Callable[[dict[str, Any]], Iterator[Issue]]] = {
    "seo": check_seo,
    "links": check_links,
    "a11y": check_a11y,
    "config": check_config,
}


def run_check(name: str, ctx: dict[str, Any]) -> Iterator[Issue]:
    return _CHECKS[name](ctx)