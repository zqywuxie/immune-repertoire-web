"""Modules listing, data-selection, and DB-alignment routes for the Script Hub API."""

import os
import random
import re
import uuid
from urllib.parse import quote
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
from flask_app.services.db_alignment_service import DBAlignmentService
from flask_app.services.project_storage_paths import script_output_parent
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
    _group_sample_identity_from_request,
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
    sample_files: Dict[tuple[str, str], List[Path]] = {}

    for pep_file in pep_files:
        chain = _infer_wide_chain_from_filename(pep_file.name) or _chain_from_parent_dirs(pep_file)
        if not pep_columns:
            pep_columns = _read_table_columns(pep_file)
        if not chain:
            continue
        sample_name = _sample_name_from_pep_file(pep_file, chain)
        discovered_chains.add(chain)
        sample_names.add(sample_name)
        identity = (chain, sample_name)
        resolved_file = pep_file.resolve()
        files_for_identity = sample_files.setdefault(identity, [])
        if resolved_file not in files_for_identity:
            files_for_identity.append(resolved_file)
        if len(file_preview) < 20:
            file_preview.append({
                "path": str(pep_file),
                "filename": pep_file.name,
                "chain": chain,
                "sample": sample_name,
            })

    sample_conflicts = []
    for (chain, sample), paths in sorted(sample_files.items()):
        if len(paths) < 2:
            continue
        common_root = Path(os.path.commonpath([str(path.parent) for path in paths]))
        sample_conflicts.append({
            "sample": sample,
            "chain": chain,
            "files": [path.relative_to(common_root).as_posix() for path in paths],
        })
    if sample_conflicts:
        examples = "、".join(
            f"{item['sample']}（{item['chain']}：{'、'.join(item['files'][:2])}）"
            for item in sample_conflicts[:5]
        )
        warnings.append(
            f"发现 {len(sample_conflicts)} 组同名且同链的克隆序列文件（例如：{examples}）。"
            "跨批次同名样本需选择支持批次字段的分析，并核对批次目录与指标表；未使用批次字段时，请先合并或重命名样本编号。"
        )

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
    if profile_file and not pep_files and profile_columns:
        sample_column = next((column for column in profile_columns
                              if str(column).strip().lower() in {"sample", "sample_id", "sample_name", "id"}), None)
        if sample_column:
            from flask_app.services.input_quality import inspect_input_quality
            checked = inspect_input_quality([], str(profile_file), "", "")
            profile_samples = checked["inputs"][0].get("samples", []) if checked["inputs"] else []
            sample_names.update(profile_samples)

    if pep_paths and not pep_files:
        warnings.append("所选克隆序列目录中没有找到数据文件。")
    if pep_files and not discovered_chains:
        warnings.append("已找到数据文件，但未识别出支持的链类型。")
    if resolved_profile and not profile_columns:
        warnings.append("无法读取所选样本指标表的表头。")

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
        "sample_conflicts": sample_conflicts,
        "random_pep_preview_file": random_pep_preview_file,
        "warnings": warnings,
    }


# ── Helper: discover DB alignment inputs ──

def _discover_db_alignment_inputs(base_path: str, profile_path: Optional[str], requested_mapping: Optional[Dict[str, Any]] = None, *, pep_paths: Optional[List[str]] = None, batch_field: Optional[str] = None) -> Dict[str, Any]:
    if not str(base_path or "").strip():
        raise ValidationError(message="base_path is required", details={"field": "base_path"})

    service = get_auto_heatmap_service()
    sources = list(dict.fromkeys(pep_paths or [base_path]))
    batch_values = set()
    if batch_field:
        if not profile_path:
            raise ValidationError(message="批次匹配需要样本指标表。")
        profile = DBAlignmentService._read_profile_frame(Path(profile_path))
        if batch_field not in profile.columns:
            raise ValidationError(message="所选批次字段不在样本指标表中。")
        batch_values = set(profile[batch_field].fillna("").astype(str).str.strip()) - {""}
    groups: Dict[tuple, Dict[str, Any]] = {}
    discovered_chains: set[str] = set()
    preview_file_path = ""
    preview_columns: List[str] = []
    preview_rows: List[List[Any]] = []
    seen_files = set()
    for source in sources:
        path = Path(source)
        if path.is_file():
            file = service._get_file_info(path.name, str(path))
            source_samples = [{"original_name": service._extract_sample_name_from_chain_file(path.name) or path.stem,
                               "display_name": path.stem, "folder_path": str(path.parent), "data_files": [file]}]
        else:
            scanned = service.scan_base_folder(source)
            source_samples = [{"original_name": sample.original_name, "display_name": sample.display_name,
                               "folder_path": sample.folder_path, "data_files": sample.data_files} for sample in scanned.samples]
        for sample in source_samples:
            for file in sample["data_files"]:
                chain = _normalize_chain(_infer_chain_from_filename(file.filename))
                if chain not in _SUPPORTED_CHAINS:
                    continue
                file_path = Path(file.filepath).resolve()
                if file_path in seen_files:
                    continue
                seen_files.add(file_path)
                sample_name = service._extract_sample_name_from_chain_file(file.filename) or sample["original_name"]
                batches = {ancestor.name.strip() for ancestor in file_path.parents if ancestor.name.strip() in batch_values}
                if len(batches) > 1:
                    raise ValidationError(message=f"克隆文件路径对应多个批次：{file.filename}")
                batch = next(iter(batches)) if batches else ""
                if batch_field and not batch:
                    raise ValidationError(message=f"克隆文件所在批次目录名需与批次字段值一致：{file.filename}")
                key = (sample_name, batch)
                entry = groups.setdefault(key, {"original_name": sample_name,
                    "display_name": f"{batch} / {sample_name}" if batch_field else sample_name,
                    "folder_path": str(file_path.parent), "batch": batch, "data_files": []})
                if any(_normalize_chain(_infer_chain_from_filename(item["filename"])) == chain for item in entry["data_files"]):
                    raise ValidationError(message=f"同一样本、批次与链型存在多个克隆文件，请选择正确批次字段或输入：{sample_name} / {batch or '未指定批次'} / {chain}")
                entry["data_files"].append({"filename": file.filename, "filepath": str(file_path),
                    "size": file.size, "rows": file.rows, "columns": file.columns})
                discovered_chains.add(chain)
                if not preview_file_path:
                    preview_file_path = str(file_path)
    filtered_samples = list(groups.values())

    if not filtered_samples:
        raise ValidationError(
            message="所选数据中未检测到 TRA/TRB 克隆文件。",
            details={"base_path": base_path}
        )

    if not discovered_chains:
        raise ValidationError(
            message="数据库比对仅支持 TRA/TRB 文件。",
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
            message="无法识别比对所需字段，请选择序列列和拷贝数列。",
            details={
                "missing_fields": missing_mapping,
                "preview_file": preview_file_path,
                "available_columns": preview_columns,
            }
        )

    invalid_mapping = [value for value in resolved_mapping.values() if value not in preview_columns]
    if invalid_mapping:
        raise ValidationError(
            message="所选映射字段不在克隆数据中，请重新检查。",
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

    reference_service = DBAlignmentService(output_parent=Path.cwd())
    reference_sources = [{"name": name, "available": path.is_file(), "path": str(path)} for name, path in (
        ("VDJdb", reference_service.vdjdb_path), ("McPAS-TCR", reference_service.mcpas_path), ("IEDB", reference_service.iedb_path))]
    return {
        "reference_sources": reference_sources,
        "base_path": base_path,
        "summary": f"发现 {len(filtered_samples)} 个样本身份、{len(seen_files)} 个克隆文件，含 {len(discovered_chains)} 种链型。",
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
            message="所选样本未匹配到比对数据，请核对样本编号，或从已识别的样本中重新选择。",
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
    db_service = DBAlignmentService(output_parent=Path.cwd())
    reference_paths = {
        "VDJdb": db_service.vdjdb_path,
        "McPAS-TCR": db_service.mcpas_path,
        "IEDB": db_service.iedb_path,
    }
    return {
        **discovery,
        "samples": samples,
        "sample_count": len(samples),
        "pep_file_count": sum(len(sample.get("data_files", [])) for sample in samples),
        "selected_chains": chains,
        "selected_samples_requested": sorted(selected),
        "selected_samples_unmatched": unmatched[:30],
        "reference_sources": [
            {"name": name, "available": path.is_file(), "path": str(path)}
            for name, path in reference_paths.items()
        ],
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
    pep_paths: Optional[List[str]] = None,
    batch_field: Optional[str] = None,
    selected_group_values: Optional[Dict[str, List[str]]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    group_sample_identity: str = "sample",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "检查比对输入", "正在检查克隆序列表与样本指标表", {"module": "db-alignment"})

        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping, pep_paths=pep_paths, batch_field=batch_field)
        discovery = _filter_discovery_samples(discovery, selected_samples or [])

        _record_stage(
            task_id,
            12,
            "检查比对输入",
            f"发现 {discovery['sample_count']} 个样本和 {len(discovery['selected_chains'])} 种链型",
            {
                "module": "db-alignment",
                "sample_count": discovery["sample_count"],
                "selected_chains": discovery["selected_chains"],
            }
        )

        service = DBAlignmentService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            samples=discovery["samples"],
            selected_chains=discovery["selected_chains"],
            field_mapping=discovery["resolved_field_mapping"],
            output_name=output_name,
            base_path=base_path,
            profile_path=profile_path,
            batch_field=batch_field,
            selected_samples=selected_samples,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
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
        summary_files = [report.summary_path, report.output_base / "specify_ratio_with_profile.csv", report.output_base / "alignment_summary.csv"]
        result["csv_urls"] = [f"/api/script-hub/results/{report.job_id}/{quote(path.relative_to(report.output_base).as_posix(), safe='/')}"
                              for path in summary_files if path.is_file()]
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="数据库比对结果",
            subtitle="链型：" + ", ".join(result.get("selected_chains") or []),
            dl_extras=[("metadata_url", "metadata.json", "分析详情"), ("csv_urls", None, "比对数据表")],
            zip_name="db_alignment_bundle.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="db-alignment",
            detail="数据库比对结果已生成",
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
            progress=float((_get_task_state(task_id) or {}).get("progress") or 0.0),
            stage="执行失败",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "db-alignment"},
            history=history[-80:]
        )


# ── Routes ──

@bp.route("/modules", methods=["GET"])
def list_modules():
    response = jsonify(
        {
            "success": True,
            "modules": [
                {"key":"immune-infiltration-consistency","label":"免疫浸润细胞相关性","status":"available","description":"组别校正后的细胞共同变化、相关矩阵及统计表。"},
                {"key":"immune-infiltration-concordance","label":"浸润与亚类方向比较","status":"available","description":"比较免疫球蛋白亚类与浸润细胞的组间变化方向。"},
                {"key":"immune-infiltration-pathway","label":"GO-BP 与浸润方向比较","status":"available","description":"复用完整 GO-BP 富集结果，按明确比较方向计算通路与细胞一致性。"},
                {"key":"immune-infiltration-sample-pathway","label":"GO-BP 与浸润样本级相关性","status":"available","description":"用转录组计算固定 GO-BP ssGSEA 分数，再与同样本浸润分数做组别校正相关和组内置换。"},
                {"key":"immune-infiltration-paired","label":"浸润与亚类配对相关性","status":"available","description":"使用明确的一对一配对计算组别校正后的跨数据相关性。"},
                {"key":"immune-infiltration","label":"免疫浸润组成与比较","status":"available","description":"按样本指标表匹配分组，生成细胞组成图及组间比较统计。"},
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
                    "description": "组合样本指标与 V/J 使用结果，按组间差异筛选特征并输出 UMAP 与 PERMANOVA。",
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
                    "description": "支持多分类模型比较、受试者分组嵌套交叉验证和稳定特征筛选，可使用样本指标、V/J 使用特征或两者联合分析。",
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


    import importlib.util
    from flask_app.services.module_runtime import enrichment_runtime_ready, infiltration_runtime_ready, consistency_runtime_ready, sample_pathway_runtime_ready
    payload = response.get_json()
    required = {'pgen-analysis': ('sonnia', 'Pgen 运行环境未配置，请联系管理员启用 SoNNia 模型。'), 'umap': ('umap', 'UMAP 运行环境未配置。'), 'umapin': ('umap', 'UMAP 运行环境未配置。')}
    for module in payload['modules']:
        if module['key'] in {'immune-infiltration-consistency','immune-infiltration-concordance','immune-infiltration-paired'} and not consistency_runtime_ready():
            module.update(status='unavailable', description='细胞相关性绘图环境尚未启用，请更新分析依赖镜像。')
        if module['key'] == 'immune-infiltration-sample-pathway' and not sample_pathway_runtime_ready():
            module.update(status='unavailable', unavailable_reason='样本级通路运行环境未就绪，需要 GSVA、GO 注释数据包及绘图依赖。')
        if module['key'] == 'immune-infiltration' and not infiltration_runtime_ready():
            module.update(status='unavailable', unavailable_reason='免疫浸润绘图运行环境未就绪，请检查分析基础镜像。')
        dependency = required.get(module['key'])
        if dependency and importlib.util.find_spec(dependency[0]) is None:
            module.update(status='unavailable', unavailable_reason=dependency[1])
        if module['key'] == 'go-kegg-enrichment' and not enrichment_runtime_ready():
            module.update(status='unavailable', unavailable_reason='GO/KEGG 运行环境未就绪，需要 R 与 clusterProfiler、org.Hs.eg.db、enrichplot、DOSE。')
    return jsonify(payload)


@bp.route("/data-selection/inspect", methods=["POST"])
def inspect_data_selection():
    try:
        data = request.get_json() or {}
        project_id = str(data.get("project_id") or "").strip()
        asset_set = str(data.get("asset_set") or "").strip()
        input_types = data.get("input_types")
        if input_types is not None and (not isinstance(input_types, list) or
                any(not isinstance(kind, str) or kind not in {"pep", "profile", "transcriptome", "deconvolution"} for kind in input_types)):
            raise ValidationError(message="数据检查范围不正确，请重新选择分析。")
        requested_types = set(input_types) if input_types is not None else None
        alignment_groups = data.get("alignment_groups")
        allowed_types = requested_types if requested_types is not None else {"pep", "profile", "transcriptome", "deconvolution"}
        if alignment_groups is not None and (not isinstance(alignment_groups, list) or any(
                not isinstance(group, list) or len(group) < 2 or
                any(not isinstance(kind, str) or kind not in allowed_types for kind in group) or
                len(set(group)) != len(group) for group in alignment_groups)):
            raise ValidationError(message="联合输入的样本检查范围不正确，请重新选择分析。")
        project_assets = _collect_project_script_hub_assets(
            project_id, asset_set or None, selections=data, input_types=requested_types)
        includes = lambda kind: requested_types is None or kind in requested_types
        if project_id:
            pep_paths = project_assets["pep_paths"]
            profile_path = project_assets["profile_path"] or None
        else:
            pep_paths = _pep_paths_from_request(data) if includes("pep") else []
            profile_path = _profile_path_from_request(data, "profile_path") if includes("profile") else None
        discovery = _inspect_data_selection_payload(pep_paths, profile_path)
        invalid_profiles = project_assets.get("invalid_profile_paths", []) if project_id else []
        registered_profiles = project_assets.get("profile_paths", []) if project_id else []
        invalid_transcriptomes = project_assets.get("invalid_transcriptome_paths", []) if project_id else []
        registered_transcriptomes = project_assets.get("transcriptome_paths", []) if project_id else []
        if project_id:
            discovery["deconvolution_path"] = project_assets.get("deconvolution_path", "")
            discovery["registered_deconvolution_paths"] = project_assets.get("deconvolution_paths", [])
            discovery["invalid_deconvolution_paths"] = project_assets.get("invalid_deconvolution_paths", [])
            if discovery["invalid_deconvolution_paths"]:
                discovery["warnings"].append("免疫细胞浸润结果表无法读取，请检查所选文件。")
        if registered_profiles:
            discovery["registered_profile_paths"] = registered_profiles[:20]
        if registered_transcriptomes:
            discovery["registered_transcriptome_paths"] = registered_transcriptomes[:20]
            discovery["transcriptome_path"] = project_assets.get("transcriptome_path") or ""
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
        from flask_app.services.input_quality import inspect_selected_input_quality
        discovery["input_quality"] = inspect_selected_input_quality(
            pep_paths, profile_path,
            (project_assets.get("transcriptome_path", "") if project_id else data.get("transcriptome_path", "")) if includes("transcriptome") else "",
            (project_assets.get("deconvolution_path", "") if project_id else data.get("deconvolution_path", "")) if includes("deconvolution") else "",
            profile_batch_field=project_assets.get("profile_batch_field") if project_id else None,
            alignment_groups=alignment_groups,
        )
        discovery["inspected_input_types"] = sorted(requested_types) if requested_types is not None else ["pep", "profile", "transcriptome", "deconvolution"]
        if not pep_paths and not profile_path:
            reference = next((item for item in discovery["input_quality"]["inputs"] if item.get("status") == "checked"), None)
            if reference:
                samples = reference.get("samples") or []
                discovery.update(sample_count=len(samples), samples=samples[:50])
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
        discovery = _discover_db_alignment_inputs(base_path, profile_path, field_mapping, pep_paths=pep_paths, batch_field=str(data.get("batch_field") or "").strip() or None)
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
            raise ValidationError(message="请选择分组字段。", details={"field": "categories"})
        pathology_values = [str(item).strip() for item in (data.get("pathology_values") or []) if str(item).strip()]
        contained_pathology = _as_bool(data.get("contained_pathology"), False)
        selected_samples = _selected_samples_from_request(data)
        selected_group_values = _selected_group_values_from_request(data)
        selected_samples_by_group = _selected_samples_by_group_from_request(data)
        batch_field = str(data.get("batch_field") or "").strip() or None
        group_sample_identity = _group_sample_identity_from_request(data)
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
                "batch_field": batch_field,
                "group_sample_identity": group_sample_identity,
                "selected_group_values": selected_group_values,
                "selected_samples_by_group": selected_samples_by_group,
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
            stage="等待执行",
            detail="数据库比对任务已加入队列。",
            meta=queued_meta,
            history=[_history_entry(0.0, "等待执行", "数据库比对任务已加入队列。", queued_meta)],
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
            pep_paths=pep_paths or None,
            batch_field=batch_field,
            selected_group_values=selected_group_values,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except ValidationError as exc:
        logger.warning("Validation error in run_db_alignment: %s", exc.message)
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("Error queuing DB alignment task: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


@bp.route("/data-selection/table-schema", methods=["POST"])
def inspect_selected_table_schema():
    try:
        from flask_app.routes.api_script_hub._common import _request_registered_assets
        from flask_app.services.input_table_schema import inspect_table_schema
        data = request.get_json() or {}
        kind = data.get('kind')
        if kind not in {'profile', 'transcriptome', 'deconvolution'}:
            raise ValidationError(message='请选择样本指标表、转录组或浸润表。')
        if not str(data.get('project_id') or '').strip():
            raise ValidationError(message='请先选择项目和数据集。')
        assets = _request_registered_assets(data, input_types={kind})
        value = assets.get(kind + '_path')
        if not value:
            raise ValidationError(message='当前数据集尚未登记可读取的此类表格。')
        schema = inspect_table_schema(value, data.get('sheet_name'))
        return jsonify({'success': True, 'kind': kind, **schema})
    except ValidationError as exc:
        return jsonify({'success': False, 'message': exc.message, 'details': exc.details}), 400
    except (OSError, ValueError, KeyError):
        return jsonify({'success': False, 'message': '表格无法读取，请检查文件格式。'}), 400
