# LaunchLint v0.3 — White-Label PDF Report Design

## Goal
Add an optional, professionally printable PDF report that agencies can white-label and hand to clients. The report turns LaunchLint from a CI tool into a client-deliverable product.

## User Stories
- As an agency owner, I want to run `launchlint <client-site> --report` and get a PDF I can email to a client.
- As a freelancer, I want to upload my logo and accent color so the report looks like mine.
- As a CI user, I want `--report-format html` as a quick preview before PDF generation.

## Scope
- PDF generation via ReportLab (pure Python, Windows-friendly).
- HTML fallback generation using stdlib templates.
- White-label overrides: logo, agency name/contact, accent color, client name, report title.
- Config file (`--brand-config`) plus CLI flags for one-off overrides.
- Cover page, executive summary, findings grouped by severity, metadata appendix.

## Out of Scope
- Multi-page crawling (v0.5).
- Historical trend charts.
- Editable Word/docx export.

## Acceptance Criteria
- `python -m launchlint https://example.com --report` writes a valid PDF.
- `--brand-config mybrand.json` customizes branding without manual CLI flags.
- Score = max(0, 100 - error*25 - warn*10 - info*2).
- A4 page size, 20mm margins, printable.
- All existing tests pass; new tests cover brand config and PDF output.
