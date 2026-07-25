# Changelog

## 0.1.0 (2026-07-26) — First ship

- SEO checks: title, meta description, h1, canonical, OG tags, JSON-LD
- Link checks: HTTP 4xx/5xx on outbound + internal links (HEAD with GET fallback)
- A11y checks: html lang, image alt, heading hierarchy, form labels, viewport
- Config checks: robots.txt + sitemap.xml presence + sitemap reference
- `--doctor` self-diagnose mode
- `--json` output for CI integration
- `--fail-on {error,warn,info,never}` for CI gating
- `--checks` to run only specific check groups
- `--max-links` to limit outbound probing
- Stdlib-first philosophy: only deps are `requests` and `beautifulsoup4`
- MIT licensed