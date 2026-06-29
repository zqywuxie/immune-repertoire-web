"""Analysis worker entry point.

Supports two modes:
    threadpool  (default)  Run inside the Flask process via ThreadPoolJobQueue
    redis       Start an RQ worker:  rq worker analysis-jobs

Usage:
    python -m analysis_workers.main                  # threadpool mode
    rq worker analysis-jobs --url redis://127.0.0.1:6379/0  # redis mode
"""

from __future__ import annotations

import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parents[1]
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from .tasks.charts import run_charts_job
from .tasks.generic import run_generic_job
from .tasks.treemap import run_treemap_job
from .tasks.chord import run_chord_job
from .tasks.ppt import (
    run_ppt_scan_images_job,
    run_ppt_load_image_job,
    run_ppt_render_slides_job,
    run_ppt_comparison_scan_job,
    run_ppt_comparison_generate_job,
)

# Module -> worker function mapping (used by RedisJobQueue / RQ)
MODULE_WORKERS = {
    "charts.combined": run_charts_job,
    "treemap.generate": run_treemap_job,
    "chord.generate": run_chord_job,
    "ppt.scan-images": run_ppt_scan_images_job,
    "ppt.load-image": run_ppt_load_image_job,
    "ppt.render-slides": run_ppt_render_slides_job,
    "ppt-comparison.scan-heatmaps": run_ppt_comparison_scan_job,
    "ppt-comparison.generate": run_ppt_comparison_generate_job,
}

# Fallback for all other modules
_DEFAULT_WORKER = run_generic_job


def get_worker(module: str):
    """Return the worker function for a given job module."""
    return MODULE_WORKERS.get(module, _DEFAULT_WORKER)


__all__ = [
    "run_charts_job",
    "run_generic_job",
    "run_treemap_job",
    "run_chord_job",
    "run_ppt_scan_images_job",
    "run_ppt_load_image_job",
    "run_ppt_render_slides_job",
    "run_ppt_comparison_scan_job",
    "run_ppt_comparison_generate_job",
    "MODULE_WORKERS",
    "get_worker",
]
