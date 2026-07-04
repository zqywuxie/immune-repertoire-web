"""Modules listing, data-selection, and DB-alignment routes for the Script Hub API."""

import random
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.db_alignment_service import DBAlignmentService
from ._common import (
    _ALLOWED_MODULES,
    _COLUMN_HINTS,
    _RESULT_DIR,
    _SUPPORTED_CHAINS,
    _as_bool,
    _build_script_cache_context,
    _chain_from_parent_dirs,
    _collect_asset_hints,
    _collect_project_script_hub_assets,
    _complete_script_task,
    _find_matching_column,
    _force_rerun_requested,
    _get_task_state,
    _history_entry,
    _infer_chain_from_filename,
    _infer_wide_chain_from_filename,
    _iter_candidate_pep_files,
    _normalize_chain,
    _normalize_script_result,
    _pep_paths_from_request,
    _primary_pep_path_from_request,
    _profile_path_from_request,
    _read_table_columns,
    _record_stage,
    _resolve_results_root,
    _robust_read_csv,
    _sample_name_from_pep_file,
    _sanitize_nan,
    _script_executor,
    _set_task_state,
    _selected_samples_from_request,
    _selected_group_values_from_request,
    _selected_samples_by_group_from_request,
    _validate_selected_samples_against_group_values,
    _try_reuse_script_result,
    logger,
)

bp = Blueprint("script_hub_modules", __name__)


# ── Helper: inspect data selection payload ──

def _inspect_data_selection_payload(pep_paths: List[str], profile_path: Optional[str]) -> Dict[str, Any]:
    pep_files = _iter_candidate_pep_files(pep_paths)
    discovered_chains: set[str] = set()
    sample_names: set[str] = set()
    file_preview: List[Dict[str, Any]] = []
    warnings: List[str] = []
    pep_columns: List[str] = []

    for pep_file in pep_files:
        chain = _infer_wide_chain_from_filename(pep_file.name) or _chain_from_parent_dirs(pep_file)
        if not pep_columns:
            pep_columns = _read_table_columns(pep_file)
        if not chain:
            continue
        discovered_chains.add(chain)
        sample_names.add(_sample_name_from_pep_file(pep_file, chain))
        if len(file_preview) < 20:
            file_preview.append({
                "path": str(pep_file),
                "filename": pep_file.name,
                "chain": chain,
                "sample": _sample_name_from_pep_file(pep_file, chain),
            })

    random_pep_preview_file = None
    if pep_files:
        random_pep_file = random.choice(pep_files)
        random_chain = _infer_wide_chain_from_filename(random_pep_file.name) or _chain_from_parent_dirs(random_pep_file)
        random_pep_preview_file = {
            "path": str(random_pep_file),
            "filename": random_pep_file.name,
            "chain": random_chain,
            "sample": _sample_name_from_pep_file(random_pep_file, random_chain) if random_chain else "",
        }

    resolved_profile = str(profile_path or "").strip()
    profile_candidates = [resolved_profile] if resolved_profile else []

    profile_file = Path(resolved_profile) if resolved_profile else None
    profile_columns = _read_table_columns(profile_file)
    group_fields = [column for column in profile_columns if str(column).strip().lower() != "sample"]

    if pep_paths and not pep_files:
        warnings.append("No CSV files were found under the selected PEP paths.")
    if pep_files and not discovered_chains:
        warnings.append("CSV files were found, but no supported chain suffix was detected.")
    if resolved_profile and not profile_columns:
        warnings.append("Profile file was selected, but its header could not be read.")

    return {
        "pep_paths": pep_paths,
        "profile_path": resolved_profile,
        "profile_candidates": profile_candidates,
        "profile_columns": profile_columns,
        "group_fields": group_fields,
        "chains": sorted(discovered_chains),
        "chain_count": len(discovered_chains),
        "sample_count": len(sample_names),
        "samples": sorted(sample_names)[:50],
        "pep_file_count": len(pep_files),
        "pep_columns": pep_columns,
        "pep_files_preview": file_preview,
        "random_pep_preview_file": random_pep_preview_file,
        "warnings": warnings,
    }


# ── Helper: discover DB alignment inputs ──

def _discover_db_alignment_inputs(base_path: str, profile_path: Optional[str], requested_mapping: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    if not str(base_path or "").strip():
        raise ValidationError(message="base_path is required", details={"field": "base_path"})

    service = get_auto_heatmap_service()
    scan_result = service.scan_base_folder(base_path)

    filtered_samples: List[Dict[str, Any]] = []
    discovered_chains: set[str] = set()
    preview_file_path = ""
    preview_columns: List[str] = []
    preview_rows: List[List[Any]] = []

    for sample in scan_result.samples:
        normalized_files: Dict[str, Dict[str, Any]] = {}
        for file_info in sample.data_files:
            normalized_chain = _normalize_chain(_infer_chain_from_filename(file_info.filename))
            if normalized_chain not in _SUPPORTED_CHAINS:
                continue
            if normalized_chain not in normalized_files:
                normalized_files[normalized_chain] = {
                    "filename": file_info.filename,
                    "filepath": file_info.filepath,
                    "size": file_info.size,
                    "rows": file_info.rows,
                    "columns": file_info.columns,
                }
                discovered_chains.add(normalized_chain)
                if not preview_file_path:
                    preview_file_path = file_info.filepath

        if normalized_files:
            filtered_samples.append(
                {
                    "original_name": sample.original_name,
                    "display_name": sample.display_name,
                    "folder_path": sample.folder_path,
                    "data_files": list(normalized_files.values()),
                }
            )

    if not filtered_samples:
        raise ValidationError(
            message="No TRA/TRB pep files were detected under the selected base path",
            details={"base_path": base_path}
        )

    if not discovered_chains:
        raise ValidationError(
            message="DB alignment currently supports TRA/TRB files only",
            details={"base_path": base_path}
        )

    if preview_file_path:
        preview_result = service.get_file_columns(preview_file_path)
        preview_columns = list(preview_result.get("columns") or [])
        preview_rows = list(preview_result.get("sample_data") or [])
        suggested_mapping = {
            "cdr3_column": str(preview_result.get("suggested_cdr3") or _find_matching_column(preview_columns, _COLUMN_HINTS["cdr3_column"])).strip(),
            "copy_column": str(preview_result.get("suggested_copy") or _find_matching_column(preview_columns, _COLUMN_HINTS["copy_column"])).strip(),
        }
    else:
        suggested_mapping = {"cdr3_column": "", "copy_column": ""}

    requested_mapping = requested_mapping if isinstance(requested_mapping, dict) else {}
    resolved_mapping = {
        "cdr3_column": str(requested_mapping.get("cdr3_column") or suggested_mapping["cdr3_column"]).strip(),
        "copy_column": str(requested_mapping.get("copy_column") or suggested_mapping["copy_column"]).strip(),
    }

    missing_mapping = [name for name, value in resolved_mapping.items() if not value]
    if missing_mapping:
        raise ValidationError(
            message="Unable to auto-detect required DB alignment columns",
            details={
                "missing_fields": missing_mapping,
                "preview_file": preview_file_path,
                "available_columns": preview_columns,
            }
        )

    invalid_mapping = [value for value in resolved_mapping.values() if value not in preview_columns]
    if invalid_mapping:
        raise ValidationError(
            message="Selected field mapping does not exist in the detected pep file",
            details={"invalid_columns": invalid_mapping, "available_columns": preview_columns}
        )

    chain_list = sorted(discovered_chains)
    asset_hints = _collect_asset_hints(base_path, profile_path)
    sample_preview = [
        {
            "sample_name": sample["display_name"] or sample["original_name"],
            "chains": [_normalize_chain(_infer_chain_from_filename(file_info.get("filename", ""))) for file_info in sample["data_files"]],
            "file_count": len(sample["data_files"]),
        }
        for sample in filtered_samples[:20]
    ]

    return {
        "base_path": base_path,
        "summary": scan_result.summary,
        "samples": filtered_samples,
        "sample_count": len(filtered_samples),
        "pep_file_count": sum(len(sample["data_files"]) for sample in filtered_samples),
        "selected_chains": chain_list,
        "sample_preview": sample_preview,
        "preview_file_path": preview_file_path,
        "preview_columns": preview_columns,
        "preview_rows": preview_rows,
        "suggested_field_mapping": suggested_mapping,
        "resolved_field_mapping": resolved_mapping,
        **asset_hints,
    }


def _filter_discovery_samples(discovery: Dict[str, Any], selected_samples: List[str]) -> Dict[str, Any]:
    selected = {str(item).strip() for item in selected_samples if str(item).strip()}
    if not selected:
        return discovery
    selected_lookup = {_sample_match_key(item): item for item in selected}
    samples = []
    matched_keys: set[str] = set()
    available_examples: List[Dict[str, Any]] = []
    for sample in discovery.get("samples", []):
        aliases = _db_alignment_sample_aliases(sample)
        alias_keys = {_sample_match_key(alias) for alias in aliases if alias}
        if len(available_examples) < 12:
            available_examples.append({
                "display_name": sample.get("display_name"),
                "original_name": sample.get("original_name"),
                "aliases": aliases[:8],
            })
        exact_matches = alias_keys.intersection(selected_lookup.keys())
        loose_matches = {
            selected_key for selected_key in selected_lookup.keys()
            if any(_sample_key_loose_match(selected_key, alias_key) for alias_key in alias_keys)
        }
        if exact_matches or loose_matches:
            matched_keys.update(exact_matches or loose_matches)
            samples.append(sample)
    if not samples:
        raise ValidationError(
            message="No DB alignment samples matched the selected sample list. Check sample name prefixes/suffixes or choose samples from detected DB alignment sample names.",
            details={
                "selected_samples": sorted(selected)[:30],
                "selected_sample_keys": sorted(selected_lookup.keys())[:30],
                "db_alignment_samples": available_examples,
            },
        )
    unmatched = [selected_lookup[key] for key in selected_lookup.keys() if key not in matched_keys]
    chains = sorted({
        _normalize_chain(_infer_chain_from_filename(file_info.get("filename", "")))
        for sample in samples
        for file_info in sample.get("data_files", [])
        if _normalize_chain(_infer_chain_from_filename(file_info.get("filename", ""))) in _SUPPORTED_CHAINS
    })
    return {
        **discovery,
        "samples": samples,
        "sample_count": len(samples),
        "pep_file_count": sum(len(sample.get("data_files", [])) for sample in samples),
        "selected_chains": chains,
        "selected_samples_requested": sorted(selected),
        "selected_samples_unmatched": unmatched[:30],
        "sample_preview": [
            {
                "sample_name": sample.get("display_name") or sample.get("original_name"),
                "chains": [_normalize_chain(_infer_chain_from_filename(file_info.get("filename", ""))) for file_info in sample.get("data_files", [])],
                "file_count": len(sample.get("data_files", [])),
            }
            for sample in samples[:20]
        ],
    }


def _db_alignment_sample_aliases(sample: Dict[str, Any]) -> List[str]:
    aliases = [
        str(sample.get("display_name") or "").strip(),
        str(sample.get("original_name") or "").strip(),
        Path(str(sample.get("folder_path") or "")).name,
    ]
    for file_info in sample.get("data_files", []):
        filename = str(file_info.get("filename") or "").strip()
        if not filename:
            continue
        aliases.append(Path(filename).stem)
        chain = _normalize_chain(_infer_chain_from_filename(filename))
        if chain:
            aliases.append(_sample_name_from_pep_file(Path(filename), chain))
    return [item for item in unique_preserve_order(aliases) if item]


def _sample_match_key(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\.(csv|tsv|txt|gz|xlsx?)$", "", text)
    text = re.sub(r"(__|-|_)?(tra|trb|trg|trd|igh|igk|igl)$", "", text)
    return re.sub(r"[^a-z0-9]+", "", text)


def _sample_key_loose_match(left: str, right: str) -> bool:
    if not left or not right:
        return False
    if left == right:
        return True
    if min(len(left), len(right)) < 4:
        return False
    return left in right or right in left


def unique_preserve_order(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values:
        key = str(value or "").strip()
        if not key or key in seen:
            continue
        seen.add(key)
        result.append(key)
    return result


# ── Helper: build profile category preview ──

def _build_profile_category_preview(
    *,
    profile_path: str,
    profile_sheet: Optional[str] = None,
    categories: Optional[List[str]] = None,
) -> Dict[str, Any]:
    path = Path(str(profile_path or "").strip())
    if not path.exists() or not path.is_file():
        raise ValidationError(message="Profile file not found", details={"profile_path": profile_path})

    read_kwargs: Dict[str, Any] = {"low_memory": False}
    if profile_sheet:
        read_kwargs["sheet_name"] = profile_sheet
    df = _robust_read_csv(path, **read_kwargs)
    requested = [str(item).strip() for item in (categories or []) if str(item or "").strip()]
    if not requested:
        requested = [
            col for col in df.columns.tolist()
            if str(col or "").strip().lower() not in {"sample", "sample_id", "sample_name"}
        ]

    fields = []
    for field in requested:
        if field not in df.columns:
            fields.append({"field": field, "values": [], "unique_count": 0, "missing": True, "truncated": False})
            continue
        values = sorted(str(value) for value in df[field].dropna().unique().tolist() if str(value).strip())
        fields.append({
            "field": field,
            "values": values[:40],
            "unique_count": len(values),
            "missing": False,
            "truncated": len(values) > 40,
        })

    return {
        "profile_path": str(path.resolve()),
        "profile_sheet": profile_sheet or "",
        "fields": fields,
    }


# ── Helper: run DB alignment task ──

def _run_db_alignment_task(
    task_id: str,
    *,
    results_root: Path,
    base_path: str,
    output_name: Optional[str],
    profile_path: Optional[str],
    field_mapping: Dict[str, str],
    categories: List[str],
    contained_pathology: bool,
    pathology_values: List[str],
    selected_samples: Optional[List[str]] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "Inspect assets", "Scanning pep/Profile inputs for DB alignment", {"module": "db-alignment"})

        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping)
        discovery = _filter_discovery_samples(discovery, selected_samples or [])

        _record_stage(
            task_id,
            12,
            "Inspect assets",
            f"Detected {discovery['sample_count']} sample(s) and {len(discovery['selected_chains'])} chain(s)",
            {
                "module": "db-alignment",
                "sample_count": discovery["sample_count"],
                "selected_chains": discovery["selected_chains"],
            }
        )

        service = DBAlignmentService(output_parent=results_root / _RESULT_DIR)
        report = service.generate_report(
            samples=discovery["samples"],
            selected_chains=discovery["selected_chains"],
            field_mapping=discovery["resolved_field_mapping"],
            output_name=output_name,
            base_path=base_path,
            profile_path=profile_path,
            categories=categories,
            contained_pathology=contained_pathology,
            pathology_values=pathology_values,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id,
                max(12.0, float(progress or 0.0)),
                stage,
                detail,
                {"module": "db-alignment", **(meta or {})}
            )
        )

        result = {
            "module": "db-alignment",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "report_path": str(report.viewer_path),
            "viewer_url": f"/api/script-hub/results/{report.job_id}/viewer.html",
            "metadata_url": f"/api/script-hub/results/{report.job_id}/metadata.json",
            "zip_url": f"/api/script-hub/results/{report.job_id}/db_alignment_bundle.zip",
            "sample_count": int(report.metadata.get("sample_count") or 0),
            "selected_chains": list(report.metadata.get("selected_chains") or []),
            "profile_path": str(report.metadata.get("profile_path") or ""),
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="DB Alignment Results",
            subtitle="Chains: " + ", ".join(result.get("selected_chains") or []),
            dl_extras=[("metadata_url", "metadata.json", "Metadata")],
            zip_name="db_alignment_bundle.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="db-alignment",
            detail="DB alignment report generated",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:  # pragma: no cover - surfaced to UI and logs
        logger.error("Script hub DB alignment task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=100.0,
            stage="Failed",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "db-alignment"},
            history=history[-80:]
        )


# ── Routes ──

@bp.route("/modules", methods=["GET"])
def list_modules():
    return jsonify(
        {
            "success": True,
            "modules": [
                {
                    "key": "db-alignment",
                    "label": "数据库比对",
                    "status": "available",
                    "description": "基于 pep 和 Profile 数据，与 VDJdb / McPAS-TCR 公共数据库做精确匹配分析。",
                },
                {
                    "key": "profile",
                    "label": "Profile 分析",
                    "status": "available",
                    "description": "从 Datapoint/Profile CSV 读取分组字段与参数范围，生成分组箱线图并做 Mann-Whitney U 统计检验。",
                },
                {
                    "key": "pep-analysis",
                    "label": "PEP 共享分析",
                    "status": "available",
                    "description": "PEP 共享矩阵、V/J/VJ 使用频率、分组比较热图、CDR3 分类、排列热图和可视化。",
                },
                {
                    "key": "charts",
                    "label": "综合图表",
                    "status": "available",
                    "description": "基于 PEP 数据生成相似性热图、Treemap 和 Chord 图表报告。",
                },
                {
                    "key": "pgen-analysis",
                    "label": "Pgen 分析",
                    "status": "available",
                    "description": "参考 Pgen_260213 / SoNNia 流程，按样本和链计算 CDR3 Pgen、Q、Ppost 及 Pgen 均值汇总。",
                },
                {
                    "key": "topclone",
                    "label": "TopClone 分析",
                    "status": "available",
                    "description": "从 pep_data 计算 top clone 比例，再运行 BoxPlot 统计分析。",
                },
                {
                    "key": "umap",
                    "label": "UMAP 降维分析",
                    "status": "available",
                    "description": "基于 Mann-Whitney U 显著性预过滤的 UMAP 降维投影。",
                },
                {
                    "key": "volcano",
                    "label": "火山图分析",
                    "status": "available",
                    "description": "对 VJ usage 或表达矩阵做两组间差异比较，生成火山图（log2FC vs -log10 p-value）。",
                },
                {
                    "key": "go-kegg-enrichment",
                    "label": "GO/KEGG 富集分析",
                    "status": "available",
                    "description": "参考 G0_KEGG_enrichment：表达矩阵差异分析、火山图、GO/KEGG ORA 与 GSEA。",
                },
                {
                    "key": "umapin",
                    "label": "UMAPin 降维",
                    "status": "available",
                    "description": "基于 VJ usage 拼接数据做 UMAP 降维投影，可选 FDR 多重检验校正。",
                },
                {
                    "key": "ml-analysis",
                    "label": "机器学习分析",
                    "status": "available",
                    "description": "参考 ML_260526 随机森林流程，支持 Profile 特征或 PEP共享分析缓存的 VJ usage 特征。",
                },
                {
                    "key": "mait-nkt",
                    "label": "MAIT/NKT 分析",
                    "status": "available",
                    "description": "基于 TRA CDR3 宽表与参考 MAIT/iNKT 序列比对，计算丰度分数并生成分组箱线图。",
                },
            ],
        }
    )


@bp.route("/data-selection/inspect", methods=["POST"])
def inspect_data_selection():
    try:
        data = request.get_json() or {}
        project_id = str(data.get("project_id") or "").strip()
        project_assets = _collect_project_script_hub_assets(project_id)
        if project_id:
            pep_paths = project_assets["pep_paths"]
            profile_path = project_assets["profile_path"] or None
        else:
            pep_paths = _pep_paths_from_request(data)
            profile_path = _profile_path_from_request(data, "profile_path")
        discovery = _inspect_data_selection_payload(pep_paths, profile_path)
        invalid_profiles = project_assets.get("invalid_profile_paths", []) if project_id else []
        registered_profiles = project_assets.get("profile_paths", []) if project_id else []
        invalid_transcriptomes = project_assets.get("invalid_transcriptome_paths", []) if project_id else []
        registered_transcriptomes = project_assets.get("transcriptome_paths", []) if project_id else []
        if registered_profiles:
            discovery["registered_profile_paths"] = registered_profiles[:20]
        if registered_transcriptomes:
            discovery["registered_transcriptome_paths"] = registered_transcriptomes[:20]
            discovery["transcriptome_path"] = project_assets.get("transcriptome_path") or registered_transcriptomes[0]
        if invalid_profiles and not profile_path:
            discovery["warnings"].append(
                "项目已注册 Profile 资产无效或为空，请在项目资产页删除后重新注册有效的 Profile 文件。"
            )
            discovery["invalid_profile_paths"] = invalid_profiles[:5]
        if invalid_transcriptomes and not project_assets.get("transcriptome_path"):
            discovery["warnings"].append(
                "项目已注册转录组表达矩阵无效或为空，请在项目资产页删除后重新注册有效的表达矩阵。"
            )
            discovery["invalid_transcriptome_paths"] = invalid_transcriptomes[:5]
        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_data_selection: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Script Hub data selection: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_SELECTION_ERROR", "message": str(exc)}), 500


@bp.route("/db-alignment/inspect", methods=["POST"])
def inspect_db_alignment():
    try:
        data = request.get_json() or {}
        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path")
        profile_path = _profile_path_from_request(data, "profile_path")
        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else None
        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping)
        return jsonify(_sanitize_nan({"success": True, **discovery}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect_db_alignment: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error inspecting DB alignment inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/db-alignment/profile-categories", methods=["POST"])
def inspect_db_alignment_profile_categories():
    try:
        data = request.get_json() or {}
        profile_path = str(data.get("profile_path") or "").strip()
        profile_sheet = str(data.get("profile_sheet") or "").strip() or None
        categories = [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()]
        preview = _build_profile_category_preview(
            profile_path=profile_path,
            profile_sheet=profile_sheet,
            categories=categories,
        )
        return jsonify(_sanitize_nan({"success": True, **preview}))
    except ValidationError as exc:
        logger.warning("Validation error in inspect profile categories: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting profile categories: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_PROFILE_CATEGORY_ERROR", "message": str(exc)}), 500


@bp.route("/db-alignment/run", methods=["POST"])
def run_db_alignment():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "db-alignment").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        pep_paths = _pep_paths_from_request(data)
        base_path = _primary_pep_path_from_request(data, "base_path")
        if not base_path:
            raise ValidationError(message="base_path is required", details={"field": "base_path"})

        field_mapping = data.get("field_mapping") if isinstance(data.get("field_mapping"), dict) else {}
        output_name = str(data.get("output_name") or "").strip() or None
        profile_path = _profile_path_from_request(data, "profile_path")
        categories = [str(item).strip() for item in (data.get("categories") or []) if str(item).strip()]
        if not categories:
            raise ValidationError(message="Please select group field / 请选择分组字段", details={"field": "categories"})
        pathology_values = [str(item).strip() for item in (data.get("pathology_values") or []) if str(item).strip()]
        contained_pathology = _as_bool(data.get("contained_pathology"), False)
        selected_samples = _selected_samples_from_request(data)
        _validate_selected_samples_against_group_values(data)
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=(
                [{"asset_type": "pep", "path": path} for path in (pep_paths or [base_path])]
                + ([{"asset_type": "profile", "path": profile_path}] if profile_path else [])
            ),
            config_json={
                "field_mapping": {
                    "cdr3_column": str(field_mapping.get("cdr3_column") or "").strip(),
                    "copy_column": str(field_mapping.get("copy_column") or "").strip(),
                },
                "categories": categories,
                "contained_pathology": contained_pathology,
                "pathology_values": pathology_values,
                "selected_samples": selected_samples,
                "selected_group_values": _selected_group_values_from_request(data),
                "selected_samples_by_group": _selected_samples_by_group_from_request(data),
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        queued_meta = {"phase": "queued", "module": module_name, "base_path": base_path}
        _set_task_state(
            task_id,
            status="queued",
            progress=0.0,
            stage="Queued",
            detail="Task created and waiting to start",
            meta=queued_meta,
            history=[_history_entry(0.0, "Queued", "Task created and waiting to start", queued_meta)],
            **cache_context,
        )

        _script_executor.submit(
            _run_db_alignment_task,
            task_id,
            results_root=_resolve_results_root(),
            base_path=base_path,
            output_name=output_name,
            profile_path=profile_path,
            field_mapping={
                "cdr3_column": str(field_mapping.get("cdr3_column") or "").strip(),
                "copy_column": str(field_mapping.get("copy_column") or "").strip(),
            },
            categories=categories,
            contained_pathology=contained_pathology,
            pathology_values=pathology_values,
            selected_samples=selected_samples,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_db_alignment: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error queuing DB alignment task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500
