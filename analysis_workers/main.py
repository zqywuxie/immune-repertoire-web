"""Analysis worker entry point.

Supports two modes:

    threadpool  (default)  Run inside the Flask process via ThreadPoolJobQueue
    redis       Start an RQ worker:  rq worker analysis-jobs

Usage:
    python -m analysis_workers.main                  # threadpool mode (import only)
    rq worker analysis-jobs --url redis://127.0.0.1:6379/0  # redis mode
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is importable
_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .tasks.charts import run_charts_job
from .tasks.generic import run_generic_job

__all__ = ["run_charts_job", "run_generic_job"]
