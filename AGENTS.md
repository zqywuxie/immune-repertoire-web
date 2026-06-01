# Repository Guidelines

## Project Structure & Module Organization

The application follows a Flask blueprint pattern. `flask_app/app.py` is the single entry point (`python flask_app/app.py`) — it creates the app via `create_app()`, registers blueprints, initializes extensions, and starts the dev server on port 5000.

**Routes** (`flask_app/routes/`) — page routes in `pages.py`, API routes split by feature domain (e.g., `api_treemap.py`, `api_combined_analysis.py`, `api_script_hub.py`). Each API file registers its own blueprint with a `url_prefix`.

**Services** (`flask_app/services/`) — all business logic lives here. Key services: `analysis_service.py` (core analysis), `treemap_renderer.py` (treemap visualization), `similarity_heatmap_report_service.py`, `chord_report_service.py`, `db_alignment_service.py`. The `analysis/` subdirectory contains a modular analysis system with a `registry.py` and pluggable modules under `analysis/modules/`.

**Templates** (`flask_app/templates/`) — Jinja2 templates with `base.html` as the layout foundation. Page-specific templates under `analysis/`, reusable components under `components/` (navbar, sidebar, field selectors, etc.).

**Static assets** (`flask_app/static/`) — JavaScript modules map 1:1 to analysis features (e.g., `treemap_analysis.js`, `chord_diagram_analysis.js`, `script_hub.js`). `style.css` is the main stylesheet (~38KB).

**Data flow**: Templates render pages → JS modules call API endpoints → Routes delegate to services → Services read/write files under `flask_app/data/` (uploads, results, PDF extractions).

## Build, Test, and Development Commands

```bash
# Install dependencies
cd flask_app && pip install -r requirements.txt

# Start the dev server
python flask_app/app.py

# Run all tests
pytest flask_app/tests/

# Run a single test file
pytest flask_app/tests/test_pipeline_comparison_api.py

# Run with coverage
pytest flask_app/tests/ --cov=flask_app --cov-report=html
```

Configuration is selected via the `FLASK_CONFIG` environment variable (`development`, `production`, `testing`). Default is `development` with SQLite at `flask_app/data/immune_repertoire.db`.

## Coding Style & Naming Conventions

No linter or formatter configs are present in the repository. Follow existing patterns:
- Python: PascalCase for classes, snake_case for functions/variables
- JavaScript: camelCase for variables/functions, feature-scoped kebab-case CSS classes (e.g., `sh-` prefix for Script Hub)
- CSS: feature-scoped class names, custom CSS variables defined in page-level `<style>` blocks using `--feature-` prefix
- Routes: API endpoints use `/api/<feature>/<action>` pattern; page routes use `/analysis/<feature>`

## Testing Guidelines

Uses `pytest` with `pytest-cov` and `hypothesis`. Test files live in `flask_app/tests/`. The `TestingConfig` class uses an in-memory SQLite database. Tests are currently minimal — only `test_pipeline_comparison_api.py` and `test_workspace_navigation.py` remain.

## Commit & Pull Request Guidelines

Commit history shows a mix of English imperative mood ("Add", "Fix", "Update", "Remove") and Chinese descriptions. Some commits use the `feat:` prefix convention. Follow the imperative pattern: `Add/Fix/Update/Remove <description>`. No PR template exists.
