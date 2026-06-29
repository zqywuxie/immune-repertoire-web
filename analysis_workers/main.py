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
from .tasks.statistical import (
    run_statistical_analyze_job,
    run_statistical_boxplot_job,
    run_statistical_analyze_multiple_job,
    run_statistical_summary_boxplot_job,
    run_statistical_analyze_batch_job,
    run_statistical_analyze_direct_job,
)
from .tasks.heatmap import (
    run_heatmap_generate_job,
    run_heatmap_pipeline_report_job,
    run_heatmap_report_job,
    run_heatmap_export_cdr3_job,
)
from .tasks.analysis import (
    run_analysis_execute_job,
    run_analysis_batch_job,
    run_analysis_execute_unified_job,
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
    "statistical.analyze": run_statistical_analyze_job,
    "statistical.boxplot": run_statistical_boxplot_job,
    "statistical.analyze-multiple": run_statistical_analyze_multiple_job,
    "statistical.summary-boxplot": run_statistical_summary_boxplot_job,
    "statistical.analyze-batch": run_statistical_analyze_batch_job,
    "statistical.analyze-direct": run_statistical_analyze_direct_job,
    "auto-heatmap.generate-heatmap": run_heatmap_generate_job,
    "auto-heatmap.generate-pipeline-report": run_heatmap_pipeline_report_job,
    "auto-heatmap.generate-heatmap-report": run_heatmap_report_job,
    "auto-heatmap.export-shared-cdr3": run_heatmap_export_cdr3_job,
    "analysis.execute": run_analysis_execute_job,
    "analysis.batch": run_analysis_batch_job,
    "analysis.execute-unified": run_analysis_execute_unified_job,
}

# Fallback for all other modules
_DEFAULT_WORKER = run_generic_job


def get_worker(module: str):
    """Return the worker function for a given job module."""
    return MODULE_WORKERS.get(module, _DEFAULT_WORKER)


def execute(module: str, job_id: str):
    """Execute a job by module and job_id — called by queue adapters.

    Returns the worker's return value (dict with success/error).
    """
    worker = get_worker(module)
    return worker(job_id)


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
    "run_statistical_analyze_job",
    "run_statistical_boxplot_job",
    "run_statistical_analyze_multiple_job",
    "run_statistical_summary_boxplot_job",
    "run_statistical_analyze_batch_job",
    "run_statistical_analyze_direct_job",
    "run_heatmap_generate_job",
    "run_heatmap_pipeline_report_job",
    "run_heatmap_report_job",
    "run_heatmap_export_cdr3_job",
    "run_analysis_execute_job",
    "run_analysis_batch_job",
    "run_analysis_execute_unified_job",
    "MODULE_WORKERS",
    "get_worker",
    "execute",
]
