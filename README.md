

# Strategic AI Leader – Content Authority Hub

![CI](https://github.com/RNaimy/strategicaileader_content_authority_hub/actions/workflows/ci.yml/badge.svg)
![coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)

A lightweight toolkit for crawling, analyzing, and reporting on content authority signals. The project includes helpers for NLP, scraping, simple data exports, and a GitHub Actions CI that runs tests with coverage and uploads an HTML report.

---

## Quick start

### 1) Create & activate a virtual environment
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\\Scripts\\activate
```

### 2) Install dependencies
```bash
pip install -r requirements.txt
```

### 3) Run the tests locally (with coverage)
```bash
pytest -q --cov=src --cov-report=term-missing --cov-report=html
open htmlcov/index.html  # macOS; on Windows use: start htmlcov/index.html
```

> If you see an "Import could not be resolved" warning in VS Code for paths like `utils.*`, add this to `.vscode/settings.json`:
```json
{
  "python.analysis.extraPaths": ["./src"],
  "python.testing.pytestEnabled": true,
  "python.testing.pytestArgs": ["tests"]
}
```

---

## Continuous Integration (CI)
- The workflow lives at **`.github/workflows/ci.yml`**.
- Triggers on pushes/PRs to `main` (and `dev` if enabled).
- Steps:
  1. Setup Python 3.12
  2. Install project deps from `requirements.txt`
  3. Run pytest with coverage
  4. Upload HTML coverage as an artifact

Badge at the top of this README reflects the current CI status.

---

## Repository layout
```
src/
  analysis/            # analysis utilities
  crawlers/            # simple scraper helpers
  gsc/                 # Google Search Console helpers (client, fetch, parser)
  reports/             # CSV/Notion/PDF exporters (stubs)
  utils/               # general utilities (db, logger, nlp, seo_rules)
tests/                 # unit tests (pytest)
.github/workflows/     # GitHub Actions CI
```

---

## Environment
- Copy `.env.example` to `.env` if/when secrets are needed.
- Python 3.12+ is recommended.

---

## Troubleshooting
- **VS Code Pylance cannot resolve `utils.*`:** ensure `"python.analysis.extraPaths": ["./src"]` is set (see above) or export `PYTHONPATH=src` before running Python/pytest.
- **macOS cannot open HTML coverage:** run `python -m webbrowser htmlcov/index.html`.

---

## License
MIT – see `LICENSE` (add one if missing).