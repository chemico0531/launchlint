# LaunchLint v0.3 — PDF Implementation Plan

## Package Layout
```
src/launchlint/reports/
├── __init__.py       # public exports
├── brand.py          # BrandConfig dataclass + JSON loading
├── templates.py      # score calc + shared helpers
├── pdf_report.py     # ReportLab PDF generation
└── html_report.py    # simple HTML report fallback
```

## Technology Choices
- **ReportLab**: pure Python, no native deps, works on Windows, proven.
- **PIL/Pillow**: optional, used only to read logo dimensions (not required).
- **stdlib json/pathlib**: for brand config loading.

## CLI Additions
- `--report`: generate report after audit.
- `--report-format {pdf,html}`: default `pdf`.
- `--pdf-output PATH`: custom output path.
- `--brand-config PATH`: JSON brand config.
- White-label overrides: `--logo`, `--agency-name`, `--agency-contact`, `--accent-color`, `--client-name`, `--report-title`.

## Default Filename
`launchlint-[domain]-YYYYMMDD-HHMMSS.pdf`
- Domain extracted from URL host; local paths use `local`.

## Score Algorithm
`score = max(0, 100 - error*25 - warn*10 - info*2)`

## Testing
- `tests/test_reports/test_brand.py`: BrandConfig loading, CLI override merging, color validation.
- `tests/test_reports/test_pdf.py`: PDF generation smoke test, file existence, score correctness.
- Run `pytest --cov=src/launchlint` and keep coverage ≥80%.

## Rollout
- Update `pyproject.toml` version to `0.3.0`, add `reportlab>=4.0`.
- Update README and CHANGELOG.
- Tag `v0.3.0` after merge.
