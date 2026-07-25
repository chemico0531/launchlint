<p align="center">
  <h1 align="center">LaunchLint</h1>
  <p align="center">Local-first pre-launch audit CLI for static sites.</p>
  <p align="center">
    <a href="#install">Install</a> · <a href="#usage">Usage</a> · <a href="#checks">Checks</a> · <a href="#roadmap">Roadmap</a>
  </p>
</p>

```
$ launchlint https://example.com

LaunchLint v0.1.0
Target: https://example.com
Checks: seo, links, a11y, config
Duration: 1342ms

============================================================
[X] ERROR  seo
    Missing meta description.
[!] WARN   links  @ <a href="/old-path">
    Broken link (404): https://example.com/old-path
    -> Fix or remove the link before launch.
[!] WARN   a11y
    2 image(s) missing alt text.
    -> Add alt="" (decorative) or descriptive alt.
============================================================
  1 errors  2 warnings  0 info

  No blockers, but review warnings before launch.
```

## Why LaunchLint?

Lighthouse is great but **online, slow, and noisy**. Screaming Frog costs
$259/year. Most "audit tools" are SaaS dashboards you can't run in CI.

LaunchLint is:

- **Local-first** — runs on your laptop or CI runner, no account, no telemetry
- **Pre-merge focused** — designed to gate PRs, not write essays
- **Actionable** — every issue tells you what to fix
- **Free forever** for core checks (Pro: AI fix suggestions + CI templates)

## Install

Requires Python 3.10+. No npm, no Docker, no API keys.

```bash
# uv (recommended — fastest)
uv tool install git+https://github.com/chemico0531/launchlint

# pipx
pipx install git+https://github.com/chemico0531/launchlint

# pip
pip install --user git+https://github.com/chemico0531/launchlint
```

Then verify:

```bash
launchlint --doctor
```

## Usage

```bash
# Audit a URL
launchlint https://yoursite.com

# Audit a local build
launchlint ./dist
launchlint ./dist/index.html

# JSON output for CI
launchlint https://yoursite.com --json > report.json

# Only run specific checks
launchlint https://yoursite.com --checks seo,a11y

# Exit non-zero on warnings (CI mode)
launchlint https://yoursite.com --fail-on warn

# Skip outbound link probing
launchlint ./dist --max-links 0
```

## Checks

| Check | What it finds |
|---|---|
| **seo** | Missing/short/long `<title>`, meta description, `<h1>`, canonical, OG tags, JSON-LD |
| **links** | HTTP 4xx/5xx on internal + outbound links (HEAD + GET fallback) |
| **a11y** | `<html lang>`, image `alt`, heading hierarchy, form `<label>`, viewport meta |
| **config** | `robots.txt`, `sitemap.xml`, sitemap reference in robots |

## CI integration

```yaml
# GitHub Actions example
- name: LaunchLint audit
  run: |
    pip install --user git+https://github.com/chemico0531/launchlint
    launchlint https://staging.yoursite.com --fail-on error --json > ll.json || true
- name: Annotate PR
  run: cat ll.json
```

## Exit codes

| Code | Meaning |
|---|---|
| 0 | No issues at or above `--fail-on` threshold |
| 1 | Issues found at or above threshold |
| 2 | Audit crashed (network error, parse failure, etc.) |

## Roadmap

- v0.2 — AI fix suggestions via optional OpenAI/Anthropic key (`--ai` flag)
- v0.3 — PDF report (white-label, for agencies billing clients)
- v0.4 — GitHub Action with PR annotations
- v0.5 — Multi-page crawl mode

## License

MIT — see [LICENSE](LICENSE).