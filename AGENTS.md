# Repository Guidelines

## Project Overview

Immune repertoire analysis web application built on Flask. Provides web-based analysis workflows (heatmaps, treemaps, chord diagrams, pipeline comparison, statistical tests), result export, PDF/PPT processing, and a modular Script Hub for multi-module analysis. Originally migrated from a Django project (`djangoProject` / `anal_pipeline`).

## Project Structure & Module Organization

### Entry Point & App Factory

`flask_app/app.py` is the single entry point (`python flask_app/app.py`). It defines `create_app(config_name)` which:
1. Reads `FLASK_CONFIG` env var (default: `development`)
2. Creates the Flask app with a custom `SafeJSONEncoder` (handles `numpy` NaN/Infinity)
3. Loads config from `flask_app/config.py`
4. Initializes SQLAlchemy, Flask-Login, and registers error handlers
5. Registers all 12 blueprints via `register_blueprints()`
6. Calls `db.create_all()` and initializes services (`analysis_service`, `config_service`, `parameter_template_service`, `annotation_service`, `analysis.registry`)
7. Runs on `http://0.0.0.0:5000` by default

### Routes (`flask_app/routes/`) — 12 Blueprints

| Blueprint | File | URL Prefix | Purpose |
|---|---|---|---|
| `pages` | `pages.py` | (none) | Page routes: `/`, `/analysis`, `/projects`, `/settings`, `/management`, plus redirects from deprecated pages |
| `api` | `api.py` | (none) | Core API: file upload/CRUD, mappings, analysis CRUD, config, annotations, groups, parameters. Largest route file (~5541 lines). |
| `analysis` | `api_analysis.py` | `/api/analysis` | Modular analysis engine: modules, schemes, execution, validation, auto-mapping |
| `statistical` | `api_statistical.py` | `/api/statistical` | Statistical comparison: Kruskal-Wallis, boxplots, batch analysis with FDR correction |
| `project_api` | `api_projects.py` | `/api` | Project/sample CRUD, assets, group specs, Django-compatible legacy endpoints |
| `auto_heatmap` | `api_auto_heatmap.py` | `/api/auto-heatmap` | Auto heatmap: folder scan, field mapping, heatmap/web-report generation, pipeline comparison reports, CDR3 export |
| `chord` | `api_chord.py` | `/api/chord` | Chord diagram: async generate → poll task → serve results |
| `treemap` | `api_treemap.py` | `/api/treemap` | Treemap: async generate → poll task → serve results |
| `ppt` | `api_ppt.py` | `/api/ppt` | PPT processing: analyze, replace heatmaps, render slides, session management |
| `ppt_comparison` | `api_ppt_comparison.py` | `/api/ppt-comparison` | PPT comparison: scan heatmaps, generate comparison PPT |
| `script_hub` | `api_script_hub.py` | `/api/script-hub` | Script Hub (7 modules): db-alignment, boxplot, topclone, pep-analysis, umap, volcano, umapin — each with `/inspect` and `/run` endpoints |
| `combined_analysis` | `api_combined_analysis.py` | `/api/combined-analysis` | Combined analysis: one-shot heatmap+treemap+chord generation |

The PPT blueprints are wrapped in try/except for optional `python-pptx` dependency.

### Services (`flask_app/services/`) — Business Logic Layer

**Top-level services** (~40 files):
- `analysis_service.py` — Core analysis orchestrator; creates/executes/tracks analysis tasks via `IntegratedAnalysisEngine`
- `integrated_analysis.py` — Unified engine for similarity heatmaps, sequencing depth, diversity metrics, chain specificity
- `similarity_analyzer.py` — Six similarity metrics: r2_inner, r2_outer, cdr3_sharing, expression_sharing, morisita_horn, sorensen_dice
- `auto_heatmap_service.py` — Auto heatmap by folder scan with sample grouping
- `similarity_heatmap_report_service.py` — Static HTML reports from heatmap results
- `treemap_renderer.py` — D3.js treemap visualization (~2400 lines)
- `treemap_report_service.py` — Per-sample treemap reports (HTML, PNG, TopClone CSV) via headless browser
- `chord_report_service.py` — V/J gene usage chord diagrams (CSV, PDF, interactive HTML)
- `pipeline_comparison_integration_service.py` — Multi-pipeline comparison (heatmaps, Venn diagrams, CDR3 export)
- `db_alignment_service.py` — CDR3 exact matching against VDJdb and McPAS-TCR reference databases
- `statistical_analysis_service.py` — Group-level Kruskal-Wallis + Dunn's post-hoc with FDR correction
- `boxplot_service.py` — Grouped boxplots with Mann-Whitney U p-values
- `volcano_service.py` — Volcano plots for differential V/J usage (log2 fold change + Mann-Whitney)
- `umap_service.py` — Significance-driven UMAP dimensionality reduction
- `umapin_service.py` — Usage-based UMAP with optional FDR correction
- `topclone_service.py` — TopClone extraction ("trace" and "per_sample" modes)
- `pep_analysis_service.py` — Pep_260213 pipeline (CDR3 sharing, V/J matrices, category heatmaps)
- `file_parser.py` — CSV/Excel/gzip parsing with encoding detection and chain detection
- `field_mapping.py` — Logical-to-physical field mapping with template save/load
- `config_service.py` — User configuration persistence (chart defaults, UI theme/locale)
- `project_service.py`, `project_asset_service.py`, `project_analysis_bridge.py` — Project management
- `group_spec_service.py`, `grouping_service.py` — Sample grouping and group statistics
- `sample_registry_service.py` — Sample metadata import/filter/export
- `pdf_extractor.py`, `pdf_table_extractor.py` — PDF image/table extraction (PyMuPDF/pdfplumber/tabula-py)
- `ppt_service.py`, `ppt_heatmap_service.py`, `ppt_comparison_service.py` — PPT generation and image replacement
- `export_service.py`, `cdr3_export_service.py` — Data export (PNG, CSV, ZIP, formatted Excel)
- `mongo_service.py` — MongoDB helpers for raw data assets and analysis cache
- `integration_catalog_service.py` — Static catalog of Django→Flask migration status
- `analysis_pipeline.py` — Pipeline wrapper: preprocess → execute analyzer → save results
- `unified_analysis_service.py` — High-level orchestrator combining scheme management, field mapping, pipeline execution
- `scheme_manager.py` — Analysis scheme CRUD, suggestion, and confidence scoring
- `annotation_service.py` — Visualization annotations (text, arrow, highlight, label, box, circle)

**Sub-package: `services/analysis/`** — Modular analysis system:
- `base_module.py` — `AnalysisModule` (abstract base), `AnalysisResult`, `PlotConfig` (matplotlib + CJK typography)
- `registry.py` — `AnalysisRegistry`: module registration, lookup by category/columns, `@register_module` decorator
- `modules/` — 17 pluggable modules: `ig_metrics`, `sequencing_depth`, `sequencing_reads`, `chain_analysis`, `bcell_isotype`, `shm_analysis`, `field_analyzer`, `statistical_comparison`, `pdf_extractor`, and variants for IG/Ig isotypes/SHM/BCell PDF extraction

**Sub-package: `services/analyzers/`** — Unified analyzer interface:
- `base_analyzer.py` — `BaseAnalyzer` (abstract) with `analyze()`, `get_required_fields()`, `validate_data()`
- 7 implementations: `BCellIsotypeAnalyzer`, `SHMAnalyzer`, `IGMetricsAnalyzer`, `CustomFieldAnalyzer`, `SequencingReadsChartAnalyzer`, `BcellMaturationAnalyzer`, `PPTReportGenerator`

### Models (`flask_app/models/`)

`database.py` defines 11 SQLAlchemy models: `File`, `MappingTemplate`, `Analysis`, `AnalysisResult`, `CustomParameter`, `Annotation`, `SampleGroup`, `Project`, `ProjectAsset`, `SampleRecord`, `ProjectGroupSpec`.

### Templates (`flask_app/templates/`)

- **`base.html`** — Main layout shell: navbar, collapsible sidebar, Bootstrap 5.3/DataTables/ECharts CDN assets. Supports `embedded` mode (strips chrome for iframe).
- **`analysis/base_analysis.html`** — Secondary base extending `base.html` for analysis modules. Provides two-column layout (file selection + field mapping + parameters + chart config + results). Used by SHM, IG metrics, B-cell isotype pages.
- **Page templates** (15 files): `index.html`, `projects.html`, `project_detail.html`, `upload.html`, `files.html`, `samples.html`, `simple_analysis.html` (unified analysis), `analysis_overview.html`, `settings.html`, `management.html`, plus `analysis/` subdirectory templates for each feature.
- **Reusable components** (`components/`, 12 files): `navbar.html`, `sidebar.html`, `file_uploader.html`, `field_mapper.html`, `field_selector.html`, `scheme_selector.html`, `mode_selector.html`, `parameter_config.html`, `analysis_results.html`, `analysis_source_panel.html`, `data_table.html`, `directory_browser.html`.
- The sidebar supports two workspaces: **"analysis"** (analysis tools) and **"management"** (data management), toggled via navbar button.

### Static Assets (`flask_app/static/`)

**CSS** (`css/`): `style.css` (~38KB main stylesheet) plus feature-specific files.

**JavaScript** (`js/`, ~34 files) — maps roughly 1:1 to features:

| File | Purpose |
|---|---|
| `app.js` | Global app shell: `AppState`, `API` wrappers, `Utils` (toast, format), sidebar toggle, responsive resize |
| `script_hub.js` | Largest file (~3672 lines): unified multi-module analysis hub (7 sub-modules) |
| `ppt_replace.js` | Second largest (~4879 lines): PPT template analysis, image replacement, comparison mode |
| `similarity_heatmap.js` | Auto heatmap: folder scan → sample/group selection → 6-metric heatmap → web report → ZIP |
| `treemap_analysis.js` | Treemap: folder scan → chain/sample selection → field mapping → async generate |
| `chord_diagram_analysis.js` | Chord diagram: folder scan → chain/sample selection → V/J mapping → async generate |
| `combined_analysis.js` | Combined analysis: one-shot heatmap+treemap+chord batch job |
| `pipeline_comparison.js` | Pipeline comparison: scan root → configure pipelines → generate comparison report |
| `advanced_analysis.js` | Module hub: iframe-based switching between Pipeline Comparison and DB Alignment |
| `analysis_workspace.js` | Shared workspace utilities (used by multiple analysis pages) |
| `project_management.js` | Project list page logic |
| `project_detail.js` | Project detail page: tabs for assets, samples, group specs, settings |
| `sample_registry.js` | Sample browser: multi-field search, edit modal, CSV export |
| `upload.js` | File upload with drag-and-drop and progress tracking |
| `settings.js` | Settings page: load/save/reset visualization and export defaults |
| `sequencing_depth.js` | Sequencing depth: PPT report, visualization, bar chart tabs |
| `directory_browser.js` | Reusable lazy-loading file system tree widget |
| `field_mapper.js`, `field_selector.js` | Field mapping/selection components |
| `scheme_manager.js`, `analysis_executor.js` | Scheme-based analysis execution |
| `tab_manager.js` | Generic tab management with sessionStorage persistence |
| `table_copy.js`, `table_extraction.js` | Table copy/CSV download and PDF table extraction |
| `color_scheme_preview.js` | Color scheme picker component |
| `file_uploader.js` | Reusable file uploader component (class-based, for embedding in analysis modules) |
| `field-detection.js` | Smart column-to-field auto-detection |
| `modules/` (9 files) | Analysis sub-modules: `shm_analysis.js`, `ig_metrics.js`, `bcell_isotype.js`, `field_analyzer.js`, `field_mapper.js` (enhanced), `sample_selector.js`, `sample_grouping.js`, `baseline_selector.js`, `pdf_extractor.js` |

## Database & Infrastructure

### SQLAlchemy (Primary)
- Configured via `SQLALCHEMY_DATABASE_URI`. Resolution order: `DATABASE_URL` env var → `flask_app.database_config` → SQLite fallback (`data/immune_repertoire.db`)
- Supports **MySQL** (production) and **SQLite** (development/testing). Testing uses in-memory SQLite.
- `flask_app/database_config.py` holds MySQL connection parameters.

### MongoDB (Auxiliary)
- Used for raw data assets and analysis result caching via PyMongo (`mongo_service.py`).
- Connection configured in `.env` (`MONGODB_URI`).

### Docker
- `docker-compose.yml` provides MySQL 8.0 (port 3307) and MongoDB 7.0 (port 27018) with healthchecks.
- Init scripts in `docker/mysql/init/` and `docker/mongo/init/`.

### Data Directories
- `flask_app/data/uploads/` — Uploaded files (UUID-named)
- `flask_app/data/results/` — Analysis result directories (UUID-named)
- `flask_app/data/projects/` — Project-scoped assets
- `flask_app/data/reference_db/` — Reference databases: `McPAS-TCR.csv` (~7MB), `vdjdb.csv` (~89MB)
- `flask_app/data/custom_schemes/` — Custom analysis schemes
- `flask_app/data/pdf_extractions/` — PDF extraction output

## Key Architectural Patterns

### Async Task Pattern
Long-running operations (treemap, chord, combined analysis, script hub modules) use:
1. Client POSTs to `/api/<module>/generate` (or `/run`) → receives `task_id`
2. Client polls `GET /api/<module>/task/<task_id>` → receives `{status, progress, result}`
3. On completion, client fetches results from `/api/<module>/results/<job_id>/...`
3. JS implements this via `pollTaskStatus(taskId, apiBase, options)` with configurable interval

### Project Bridging
Analysis pages accept URL parameters (`?project_id=X&base_path=Y&auto_scan=1`) to pre-populate from project assets:
- `project_analysis_bridge.py` generates pre-filled analysis URLs
- JS checks for these params on init and auto-scans/auto-loads the project directory

### Analysis Registry
`services/analysis/registry.py` maintains a registry of pluggable `AnalysisModule` subclasses:
- Modules register via `@register_module` decorator or explicit `register()` call
- Lookup by category (e.g., `diversity_analysis`, `quality_control`, `bcell_analysis`) or by required data columns
- `services/analysis/modules/__init__.py` imports all modules to trigger registration

### Scheme-Based Analysis
Analysis schemes (predefined and custom) define required fields, parameters, and chart configuration:
- `scheme_manager.py` manages scheme CRUD and suggestion
- `unified_analysis_service.py` orchestrates scheme → field mapping → analysis pipeline execution
- Schemes stored as JSON in `flask_app/config/analysis_schemes.json`

### Workspace Paradigm
The UI has two workspaces toggled via navbar:
- **Analysis workspace**: data analysis, pipeline comparison, script hub, statistical tests, PDF extractor, PPT replacer
- **Management workspace**: home, projects, samples, settings
- Sidebar renders different navigation based on `current_workspace` context variable

### Error Handling
`flask_app/exceptions.py` defines a structured exception hierarchy:
- `AppException` (base) → `to_dict()` for JSON error responses with `error_code`, `message`, `details`
- Domain-specific subclasses: `File*Error`, `Mapping*Error`, `Analysis*Error`, `PPT*Error`, `ValidationError`, `StorageError`
- Registered as Flask error handlers in `app.py` via `register_error_handlers()`

## Build, Test, and Development Commands

```bash
# Install dependencies
cd flask_app && pip install -r requirements.txt

# Start infrastructure (MySQL + MongoDB)
docker-compose up -d

# Start the dev server
python flask_app/app.py
# → http://127.0.0.1:5000

# Run all tests
pytest flask_app/tests/

# Run a single test file
pytest flask_app/tests/test_pipeline_comparison_api.py

# Run with coverage
pytest flask_app/tests/ --cov=flask_app --cov-report=html
```

### Configuration
- `FLASK_CONFIG` env var selects config class: `development` (default), `production`, `testing`
- `DATABASE_URL` env var overrides the database connection string
- `SECRET_KEY`, `HOST`, `PORT` also configurable via environment
- `.env` file at project root provides defaults for local development
- `TestingConfig` uses in-memory SQLite (`sqlite:///:memory:`) with CSRF disabled

### PPT Dependencies
The `python-pptx` package is optional. If missing, the PPT blueprints raise a descriptive error. Install via `pip install python-pptx`.

## Coding Style & Naming Conventions

No linter or formatter configs are present. Follow existing patterns:

- **Python**: PascalCase for classes, snake_case for functions/variables. Blueprint variables use `_bp` suffix. Route files named `api_<feature>.py`.
- **JavaScript**: camelCase for variables/functions. Feature-scoped kebab-case CSS classes with prefixes (e.g., `sh-` for Script Hub, `ah-` for auto heatmap). CSS variables use `--feature-` prefix in page-level `<style>` blocks.
- **CSS**: Feature-scoped class naming. CSS custom properties defined in page-level `<style>` blocks. Main stylesheet at `static/css/style.css`.
- **Routes**: API endpoints use `/api/<feature>/<action>` pattern. Page routes use `/analysis/<feature>`. Some legacy Django-compatible endpoints exist under `/api/` with non-standard naming.
- **Templates**: Jinja2 with `{% extends "base.html" %}` or `{% extends "analysis/base_analysis.html" %}`. Reusable pieces use `{% include %}`. Inline JS is acceptable for simple pages; complex logic goes in external `static/js/` files.
- **Services**: Each service file typically exports one main class. Services are initialized in `create_app()` and accessed via imports. Some services use module-level functions for stateless operations.

### Common JS Patterns
- `escapeHtml(str)` — XSS prevention, used throughout
- `pollTaskStatus(taskId, apiBase, options)` — async task polling with progress callbacks
- `API.get(url, params)` / `API.post(url, data)` — wrapper around fetch with error handling
- `Utils.showToast(message, type)` — Bootstrap toast notifications
- `Utils.formatFileSize(bytes)` / `Utils.formatDate(isoString)` — display formatting
- Project bridging: check `project_id` URL param → auto-scan directory → enable "register result" button

### Inline JS vs External Files
Some older pages (`files.html`, `simple_analysis.html`, `results.html`, `statistical_comparison.html`) contain large inline JS classes rather than external files. New development should prefer external JS files in `static/js/`.

## Testing Guidelines

Uses `pytest` with `pytest-cov` and `hypothesis`. Test files live in `flask_app/tests/`.

**Existing tests** (minimal — only 2 files):
- `test_pipeline_comparison_api.py` — Tests the pipeline comparison generate/serve endpoints with Flask test client
- `test_workspace_navigation.py` — Tests workspace routing (root redirect, nav items per workspace, settings context preservation)

Tests use `TestingConfig` (in-memory SQLite, CSRF disabled). Use the Flask test client pattern from existing tests. Service-level mocking is done via `unittest.mock.patch`.

## Commit & Pull Request Guidelines

Commit history mixes English imperative mood ("Add", "Fix", "Update", "Remove") and Chinese descriptions. Some commits use `feat:` prefix. Follow the imperative pattern: `Add/Fix/Update/Remove <description>`. No PR template exists.

## External Dependencies

- **CDN**: Bootstrap 5.3.2, Bootstrap Icons, DataTables 1.13.7, jQuery 3.7.1, ECharts 5.4.3, JSZip 3.10.1 — loaded from CDN in `base.html`
- **Python**: Flask 3.0, SQLAlchemy 2.0, PyMySQL, PyMongo, pandas, numpy, matplotlib, seaborn, scipy, scikit-learn (UMAP), PyMuPDF, pdfplumber, tabula-py, python-pptx (optional), openpyxl
- **Infrastructure**: MySQL 8.0, MongoDB 7.0 (via Docker)
- **Reference databases**: VDJdb and McPAS-TCR (CSV files in `data/reference_db/`)
