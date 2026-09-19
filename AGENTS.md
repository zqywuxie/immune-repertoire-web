# Repository Guidelines

## Commands

Always prefix shell commands with `rtk`. Use `rtk proxy <command>` for unsupported commands or when complete output is needed. Prefix every segment in command chains. Prefer `rg` for searches.

## Current architecture

- Read `docs/architecture/current-system.md` for current boundaries and `docs/dev-startup-guide.md` for startup.
- `frontend/`: React 19, TypeScript, Vite; routes in `src/app/App.tsx`. Default development proxy targets Flask on port 5000.
- `flask_app/`: Flask app factory, API routes, SQLAlchemy models and shared analysis services. Script Hub routes are the package `routes/api_script_hub/`, not a single file.
- `backend-api/`: FastAPI API/repositories and job/asset infrastructure. `analysis_workers/`: worker entry points.
- Generic job modules use `docs/api/module-manifest.yaml`; Legacy Script Hub has its own catalog and task/result API. Preserve both contracts.
- Reuse shared React components and `features/scripthub/` for analysis configuration/execution. Prefer external components/scripts to large inline page logic.

## Data and cleanup

Large `_reference`, `test_data`, and `flask_app/data/results` directories are junctions to sibling `immune-repertoire-web-data`; do not follow them during cleanup. Old workspace paths may also be compatibility links.
Runtime databases, project assets, reference databases and PDF extractions are not caches. Delete analysis results only through their task/asset lifecycle. Preserve active startup files in `.dev-runtime`.
`docs/api/module-manifest.yaml` is required at runtime. Historical designs are under `docs/archive`; unfinished plans remain in `docs/superpowers`.

## Style

Python: PascalCase classes, snake_case functions, `_bp` blueprint suffix, service-layer business logic. JavaScript/TypeScript: camelCase, feature-scoped components and styles; use existing CSS variables. Validate submitted fields against actual inputs and task contracts. Chinese is the primary product language; preserve scientific labels such as CDR3, V/J and p/q values.
Keep existing user changes. Do not add dependencies or broad architecture changes for a local fix. Do not change statistical definitions during interaction-only work.

## Verification

- `rtk proxy npm --prefix frontend test` and `rtk proxy npm --prefix frontend run build`.
- `rtk proxy python -m pytest flask_app/tests/` or targeted tests for modified services/APIs.
- FastAPI tests live in `backend-api/tests/`; worker tests in `analysis_workers/tests/`.
- Use small synthetic input for analysis regression. Test real asset references, task status transitions and output retrieval; never run tests against production datasets.

## Commits

Use imperative titles (`Add`, `Fix`, `Update`, `Remove`, or equivalent Chinese). Keep changes scoped; do not stage or commit unrelated files. No PR template is required.

## Docker Environment Policy (2026-09-12)

User requirement: all subsequent application and analysis environments must be created inside Docker containers; Docker is the deployment target.

- Install new Python, R, Node and system dependencies through Dockerfiles or container build steps. Do not install project runtimes or analysis dependencies on the host.
- Run subsequent application tests, frontend builds and analysis validation inside the corresponding containers. Host tools may edit source and manage Docker.
- Keep dependency manifests and container build definitions synchronized, including optional Pgen and GO/KEGG dependencies when enabling those modules.
- Persist databases, uploads, project assets, results and reference databases using named volumes or explicit bind mounts. Do not bake existing large datasets into images or the build context.
- Use container service names and Linux container paths in deployment configuration; do not carry Windows absolute paths into images.
- Use compose.docker.yml and docs/docker-deployment.md for the application deployment. The original docker-compose.yml remains the legacy infrastructure stack. Validate actual image builds and runtime checks before claiming a complete container deployment.
- If Docker is unavailable, report the container execution blocker instead of falling back to host dependency installation or host-based validation.

This policy supersedes older host-based installation, build and test examples in this repository for future work.
