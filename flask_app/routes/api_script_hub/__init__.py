"""Script Hub API — modular Blueprint registry.

All sub-blueprints register under the ``/api/script-hub`` prefix.
Backward-compatible re-exports for tests and direct module consumers.
"""

from flask import Blueprint


def _build_script_hub_bp():
    """Create a fresh parent Blueprint with all sub-blueprints registered as children.

    Returns a new Blueprint each call, safe for repeated app creation (e.g. tests).
    """
    from . import cache, modules_config, boxplot, profile_analysis, enrichment, tasks_results

    bp = Blueprint("script_hub", __name__, url_prefix="/api/script-hub")
    bp.register_blueprint(cache.bp)
    bp.register_blueprint(modules_config.bp)
    bp.register_blueprint(boxplot.bp)
    bp.register_blueprint(profile_analysis.bp)
    bp.register_blueprint(enrichment.bp)
    bp.register_blueprint(tasks_results.bp)
    return bp


def register_script_hub_routes(app):
    """Register all script-hub sub-blueprints with the Flask app."""
    app.register_blueprint(_build_script_hub_bp())


def __getattr__(name):
    """Lazy attribute access for backward-compatible ``script_hub_bp``.

    Tests and legacy code access ``script_hub_bp`` as a module attribute.
    Returns a freshly-built Blueprint so repeated app creation works.
    """
    if name == "script_hub_bp":
        return _build_script_hub_bp()
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


# ── Re-exports from _common (shared utilities) ──

from ._common import (
    # class
    ScriptTaskCancelled,
    # constants
    _ALLOWED_MODULES,
    _COLUMN_HINTS,
    _CSV_ENCODINGS,
    _RESULT_DIR,
    _RESULT_FILES,
    _SUPPORTED_CHAINS,
    _SUPPORTED_CHAINS_WIDE,
    # state
    _script_executor,
    _script_task_lock,
    _script_tasks,
    logger,
    # task state helpers
    _set_task_state,
    _get_task_state,
    _sync_job_state,
    _script_task_cancel_requested,
    _mark_script_task_cancelled,
    _record_stage,
    _history_entry,
    # utilities
    _sanitize_nan,
    _as_bool,
    _robust_read_csv,
    _normalize_chain,
    _infer_chain_from_filename,
    _find_matching_column,
    _strip_table_suffix,
    _is_table_file,
    _read_header_columns,
    _looks_like_pep_table,
    _chain_from_parent_dirs,
    _resolve_profile_path,
    _collect_asset_hints,
    _is_profile_like_file,
    _infer_wide_chain_from_filename,
    _sample_name_from_pep_file,
    _iter_candidate_pep_files,
    _read_table_columns,
    _is_readable_table_asset,
    _project_assets_root,
    _resolve_registered_asset_path,
    _is_project_profile_asset,
    _is_project_transcriptome_asset,
    _collect_project_script_hub_assets,
    _collect_project_cached_usage_assets,
    _resolve_project_cached_usage_path,
    _pep_tra_candidates_from_output_base,
    _pep_output_base_candidates_from_path,
    _resolve_pep_analysis_tra_source,
    _request_registered_assets,
    _profile_path_from_request,
    _transcriptome_path_from_request,
    _pep_paths_from_request,
    _primary_pep_path_from_request,
    _analysis_input_descriptor,
    _analysis_external_input_descriptor,
    _build_script_cache_context,
    _force_rerun_requested,
    _cache_context_from_script_request,
    _result_relative_path_from_url,
    _stored_script_result_available,
    _mongo_result_to_script_result,
    _try_find_script_task_result,
    _find_reusable_script_result,
    _try_reuse_script_result,
    _resolve_results_root,
    _projects_root,
    _project_asset_service,
    # task completion
    _persist_script_result,
    _complete_script_task,
    # viewer utilities
    _build_and_save_viewer,
    _build_topclone_viewer,
    _result_url_exists,
    _result_file_url,
    _result_url_to_path,
    _script_hub_zip_category,
    _iter_script_hub_result_files,
    _ensure_result_zip,
    _normalize_script_result,
    _pep_chain_from_result_rel,
    _pep_viewer_items,
    _generate_pep_csv_preview_images,
    _write_pep_analysis_viewer,
    _write_unified_viewer,
    # service
    get_script_hub_job_service,
)

# ── Re-exports from domain modules ──

from .modules_config import (
    _inspect_data_selection_payload,
    _discover_db_alignment_inputs,
    _build_profile_category_preview,
    _run_db_alignment_task,
)

from .boxplot import (
    _discover_boxplot_inputs,
    _run_boxplot_task,
)

from .profile_analysis import (
    _run_topclone_task,
    _run_pep_analysis_task,
    _run_pgen_analysis_task,
    _cache_pep_usage_assets,
    _suggest_profile_ranges,
    _suggest_umap_ranges,
)

from .enrichment import (
    _run_umap_task,
    _run_volcano_task,
    _run_go_kegg_enrichment_task,
    _run_umapin_task,
    _run_ml_analysis_task,
    _run_mait_nkt_task,
    _suggest_ml_label,
    _suggest_ml_sample,
    _list_payload,
    _ml_profile_feature_candidates,
    _ml_usage_feature_range,
    _parse_group_comparisons,
    _resolve_usage_data_dir,
    _usage_union_columns,
)

from .tasks_results import (
    _looks_like_category_row,
)

# ── Service re-exports for test monkeypatching ──

from flask_app.services.pep_analysis_service import PepAnalysisService  # noqa: F401
from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService  # noqa: F401
