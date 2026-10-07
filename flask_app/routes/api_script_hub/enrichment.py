"""Enrichment and visualization routes: umap, volcano, go-kegg, umapin, ml-analysis, mait-nkt."""

import uuid
import zipfile
import re
import math
from urllib.parse import quote
from itertools import combinations
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from flask import Blueprint, current_app, jsonify, request

from flask_app.exceptions import ValidationError
from flask_app.services.umap_service import UmapService
from flask_app.services.volcano_service import VolcanoService
from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService
from flask_app.services.umapin_service import UmapinService
from flask_app.services.unified_umap_service import UnifiedUmapService
from flask_app.services.ml_analysis_service import MLAnalysisService
from flask_app.services.mait_nkt_service import MaitNktService
from flask_app.services.figure_style import save_publication_png
from flask_app.services.path_access_service import PathAccessService
from flask_app.services.path_config import RESULTS_DIR
from flask_app.services.project_storage_paths import script_output_parent
from ._common import (
    _ALLOWED_MODULES,
    _RESULT_DIR,
    _as_bool,
    _build_and_save_viewer,
    _build_script_cache_context,
    _collect_project_cached_usage_assets,
    _collect_project_script_hub_assets,
    _complete_script_task,
    _force_rerun_requested,
    _group_sample_identity_from_request,
    _selected_samples_from_request,
    _selected_group_values_from_request,
    _selected_samples_by_group_from_request,
    _validate_selected_samples_against_group_values,
    _get_task_state,
    _history_entry,
    _infer_wide_chain_from_filename,
    _iter_candidate_pep_files,
    _normalize_chain,
    _normalize_script_result,
    _profile_path_from_request,
    _looks_like_category_row,
    _read_header_columns,
    _read_table_columns,
    _record_stage,
    _resolve_usage_data_dir,
    _request_registered_assets,
    _resolve_pep_analysis_tra_source,
    _resolve_project_cached_usage_path,
    _resolve_results_root,
    _robust_read_csv,
    _sanitize_nan,
    _script_executor,
    _set_task_state,
    _suggest_profile_ranges,
    _suggest_umap_ranges,
    _transcriptome_path_from_request,
    _try_reuse_script_result,
    get_script_hub_job_service,
    logger,
)
from .profile_analysis import _suggest_profile_ranges, _suggest_umap_ranges
bp = Blueprint("script_hub_enrichment", __name__)

_MAIT_SAMPLE_COLUMNS = ("sample", "sample_id", "sample_name", "display_name")
_MAIT_CDR3_COLUMNS = ("junction_aa", "cdr3_aa", "cdr3", "cdr3(pep)", "aa_sequence")
_MAIT_COUNT_COLUMNS = ("count", "umi_count", "duplicate_count", "copies", "copy", "reads", "frequency")
_MAIT_V_COLUMNS = ("v_call", "v_gene", "v")
_MAIT_J_COLUMNS = ("j_call", "j_gene", "j")


def _mait_column_lookup(df: pd.DataFrame) -> Dict[str, Any]:
    return {str(col).strip().lower(): col for col in df.columns}


def _first_existing_column(lookup: Dict[str, Any], candidates: tuple[str, ...]) -> Optional[Any]:
    for name in candidates:
        if name in lookup:
            return lookup[name]
    return None


def _normalize_mait_tra_dataframe(tra_df: pd.DataFrame, source_label: str = "受体 α 链数据", batch_field: Optional[str] = None) -> pd.DataFrame:
    """Validate MAIT/NKT TRA input and normalize long tables to CDR3 x sample wide form."""
    if tra_df is None or tra_df.empty:
        raise ValidationError(
            message="MAIT/NKT 分析需要 TRA 链数据。当前选择的数据源为空，请选择包含 TRA 的 PEP cache，或手动上传 TRA CSV。",
            details={"source": source_label},
        )

    lookup = _mait_column_lookup(tra_df)
    sample_col = _first_existing_column(lookup, _MAIT_SAMPLE_COLUMNS)
    cdr3_col = _first_existing_column(lookup, _MAIT_CDR3_COLUMNS)
    count_col = _first_existing_column(lookup, _MAIT_COUNT_COLUMNS)
    v_col = _first_existing_column(lookup, _MAIT_V_COLUMNS)
    j_col = _first_existing_column(lookup, _MAIT_J_COLUMNS)

    if sample_col is not None and cdr3_col is not None:
        fields = [sample_col, cdr3_col] + ([count_col] if count_col is not None else [])
        if batch_field and batch_field in tra_df.columns:
            fields.append(batch_field)
        work = tra_df[list(dict.fromkeys(fields))].fillna("").copy()
        work[sample_col] = work[sample_col].astype(str).str.strip()
        work[cdr3_col] = work[cdr3_col].astype(str).str.strip()
        if work[sample_col].eq("").any() or work[cdr3_col].eq("").any():
            raise ValidationError(message="受体 α 链长表存在空样本编号或克隆序列。")
        if batch_field and batch_field in work.columns:
            from flask_app.services.pep_analysis_service import _batch_sample_identity
            batches = work[batch_field].astype(str).str.strip()
            if batches.eq("").any():
                raise ValidationError(message="受体 α 链长表存在空批次值。")
            work[sample_col] = [_batch_sample_identity(batch, sample) for batch, sample in zip(batches, work[sample_col])]
        if count_col is not None:
            counts = pd.to_numeric(work[count_col], errors="coerce")
            if not counts.map(math.isfinite).all() or (counts < 0).any():
                raise ValidationError(message="受体 α 链长表含无效拷贝数，请检查空值、非数值、无穷值或负数。")
            work["__mait_count__"] = counts
        else:
            work["__mait_count__"] = 1
        if work.empty:
            raise ValidationError(
                message="MAIT/NKT 分析需要 TRA 链数据。当前 TRA Source 中没有有效的 sample/CDR3 记录。",
                details={"source": source_label, "sample_column": str(sample_col), "cdr3_column": str(cdr3_col)},
            )
        wide = work.pivot_table(
            index=cdr3_col,
            columns=sample_col,
            values="__mait_count__",
            aggfunc="sum",
            fill_value=0,
        ).reset_index()
        wide = wide.rename(columns={cdr3_col: "CDR3"})
        wide.columns = [str(col) for col in wide.columns]
        return wide

    if tra_df.shape[1] > 1:
        sample_columns = [str(col) for col in tra_df.columns[1:] if str(col).strip()]
        if sample_columns:
            return tra_df.copy()

    raise ValidationError(
        message="MAIT/NKT 分析需要 TRA 链数据。当前选择的数据源不包含可识别的 TRA 矩阵或 sample/junction_aa 字段。",
        details={
            "source": source_label,
            "available_columns": [str(col) for col in tra_df.columns[:12]],
            "accepted_sample_columns": list(_MAIT_SAMPLE_COLUMNS),
            "accepted_cdr3_columns": list(_MAIT_CDR3_COLUMNS),
            "accepted_count_columns": list(_MAIT_COUNT_COLUMNS),
            "detected_v_column": str(v_col) if v_col is not None else "",
            "detected_j_column": str(j_col) if j_col is not None else "",
        },
    )


def _run_umap_task(
    task_id: str,
    *,
    results_root: Path,
    datapoint_path: str,
    classification_begin: str,
    classification_over: str,
    param_begin: str,
    param_over: str,
    pvalue_threshold: float = 0.05,
    n_neighbors: int = 6,
    min_dist: float = 0.01,
    output_name: Optional[str] = None,
    module_name: str = "umap",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "检查样本指标表", "正在读取文件并核对分组列与特征范围", {"module": module_name})
        dp_path = str(datapoint_path)
        if Path(dp_path).exists():
            columns = _robust_read_csv(dp_path, nrows=0).columns.tolist()
        else:
            raise FileNotFoundError(f"未找到样本指标表：{dp_path}")
        if (not classification_begin or not classification_over) and columns:
            range_suggestions = _suggest_umap_ranges(columns)
            classification_begin = classification_begin or range_suggestions["suggested_classification_begin"]
            classification_over = classification_over or range_suggestions["suggested_classification_over"]
        if classification_begin not in columns:
            raise ValidationError(message=f"未找到分组字段：{classification_begin}")
        if classification_over not in columns:
            raise ValidationError(message=f"未找到分组字段：{classification_over}")
        if param_begin not in columns:
            raise ValidationError(message=f"未找到特征字段：{param_begin}")
        if param_over not in columns:
            raise ValidationError(message=f"未找到特征字段：{param_over}")

        _record_stage(task_id, 10, "准备降维分析", f"已读取 {len(columns)} 个字段，开始检查所选样本与特征", {"module": module_name})

        service = UmapService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            datapoint_path=dp_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        pdf_urls = []
        for p in report.pdf_paths:
            rel = Path(p).relative_to(report.output_base)
            pdf_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        zip_url = ""
        if report.zip_path:
            zp = Path(report.zip_path)
            if zp.exists():
                rel = zp.relative_to(report.output_base)
                zip_url = f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "pdf_urls": pdf_urls,
            "csv_urls": csv_urls,
            "zip_url": zip_url,
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="UMAP 样本降维结果",
            subtitle="样本指标表：" + str(report.metadata.get("datapoint_path") or datapoint_path),
            dl_extras=[("csv_urls", None, "坐标数据表"), ("pdf_urls", None, "结果图 PDF")],
            zip_name="umap_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"UMAP 降维完成，生成 {len(report.png_paths)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("UMAP task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=0.0, stage="分析失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


def _unified_umap_config(data, profile_path):
    label = str(data.get("label_column") or data.get("group_field") or "").strip()
    raw_groups = data.get("selected_group_values")
    if isinstance(raw_groups, dict) and label in raw_groups and raw_groups[label] == []:
        raise ValidationError(message="请至少选择两个分组后再运行 UMAP。")
    configurations = data.get("configurations") if isinstance(data.get("configurations"), list) else ["profile"]
    configurations = list(dict.fromkeys(str(item).strip().lower() for item in configurations if str(item).strip()))
    uses_vj = any("vj" in item.split("+") for item in configurations)
    usage = str(data.get("vj_usage_path") or "").strip() if uses_vj else ""
    if uses_vj:
        usage = usage or _resolve_project_cached_usage_path(data, preferred="umapin")
    group_order = data.get("group_order")
    if not isinstance(group_order, list):
        group_order = str(group_order or "").split(",")
    return {
        "output_name": str(data.get("output_name") or "").strip(),
        "profile_path": profile_path, "sample_column": str(data.get("sample_column") or "").strip(),
        "label_column": label, "batch_field": str(data.get("batch_field") or "").strip(),
        "configurations": configurations, "vj_usage_path": usage,
        "profile_start": str(data.get("param_begin") or "").strip(),
        "profile_end": str(data.get("param_over") or "").strip(),
        "include_labels": _selected_group_values_from_request(data).get(label, []),
        "selected_samples": _selected_samples_from_request(data),
        "selected_samples_by_group": _selected_samples_by_group_from_request(data),
        "group_sample_identity": _group_sample_identity_from_request(data),
        "group_order": [str(item).strip() for item in group_order if str(item).strip()],
        "raw_p_threshold": float(data.get("raw_p_threshold", data.get("pvalue_threshold", 0.05))),
        "comparison_cohort": str(data.get("comparison_cohort") or "auto").strip(),
        "n_neighbors": int(data.get("n_neighbors", 6)), "min_dist": float(data.get("min_dist", 0.01)),
        "n_epochs": int(data.get("n_epochs", 50)), "permutations": int(data.get("permanova_permutations", 999)),
        "random_state": int(data.get("random_state", 42)), "permanova_random_state": int(data.get("permanova_random_state", 42)),
    }


def _run_unified_umap_task(task_id: str, *, results_root: Path, config: Dict[str, Any], app_context_app: Optional[Any] = None) -> None:
    try:
        _record_stage(task_id, 5, "核对 UMAP 输入", "正在准备样本指标、V/J 特征与分组比较。", {"module": "umap", "phase": "validate"})
        service = UnifiedUmapService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            **{**config, "output_name": config.get("output_name") or task_id},
            progress_callback=lambda progress, stage, detail: _record_stage(
                task_id, float(progress or 0), stage, detail,
                {"module": "umap", "phase": "calculate"},
            ),
        )
        base_url = f"/api/script-hub/results/{report.job_id}"
        png_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.png_paths]
        csv_urls = [f"{base_url}/{path.relative_to(report.output_base).as_posix()}" for path in report.csv_paths]
        zip_url = f"{base_url}/{report.zip_path.relative_to(report.output_base).as_posix()}"
        result = {
            "module": "umap", "analysis_mode": "unified", "job_id": report.job_id,
            "output_base": str(report.output_base), "png_urls": png_urls,
            "csv_urls": csv_urls, "zip_url": zip_url, "metadata": report.metadata,
        }
        summary = pd.read_csv(report.output_base / "permanova_summary.csv")
        _normalize_script_result(
            result, report.output_base, report.metadata,
            title="统一多模态 UMAP 结果",
            subtitle=f"配置：{'、'.join({'profile': '样本指标', 'vj': 'V/J 特征', 'vj+profile': '联合特征'}.get(item, item) for item in report.metadata['configurations'])}；比较数：{len(summary)}",
            dl_extras=[("csv_urls", None, "特征筛选、UMAP 坐标与 PERMANOVA 统计表")],
            zip_name="统一多模态 UMAP 结果.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id, module_name="umap", detail=f"统一多模态 UMAP 完成，生成 {len(png_urls)} 张图。",
            result=result, history=history, app_context_app=app_context_app,
        )
    except Exception as exc:
        logger.error("Unified UMAP task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=float((_get_task_state(task_id) or {}).get("progress") or 0), stage="分析失败",
                        detail=str(exc), error=str(exc), meta={"phase": "failed", "module": "umap"},
                        history=history[-80:])


@bp.route("/umap/inspect", methods=["POST"])
def inspect_umap():
    try:
        data = request.get_json() or {}
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        if not datapoint_path:
            raise ValidationError(message="请选择样本指标表。", details={"field": "datapoint_path"})

        dp = Path(datapoint_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="未找到所选样本指标表，请重新选择数据。", details={"datapoint_path": datapoint_path})
        df = _robust_read_csv(dp, nrows=0)
        columns = df.columns.tolist()
        suggestions = _suggest_umap_ranges(columns)
        sample_candidates = [column for column in columns if str(column).strip().lower() in {"sample", "sample_id", "sample_name", "id"}]
        group_candidates = [column for column in columns if str(column).strip().lower() in {"group", "category", "timepoint", "condition", "cohort"}]
        batch_candidates = [column for column in columns if str(column).strip().lower() in {"batch", "batch_id", "batch_name", "run", "run_id", "cohort_batch"}]
        vj_usage_path = str(data.get("vj_usage_path") or "").strip()
        recommended = None
        available = []
        if data.get("project_id") and data.get("asset_set"):
            from flask_app.services.analysis_artifacts import scoped_pep_candidates
            available = [candidate for candidate in scoped_pep_candidates(data["project_id"], data["asset_set"], "umapin")
                         if candidate["status"] == "available"]
            canonical = [candidate for candidate in available if Path(candidate["path"]).name == "df_VJ_all.csv"]
            if not data.get("upstream_artifact_id") and not vj_usage_path:
                if len(canonical) == 1:
                    recommended = canonical[0]
                elif len(available) == 1:
                    recommended = available[0]
                if recommended:
                    vj_usage_path = recommended["path"]
        elif not vj_usage_path:
            try:
                vj_usage_path = _resolve_project_cached_usage_path(data, preferred="umapin")
            except ValidationError:
                vj_usage_path = ""
        return jsonify({
            "success": True,
            "datapoint_path": str(dp.resolve()),
            "columns": columns,
            "column_count": len(columns),
            "sample_column_candidates": sample_candidates,
            "suggested_sample_column": sample_candidates[0] if sample_candidates else columns[0],
            "group_column_candidates": group_candidates,
            "suggested_group_column": group_candidates[0] if group_candidates else "",
            "batch_column_candidates": batch_candidates,
            "vj_usage_path": vj_usage_path,
            "vj_usage_available": bool(available or (vj_usage_path and Path(vj_usage_path).exists())),
            "vj_upstream_artifact_id": (recommended or {}).get("artifact_id"),
            "vj_candidate_count": len(available),
            **suggestions,
        })
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/umap/run", methods=["POST"])
def run_umap():
    try:
        data = request.get_json() or {}
        module_name = "umap"
        datapoint_path = _profile_path_from_request(data, "datapoint_path", "profile_path") or ""
        if str(data.get("analysis_mode") or "").strip().lower() == "unified":
            if not datapoint_path or not Path(datapoint_path).is_file():
                raise ValidationError(message="统一 UMAP 需要有效的样本指标表。")
            columns = _robust_read_csv(datapoint_path, nrows=0).columns.tolist()
            sample_column = str(data.get("sample_column") or "").strip()
            label_column = str(data.get("label_column") or data.get("group_field") or "").strip()
            batch_field = str(data.get("batch_field") or "").strip()
            if sample_column not in columns or label_column not in columns:
                raise ValidationError(message="请选择有效的样本编号列和分组列。")
            if batch_field and (batch_field not in columns or batch_field in {sample_column, label_column}):
                raise ValidationError(message="所选批次字段无效，请重新选择。")
            configurations = data.get("configurations") if isinstance(data.get("configurations"), list) else ["profile"]
            configurations = list(dict.fromkeys(str(item).strip().lower() for item in configurations if str(item).strip()))
            if not configurations or any(item not in {"profile", "vj", "vj+profile"} for item in configurations):
                raise ValidationError(message="配置仅支持 Profile、VJ 或 VJ+Profile。")
            vj_usage_path = str(data.get("vj_usage_path") or "").strip()
            if any("vj" in item.split("+") for item in configurations):
                vj_usage_path = vj_usage_path or _resolve_project_cached_usage_path(data, preferred="umapin")
                if not vj_usage_path or not Path(vj_usage_path).exists():
                    raise ValidationError(message="当前数据集没有可用的 V/J 特征结果，请先完成克隆共享分析并选择产物。")
            config = _unified_umap_config(data, datapoint_path)
            _validate_selected_samples_against_group_values({**data, "sample_col": sample_column})
            UnifiedUmapService.prepare_profile(**{key: config[key] for key in (
                "profile_path", "sample_column", "label_column", "batch_field", "include_labels",
                "selected_samples", "selected_samples_by_group", "group_sample_identity",
            )})
            project_id = str(data.get("project_id") or "").strip() or None
            input_paths = [{"asset_type": "profile", "path": datapoint_path}]
            if vj_usage_path and any("vj" in item.split("+") for item in configurations):
                input_paths.append({"asset_type": "cached_usage", "path": vj_usage_path})
            cache_context = _build_script_cache_context(
                project_id=project_id, module_name="umap", input_paths=input_paths,
                config_json={"analysis_mode": "unified", **config},
            )
            if not _force_rerun_requested(data):
                reused = _try_reuse_script_result(cache_context, "umap")
                if reused:
                    return jsonify(reused)
            task_id = f"script_task_{uuid.uuid4().hex[:12]}"
            meta = {"phase": "queued", "module": "umap", "analysis_mode": "unified"}
            _set_task_state(task_id, status="queued", progress=0.0, stage="排队中", detail="统一多模态 UMAP 已加入任务队列。", meta=meta,
                            history=[_history_entry(0.0, "排队中", "统一多模态 UMAP 已加入任务队列。", meta)], **cache_context)
            _script_executor.submit(
                _run_unified_umap_task, task_id, results_root=_resolve_results_root(), config=config,
                app_context_app=current_app._get_current_object() if project_id else None,
            )
            return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
        classification_begin = str(data.get("classification_begin") or "").strip()
        classification_over = str(data.get("classification_over") or "").strip()
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()

        if not datapoint_path:
            raise ValidationError(message="请选择样本指标表。")

        dp = Path(datapoint_path)
        if not dp.exists() or not dp.is_file():
            raise ValidationError(message="未找到所选样本指标表，请重新选择数据。", details={"datapoint_path": datapoint_path})
        columns = _robust_read_csv(dp, nrows=0).columns.tolist()
        suggestions = _suggest_umap_ranges(columns)
        classification_begin = classification_begin or suggestions["suggested_classification_begin"]
        classification_over = classification_over or suggestions["suggested_classification_over"]
        param_begin = param_begin or suggestions["suggested_param_begin"]
        param_over = param_over or suggestions["suggested_param_over"]
        if not param_begin or not param_over:
            raise ValidationError(message="请选择特征范围的起始列和结束列。")
        if not classification_begin or not classification_over:
            raise ValidationError(message="请选择分组范围的起始列和结束列。")

        pvalue_threshold = float(data.get("pvalue_threshold") or 0.05)
        n_neighbors = int(data.get("n_neighbors") or 6)
        min_dist = float(data.get("min_dist") or 0.01)
        output_name = str(data.get("output_name") or "").strip() or None
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[{"asset_type": "profile", "path": datapoint_path}],
            config_json={
                "classification_begin": classification_begin,
                "classification_over": classification_over,
                "param_begin": param_begin,
                "param_over": param_over,
                "pvalue_threshold": pvalue_threshold,
                "n_neighbors": n_neighbors,
                "min_dist": min_dist,
            },
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="Queued",
                        detail="Task created", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "Queued", "Task created", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_umap_task, task_id,
            results_root=_resolve_results_root(),
            datapoint_path=datapoint_path,
            classification_begin=classification_begin,
            classification_over=classification_over,
            param_begin=param_begin,
            param_over=param_over,
            pvalue_threshold=pvalue_threshold,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            output_name=output_name,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except (ValidationError, ValueError) as exc:
        return jsonify({"success": False, "error": getattr(exc, "error_code", "VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Volcano Analysis ----

def _usage_union_columns(data_dir: Path) -> List[str]:
    columns: List[str] = ["sample", "Category"]
    seen = set(columns)
    for csv_path in sorted(data_dir.glob("*.csv")):
        header = _read_header_columns(csv_path)
        if "Category" not in header:
            continue
        category_idx = header.index("Category")
        for col in header[category_idx + 1:]:
            if col not in seen:
                seen.add(col)
                columns.append(col)
    return columns


def _parse_group_comparisons(raw_value: Any) -> List[List[str]]:
    if raw_value is None:
        return []
    if isinstance(raw_value, str):
        text = raw_value.strip()
        if not text:
            return []
        pairs = []
        for line in re.split(r"[\n;]+", text):
            line = line.strip()
            if not line:
                continue
            if "_vs_" in line:
                left, right = line.split("_vs_", 1)
            elif "," in line:
                left, right = line.split(",", 1)
            else:
                continue
            pairs.append([left.strip(), right.strip()])
        return [pair for pair in pairs if pair[0] and pair[1] and pair[0] != pair[1]]
    if isinstance(raw_value, list):
        pairs = []
        for item in raw_value:
            if isinstance(item, str):
                pairs.extend(_parse_group_comparisons(item))
                continue
            if isinstance(item, dict):
                left = str(item.get("group1") or "").strip()
                right = str(item.get("group2") or "").strip()
            elif isinstance(item, (list, tuple)) and len(item) >= 2:
                left = str(item[0] or "").strip()
                right = str(item[1] or "").strip()
            else:
                continue
            if left and right and left != right:
                pairs.append([left, right])
        return pairs
    return []


def _normalize_expression_group_label(value: Any, group_prefix: str = "tpm_") -> str:
    label = str(value or "").strip()
    if group_prefix and label.startswith(group_prefix):
        label = label[len(group_prefix):]
    label = re.sub(r"_\d+$", "", label).strip("_ ")
    return label


def _normalize_expression_comparisons(
    comparisons: List[List[str]],
    group_prefix: str = "tpm_",
) -> List[List[str]]:
    normalized: List[List[str]] = []
    for left, right in comparisons:
        clean_left = _normalize_expression_group_label(left, group_prefix)
        clean_right = _normalize_expression_group_label(right, group_prefix)
        if clean_left and clean_right and clean_left != clean_right:
            pair = [clean_left, clean_right]
            if pair not in normalized:
                normalized.append(pair)
    return normalized


def _volcano_config(data):
    mode = str(data.get("input_mode") or "usage").strip().lower()
    if mode not in {"usage", "expression"}:
        raise ValidationError(message="请选择有效的差异分析输入模式。")
    prefix = str(data.get("group_prefix") or "tpm_").strip() if mode == "expression" else ""
    pairs = _parse_group_comparisons(data.get("comparisons"))
    if mode == "expression":
        pairs = _normalize_expression_comparisons(pairs, prefix)
    if "comparisons" in data and data["comparisons"] is not None and not pairs:
        raise ValidationError(message="至少选择一个组间比较。", details={"field": "comparisons"})
    try:
        pvalue = float(data.get("pvalue_threshold") if data.get("pvalue_threshold") is not None else 0.05)
        logfc = float(data.get("logfc_cutoff") if data.get("logfc_cutoff") is not None else 1.0)
    except (ValueError, TypeError):
        raise ValidationError(message="差异分析阈值必须为有效数字。")
    if not math.isfinite(pvalue) or not 0 < pvalue <= 1 or not math.isfinite(logfc) or logfc < 0:
        raise ValidationError(message="P 值阈值需在 0 到 1 之间，对数倍数变化阈值不得为负数。")
    config = {"input_mode": mode, "group_prefix": prefix,
        "comparisons": pairs if data.get("comparisons") is not None else "all-pairs",
        "pvalue_threshold": pvalue, "logfc_cutoff": logfc if mode == "expression" else None}
    if mode == "usage" or mode == "expression":
        for field in (("selected_categories", "selected_samples") if mode == "usage" else ("selected_expression_groups", "selected_expression_samples")):
            choices = data.get(field)
            if choices is not None and (not isinstance(choices, list) or not all(isinstance(x, str) for x in choices)):
                raise ValidationError(message="样本与分组选择必须为文本列表。", details={"field": field})
            config[field] = choices
    return config


@bp.route("/volcano/inspect", methods=["POST"])
def inspect_volcano():
    try:
        data = request.get_json() or {}
        input_mode = str(data.get("input_mode") or "usage").strip().lower()
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(
                data,
                "expression_path",
                "transcriptome_path",
                "profile_path",
                "datapoint_path",
            ) or ""
            if not expression_path:
                raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
            group_prefix = str(data.get("group_prefix") or "tpm_").strip()
            inspect = VolcanoService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)
            return jsonify({"success": True, "input_mode": "expression", **inspect})

        data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
        base_path = str(data.get("base_path") or "").strip()

        if not data_dir and not base_path:
            raise ValidationError(message="data_dir or base_path is required", details={"field": "data_dir"})

        source = data_dir or base_path
        inspected = VolcanoService.prepare_usage_inputs(source)
        return jsonify({"success": True, "data_dir": str(Path(source).resolve()),
            "file_count": len(inspected["tables"]), "files": [path.name for path, _ in inspected["tables"]],
            "sample_count": len(inspected["samples"]), "groups": inspected["groups"],
            "samples_by_value": inspected["samples_by_value"], "group_counts": inspected["group_counts"],
            "suggested_comparisons": [{"group1": left, "group2": right}
                for left, right in combinations(inspected["groups"], 2)]})
    except (ValueError, FileNotFoundError) as exc:
        return jsonify(success=False, message=str(exc)), 400
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting Volcano inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_volcano_task(
    task_id: str,
    *,
    results_root: Path,
    data_dir: str,
    input_mode: str = "usage",
    expression_path: str = "",
    group_prefix: str = "tpm_",
    comparisons: Optional[List[List[str]]] = None,
    pvalue_threshold: float = 0.05,
    logfc_cutoff: float = 1.0,
    selected_expression_groups=None,
    selected_expression_samples=None,
    selected_categories=None,
    selected_samples=None,
    output_name: Optional[str] = None,
    module_name: str = "volcano",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "火山图分析", f"扫描 {expression_path or data_dir}", {"module": module_name})

        local_data_dir = data_dir

        service = VolcanoService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        if input_mode == "expression":
            report = service.generate_expression_report(
                expression_path=expression_path,
                selected_expression_groups=selected_expression_groups, selected_expression_samples=selected_expression_samples,
                group_prefix=group_prefix,
                comparisons=comparisons,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                output_name=output_name,
                progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                    task_id, float(progress or 0.0), stage, detail,
                    {"module": module_name, **(meta or {})}
                )
            )
        else:
            report = service.generate_report(
                data_dir=local_data_dir,
                pvalue_threshold=pvalue_threshold,
                comparisons=comparisons,
                selected_categories=selected_categories, selected_samples=selected_samples, output_name=output_name,
                progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                    task_id, float(progress or 0.0), stage, detail,
                    {"module": module_name, **(meta or {})}
                )
            )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="差异分析结果",
            subtitle=f"已完成 {len(report.metadata.get('comparisons', []))} 个比较，共纳入 {report.metadata.get('sample_count', 0)} 个样本",
            dl_extras=[("csv_urls", None, "差异结果表")],
            zip_name="差异分析结果.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"火山图分析完成，生成 {len(png_urls)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("Volcano task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=float((_get_task_state(task_id) or {}).get("progress") or 0), stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/volcano/run", methods=["POST"])
def run_volcano():
    try:
        data = request.get_json() or {}
        module_name = "volcano"
        config = _volcano_config(data)
        input_mode = config["input_mode"]
        comparisons = None if config["comparisons"] == "all-pairs" else config["comparisons"]
        group_prefix = config["group_prefix"]
        data_dir = ""
        expression_path = ""
        if input_mode == "expression":
            expression_path = _transcriptome_path_from_request(data, "expression_path", "transcriptome_path", "profile_path", "datapoint_path") or ""
            if not expression_path:
                raise ValidationError(message="请选择转录组表达数据。")
            VolcanoService.prepare_expression_input(expression_path, group_prefix=group_prefix,
                selected_expression_groups=config["selected_expression_groups"], selected_expression_samples=config["selected_expression_samples"],
                comparisons=comparisons, validate=True)
        else:
            data_dir = str(data.get("data_dir") or "").strip() or _resolve_project_cached_usage_path(data, preferred="volcano")
            if not data_dir:
                raise ValidationError(message="请选择 V/J 使用分析结果。")
            VolcanoService.prepare_usage_inputs(data_dir, selected_categories=config["selected_categories"],
                selected_samples=config["selected_samples"], comparisons=comparisons, validate_comparisons=True)
        pvalue_threshold = config["pvalue_threshold"]
        logfc_cutoff = config["logfc_cutoff"] if input_mode == "expression" else 1.0
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(project_id=project_id, module_name=module_name,
            input_paths=[{"asset_type": "transcriptome" if input_mode == "expression" else "cached_usage",
                          "path": expression_path or data_dir}], config_json=config)
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_volcano_task, task_id,
            results_root=_resolve_results_root(),
            data_dir=data_dir,
            input_mode=input_mode,
            expression_path=expression_path,
            group_prefix=group_prefix,
            comparisons=comparisons,
            selected_expression_groups=config.get("selected_expression_groups"), selected_expression_samples=config.get("selected_expression_samples"),
            selected_categories=config.get("selected_categories"), selected_samples=config.get("selected_samples"),
            output_name=str(data.get("output_name") or "").strip() or None,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except (ValueError, TypeError, FileNotFoundError) as exc:
        return jsonify(success=False, message=str(exc)), 400
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- GO / KEGG Enrichment ----

@bp.route("/go-kegg-enrichment/sources", methods=["GET"])
def enrichment_sources():
    from flask_app.services.differential_artifacts import differential_candidates
    from flask_app.services.upstream_source_catalog import source_view_options, source_management_view
    options = source_view_options(request.args)
    candidates = differential_candidates(request.args.get('project_id', ''), request.args.get('asset_set', ''))
    return jsonify(source_management_view(candidates, **options) if options else {"success": True, "candidates": candidates})


@bp.route("/go-kegg-enrichment/inspect", methods=["POST"])
def inspect_go_kegg_enrichment():
    try:
        data = request.get_json() or {}
        expression_path = _transcriptome_path_from_request(
            data,
            "expression_path",
            "transcriptome_path",
            "profile_path",
            "datapoint_path",
        ) or ""
        if not expression_path:
            raise ValidationError(message="expression_path is required", details={"field": "expression_path"})
        group_prefix = str(data.get("group_prefix") or "tpm_").strip()
        inspect = GoKeggEnrichmentService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)
        return jsonify({"success": True, **inspect})
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error inspecting GO/KEGG inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_go_kegg_enrichment_task(
    task_id: str,
    *,
    results_root: Path,
    expression_path: str,
    deg_directory: Optional[str] = None,
    differential_metadata: Optional[Dict[str, Any]] = None,
    group_prefix: str = "tpm_",
    comparisons: Optional[List[List[str]]] = None,
    selected_expression_groups=None,
    selected_expression_samples=None,
    pvalue_threshold: float = 0.05,
    logfc_cutoff: float = 1.0,
    enrich_pvalue_cutoff: float = 0.05,
    p_adjust_method: str = "BH",
    show_category: int = 10,
    simplify_go: bool = False,
    do_gsea: bool = True,
    output_name: Optional[str] = None,
    module_name: str = "go-kegg-enrichment",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 4, "GO/KEGG", "读取前置差异表达结果" if deg_directory else "读取表达矩阵", {"module": module_name})
        service = GoKeggEnrichmentService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            expression_path=expression_path,
            deg_directory=deg_directory,
            differential_metadata=differential_metadata,
            group_prefix=group_prefix,
            comparisons=comparisons,
            selected_expression_groups=selected_expression_groups, selected_expression_samples=selected_expression_samples,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            enrich_pvalue_cutoff=enrich_pvalue_cutoff,
            p_adjust_method=p_adjust_method,
            show_category=show_category,
            simplify_go=simplify_go,
            do_gsea=do_gsea,
            output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            ),
        )

        def _url(path_value: str) -> str:
            path = Path(path_value)
            rel = path.relative_to(report.output_base)
            return f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}"

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": [_url(p) for p in report.png_paths],
            "csv_urls": [_url(p) for p in report.csv_paths],
            "log_url": _url(report.log_path),
            "zip_url": _url(report.zip_path),
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="基因功能与通路富集结果",
            subtitle=f"{'复用差异表达结果' if report.metadata.get('reused_differential_results') else '表达矩阵差异与富集'}；共 {len(report.metadata.get('comparisons', []))} 个比较",
            dl_extras=[("csv_urls", None, "分析结果表"), ("log_url", "go_kegg_enrichment.log", "计算日志")],
            zip_name="go_kegg_enrichment_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"GO/KEGG 富集分析完成，生成 {len(report.csv_paths)} 个表格和 {len(report.png_paths)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("GO/KEGG task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=float((_get_task_state(task_id) or {}).get("progress") or 0), stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


def _go_kegg_request(data, *, validate=False):
    source = None
    if data.get("input_mode") == "deg" or data.get("upstream_artifact_id"):
        from flask_app.services.differential_artifacts import resolve_differential_input
        source = resolve_differential_input(data)
        expression_path = ""
        config = {"input_mode": "deg", "upstream_artifact_id": source["id"], "differential_metadata": source["metadata"]}
    else:
        if data.get("input_mode") not in (None, "", "expression"):
            raise ValidationError(message="请选择有效的富集分析输入方式。")
        expression_path = _transcriptome_path_from_request(data, "expression_path", "transcriptome_path", "profile_path", "datapoint_path") or ""
        if not expression_path:
            raise ValidationError(message="请选择转录组表达矩阵或已完成的差异表达结果。")
        config = _volcano_config({**data, "input_mode": "expression"})
    try:
        cutoff = float(data.get("enrich_pvalue_cutoff") if data.get("enrich_pvalue_cutoff") is not None else 0.05)
        count_value = data.get("show_category") if data.get("show_category") is not None else 10
        count = int(count_value)
        if isinstance(count_value, float) and count_value != count:
            raise ValueError()
    except (TypeError, ValueError):
        raise ValidationError(message="富集阈值必须为有效数字，展示条目数必须为正整数。")
    method = str(data.get("p_adjust_method") or "BH").strip()
    if not math.isfinite(cutoff) or not 0 < cutoff <= 1 or count < 1:
        raise ValidationError(message="富集阈值需大于 0 且不超过 1，展示条目数至少为 1。")
    if method not in {"none", "BH", "BY", "holm", "bonferroni", "hochberg", "hommel", "fdr"}:
        raise ValidationError(message="请选择有效的多重检验校正方法。")
    config.update(enrich_pvalue_cutoff=cutoff, p_adjust_method=method, show_category=count,
        simplify_go=_as_bool(data.get("simplify_go"), False), do_gsea=_as_bool(data.get("do_gsea"), True))
    if validate:
        if source:
            GoKeggEnrichmentService.inspect_differential_input(Path(source["path"]), do_gsea=config["do_gsea"])
        else:
            VolcanoService.prepare_expression_input(expression_path, group_prefix=config["group_prefix"],
                selected_expression_groups=config["selected_expression_groups"], selected_expression_samples=config["selected_expression_samples"],
                comparisons=None if config["comparisons"] == "all-pairs" else config["comparisons"], validate=True)
    paths = ([{"asset_type": "differential_expression", "path": str(Path(source["path"]) / item["relative_path"])} for item in source["files"]]
             if source else [{"asset_type": "transcriptome", "path": expression_path}])
    cache = _build_script_cache_context(project_id=str(data.get("project_id") or "").strip() or None,
        module_name="go-kegg-enrichment", input_paths=paths, config_json=config)
    return source, expression_path, config, cache


@bp.route("/go-kegg-enrichment/run", methods=["POST"])
def run_go_kegg_enrichment():
    try:
        data = request.get_json() or {}
        module_name = "go-kegg-enrichment"
        source, expression_path, config, cache_context = _go_kegg_request(data, validate=True)
        project_id = str(data.get("project_id") or "").strip() or None
        output_name = str(data.get("output_name") or "").strip() or None
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)
        _script_executor.submit(_run_go_kegg_enrichment_task, task_id,
            results_root=_resolve_results_root(), expression_path=expression_path,
            deg_directory=source["path"] if source else None, differential_metadata=source["metadata"] if source else None,
            group_prefix=config.get("group_prefix", "tpm_"),
            comparisons=None if config.get("comparisons", "all-pairs") == "all-pairs" else config["comparisons"],
            selected_expression_groups=config.get("selected_expression_groups"), selected_expression_samples=config.get("selected_expression_samples"),
            pvalue_threshold=config.get("pvalue_threshold", 0.05), logfc_cutoff=config.get("logfc_cutoff", 1),
            enrich_pvalue_cutoff=config["enrich_pvalue_cutoff"], p_adjust_method=config["p_adjust_method"],
            show_category=config["show_category"], simplify_go=config["simplify_go"], do_gsea=config["do_gsea"],
            output_name=output_name, module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None)
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except (ValueError, TypeError, FileNotFoundError) as exc:
        return jsonify(success=False, message=str(exc)), 400
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- UMAPin Analysis ----

def _umapin_config(data):
    selections = {}
    for field in ("selected_categories", "selected_samples"):
        if field in data and data[field] is not None:
            if not isinstance(data[field], list):
                raise ValidationError(message="分组及样本选择必须是列表。", details={"field": field})
            selections[field] = list(dict.fromkeys(str(v).strip() for v in data[field] if str(v).strip()))
        else:
            selections[field] = None
    fdr = data.get("do_fdr", False)
    if isinstance(fdr, str):
        if fdr.lower() not in {"true", "false", "1", "0"}:
            raise ValidationError(message="FDR 校正开关格式无效。")
        fdr = fdr.lower() in {"true", "1"}
    return {"param_begin": str(data.get("param_begin") or "").strip(),
        "param_over": str(data.get("param_over") or "").strip(),
        "category_col": str(data.get("category_col") or "Category").strip(),
        "sample_column": str(data.get("sample_column") or "").strip(),
        "n_neighbors": int(data.get("n_neighbors", 6)), "min_dist": float(data.get("min_dist", 0.01)),
        "n_epochs": int(data.get("n_epochs", 100)), "do_fdr": bool(fdr),
        "output_name": str(data.get("output_name") or "umapin").strip(), **selections}


@bp.route("/umapin/inspect", methods=["POST"])
def inspect_umapin():
    try:
        data = request.get_json() or {}
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        if not data_path:
            base_path = str(data.get("base_path") or "").strip()
            if base_path:
                data_path = base_path
            else:
                raise ValidationError(message="请选择 V/J 使用数据或对应的分析缓存。", details={"field": "data_path"})

        dp = Path(data_path)
        if not dp.exists():
            raise ValidationError(message="未找到所选 V/J 使用数据，请重新选择。", details={"data_path": data_path})

        prepared = UmapinService.prepare_input(data_path=str(dp),
            category_col=str(data.get("category_col") or "Category"), sample_column=str(data.get("sample_column") or ""),
            validate_sample_count=False)
        frame, samples = prepared["data"], prepared["samples"]
        category = prepared["category_col"]
        groups = list(dict.fromkeys(frame[category]))
        return jsonify({"success": True, "data_path": str(prepared["source"].resolve()),
            "columns": frame.columns.tolist(), "column_count": len(frame.columns),
            "category_col": category, "sample_column": prepared["sample_column"], "sample_count": len(frame),
            "feature_columns": prepared["feature_candidates"], "pvalue_columns": UmapinService.pvalue_columns(frame.columns),
            "values": groups, "samples_by_value": {group: samples.loc[frame[category].eq(group)].tolist() for group in groups},
            "suggested_param_begin": prepared["feature_candidates"][0] if prepared["feature_candidates"] else "",
            "suggested_param_over": prepared["feature_candidates"][-1] if prepared["feature_candidates"] else ""})
    except (ValidationError, ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "error": getattr(exc, "error_code", "INPUT_VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        logger.error("Error inspecting UMAPin inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_umapin_task(
    task_id: str,
    *,
    results_root: Path,
    data_path: str,
    param_begin: str,
    param_over: str,
    category_col: str = "Category",
    n_neighbors: int = 6,
    min_dist: float = 0.01,
    do_fdr: bool = False,
    n_epochs: int = 100, sample_column: str = "",
    selected_categories=None, selected_samples=None, output_name: str = "umapin",
    module_name: str = "umapin",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "核对特征输入", "正在核对所选特征表与样本。", {"module": module_name})

        dp = data_path

        service = UmapinService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            data_path=dp,
            param_begin=param_begin,
            param_over=param_over,
            category_col=category_col,
            n_neighbors=n_neighbors,
            min_dist=min_dist,
            do_fdr=do_fdr, n_epochs=n_epochs, sample_column=sample_column,
            selected_categories=selected_categories, selected_samples=selected_samples, output_name=output_name,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            )
        )

        png_urls = []
        for p in report.png_paths:
            rel = Path(p).relative_to(report.output_base)
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
        csv_urls = []
        for c in report.csv_paths:
            rel = Path(c).relative_to(report.output_base)
            csv_urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": png_urls,
            "csv_urls": csv_urls,
            "metadata": report.metadata,
        }
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="UMAP 特征降维结果",
            subtitle="特征数：" + str(report.metadata.get("feature_count", "")) + "；分组：" + "、".join(report.metadata.get("unique_groups", [])),
            dl_extras=[("csv_urls", None, "降维坐标表")],
            zip_name="特征降维结果.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"特征降维完成，{len(png_urls)} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("UMAPin task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=(_get_task_state(task_id) or {}).get("progress", 0.0), stage="分析失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/umapin/run", methods=["POST"])
def run_umapin():
    try:
        data = request.get_json() or {}
        module_name = "umapin"
        data_path = str(data.get("data_path") or "").strip() or _resolve_project_cached_usage_path(data, preferred="umapin")
        if not data_path:
            raise ValidationError(message="请选择 V/J 使用数据或对应的分析缓存。", details={"field": "data_path"})

        config = _umapin_config(data)
        UmapinService.prepare_input(data_path=data_path, **{key: value for key, value in config.items()
            if key in {"param_begin", "param_over", "category_col", "sample_column", "selected_categories", "selected_samples"}})
        if config["n_neighbors"] < 2 or not 0 <= config["min_dist"] <= 1 or config["n_epochs"] < 1:
            raise ValidationError(message="UMAP 参数超出有效范围。")
        project_id = str(data.get("project_id") or "").strip() or None
        cache_context = _build_script_cache_context(project_id=project_id, module_name=module_name,
            input_paths=[{"asset_type": "cached_usage", "path": data_path}], config_json=config)
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_umapin_task, task_id,
            results_root=_resolve_results_root(),
            data_path=data_path,
            **config,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except (ValidationError, ValueError, FileNotFoundError) as exc:
        return jsonify({"success": False, "error": getattr(exc, "error_code", "INPUT_VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


# ---- Machine Learning Analysis ----

def _suggest_ml_label(columns: List[str]) -> str:
    preferred = ["group_type", "timepoint", "Category", "category", "group", "disease", "therapy"]
    lower_map = {str(col).lower(): col for col in columns}
    for key in preferred:
        if key.lower() in lower_map:
            return lower_map[key.lower()]
    non_sample = [col for col in columns if str(col).strip().lower() not in {"sample", "sample_id", "id"}]
    return non_sample[0] if non_sample else (columns[0] if columns else "")


def _suggest_ml_sample(columns: List[str]) -> str:
    lower_map = {str(col).lower(): col for col in columns}
    for key in ("sample", "sample_id", "sampleid", "id"):
        if key in lower_map:
            return lower_map[key]
    return columns[0] if columns else "Sample"


def _list_payload(value: Any) -> List[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def _ml_profile_feature_candidates(
    profile_file: Path,
    columns: List[str],
    *,
    sample_col: str,
    label_col: str,
    filter_col: str = "",
) -> List[str]:
    excluded = {sample_col, label_col}
    if filter_col:
        excluded.add(filter_col)
    try:
        preview_df = _robust_read_csv(profile_file, nrows=200, low_memory=False)
    except TypeError:
        preview_df = _robust_read_csv(profile_file, nrows=200)
    except Exception:
        preview_df = pd.DataFrame(columns=columns)
    candidates: List[str] = []
    for col in columns:
        if col in excluded:
            continue
        if col in preview_df.columns:
            numeric = pd.to_numeric(preview_df[col], errors="coerce")
            if not numeric.notna().any():
                continue
        candidates.append(col)
    return candidates


def _ml_usage_feature_range(
    *,
    profile_path: str,
    usage_path: str,
    sample_col: str,
    param_begin: str,
    param_over: str,
    batch_field=None, group_sample_identity="sample",
    selected_group_values=None, selected_samples=None, selected_samples_by_group=None,
) -> List[str]:
    profile_file = Path(profile_path)
    profile_df = _robust_read_csv(profile_file, low_memory=False, dtype=str, keep_default_na=False)
    sample_source_col = sample_col if sample_col in profile_df.columns else _suggest_ml_sample(profile_df.columns.tolist())
    if batch_field:
        from flask_app.services.pep_analysis_service import _batch_sample_identity
        if batch_field not in profile_df.columns:
            raise ValidationError(message="所选批次字段不存在", details={"field": "batch_field"})
        profile_samples = set(profile_df.apply(lambda row: _batch_sample_identity(str(row[batch_field]).strip(), str(row[sample_source_col]).strip()), axis=1))
    else:
        profile_samples = set(profile_df[sample_source_col].dropna().astype(str).str.strip())
    candidates = MLAnalysisService.collect_usage_feature_candidates(
        profile_samples=profile_samples,
        usage_path=usage_path,
        sample_col=sample_source_col,
    )
    values = [str(item.get("value") or "").strip() for item in candidates if str(item.get("value") or "").strip()]
    if not values:
        return []
    if not param_begin or not param_over:
        return values
    if param_begin not in values or param_over not in values:
        raise ValidationError(
            message="VJ usage param_begin or param_over not found in usage features",
            details={"param_begin": param_begin, "param_over": param_over},
        )
    start = values.index(param_begin)
    end = values.index(param_over)
    if start > end:
        start, end = end, start
    return values[start:end + 1]


def _normalize_ml_mode(value: Any) -> str:
    mode = str(value or "profile").strip().lower().replace("-", "_").replace("+", "_")
    if mode in {"vj", "vj_usage", "usage"}:
        return "vj"
    if mode in {"profile_vj", "profile_usage", "profile_vj_usage"}:
        return "profile_vj"
    return "profile"


def _ml_selection_parameters(data):
    return {
        "batch_field": str(data.get("batch_field") or "").strip() or None,
        "group_sample_identity": _group_sample_identity_from_request(data),
        "selected_group_values": _selected_group_values_from_request(data),
        "selected_samples": _selected_samples_from_request(data),
        "selected_samples_by_group": _selected_samples_by_group_from_request(data),
    }


def _ml_cache_config(data, profile_path, usage_path):
    mode = _normalize_ml_mode(data.get("mode"))
    features = _list_payload(data.get("feature_cols")) if mode != "profile" else []
    usage_features = _list_payload(data.get("usage_feature_cols")) if mode != "profile" else []
    begin = str(data.get("param_begin") or "").strip()
    end = str(data.get("param_over") or "").strip()
    if mode == "vj" and begin and end:
        usage_features = _ml_usage_feature_range(
            profile_path=profile_path, usage_path=usage_path,
            sample_col=str(data.get("sample_col") or "Sample"), param_begin=begin, param_over=end,
            **_ml_selection_parameters(data),
        )
    raw_stability = data.get("use_stability_selection", True)
    if isinstance(raw_stability, bool):
        stability = raw_stability
    elif str(raw_stability).strip().lower() in {"1", "true", "yes", "on", "0", "false", "no", "off"}:
        stability = str(raw_stability).strip().lower() in {"1", "true", "yes", "on"}
    else:
        raise ValidationError(message="稳定特征筛选开关格式无效", details={"field": "use_stability_selection"})
    return {
        "mode": mode, "data_mode": mode,
        "label_col": str(data.get("label_col") or "").strip(),
        "sample_col": str(data.get("sample_col") or "Sample").strip() or "Sample",
        "group_col": str(data.get("group_col") or "").strip(),
        "param_begin": begin, "param_over": end,
        "filter_col": str(data.get("filter_col") or "").strip(),
        "filter_value": str(data.get("filter_value") or "").strip(),
        **_ml_selection_parameters(data),
        **({"feature_cols": features} if mode != "profile" else {}),
        "usage_feature_cols": usage_features,
        "model_keys": _list_payload(data.get("model_keys")) or ["random_forest"],
        "custom_threshold": float(0.003 if data.get("custom_threshold") in (None, "") else data["custom_threshold"]),
        "cv_splits": int(data.get("cv_splits") or 3),
        "use_stability_selection": stability,
        "stability_threshold": float(data.get("stability_threshold") or 0.60),
        "stability_splits": int(data.get("stability_splits") or 5),
        "stability_min_features": int(data.get("stability_min_features") or 5),
    }


@bp.route("/ml-analysis/inspect", methods=["POST"])
def inspect_ml_analysis():
    try:
        data = request.get_json() or {}
        project_id = str(data.get("project_id") or "").strip()
        mode = _normalize_ml_mode(data.get("mode"))
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path")
        if not profile_path:
            raise ValidationError(message="请选择样本指标表。", details={"field": "profile_path"})

        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise ValidationError(message="样本指标表文件不存在，请重新选择。", details={"profile_path": profile_path})

        columns = _read_table_columns(profile_file)
        if not columns:
            raise ValidationError(message="样本指标表未读取到可用列，请检查文件内容。", details={"profile_path": profile_path})

        usage_path = str(data.get("usage_path") or "").strip()
        if mode in {"vj", "profile_vj"}:
            usage_path = usage_path or _resolve_project_cached_usage_path(data, preferred="umapin")
        cached_usage_assets = _collect_project_cached_usage_assets(project_id) if project_id else []
        suggestions = _suggest_profile_ranges(columns)
        label_col = str(data.get("label_col") or "").strip() or _suggest_ml_label(columns)
        sample_col = str(data.get("sample_col") or "").strip() or _suggest_ml_sample(columns)
        filter_col = str(data.get("filter_col") or "").strip()
        selection = _ml_selection_parameters(data)
        prepared, sample_col, _ = MLAnalysisService.prepare_profile(
            profile_path=profile_path, sample_col=sample_col, label_col=label_col,
            group_col=str(data.get("group_col") or "").strip(),
            filter_col=filter_col, filter_value=str(data.get("filter_value") or "").strip(), **selection,
        )

        filter_candidates = [
            col for col in columns
            if col not in {sample_col}
            and len(col) < 80
        ]
        profile_feature_candidates = _ml_profile_feature_candidates(
            profile_file,
            columns,
            sample_col=sample_col,
            label_col=label_col,
            filter_col=filter_col,
        )
        profile_feature_candidates = [col for col in profile_feature_candidates
                                      if col not in {selection["batch_field"], data.get("group_col")}]
        usage_feature_candidates: List[Dict[str, str]] = []
        if usage_path:
            try:
                sample_source_col = sample_col
                profile_samples = set(prepared[sample_col])
                usage_feature_candidates = MLAnalysisService.collect_usage_feature_candidates(
                    profile_samples=profile_samples,
                    usage_path=usage_path,
                    sample_col=sample_source_col,
                )
            except (OSError, ValueError) as exc:
                raise ValidationError(
                    message="无法读取 V/J 候选特征，请检查来源文件后重新检查。",
                    details={"field": "usage_path", "reason": str(exc)},
                ) from exc

        return jsonify({
            "success": True,
            "mode": mode,
            "profile_path": str(profile_file.resolve()),
            "usage_path": usage_path,
            "columns": columns,
            "column_count": len(columns),
            "sample_count": len(prepared),
            "sample_ids": prepared[sample_col].tolist(),
            "batch_field": selection["batch_field"],
            "sample_col": sample_col,
            "label_col": label_col,
            "filter_candidates": filter_candidates,
            "profile_feature_candidates": profile_feature_candidates,
            "usage_feature_candidates": usage_feature_candidates,
            "suggested_param_begin": (suggestions.get("param_begin") if suggestions.get("param_begin") in profile_feature_candidates else (profile_feature_candidates[0] if profile_feature_candidates else "")),
            "suggested_param_over": (suggestions.get("param_over") if suggestions.get("param_over") in profile_feature_candidates else (profile_feature_candidates[-1] if profile_feature_candidates else "")),
            "cached_usage_assets": cached_usage_assets[:20],
        })
    except (ValidationError, ValueError) as exc:
        return jsonify({"success": False, "error": getattr(exc, "error_code", "VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        logger.error("Error inspecting ML inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


def _run_ml_analysis_task(
    task_id: str,
    *,
    results_root: Path,
    profile_path: str,
    mode: str,
    label_col: str,
    sample_col: str,
    group_col: str,
    param_begin: str,
    param_over: str,
    usage_path: str,
    filter_col: str,
    filter_value: str,
    feature_cols: List[str],
    usage_feature_cols: List[str],
    model_keys: List[str],
    custom_threshold: float,
    cv_splits: int,
    use_stability_selection: bool,
    stability_threshold: float,
    stability_splits: int,
    stability_min_features: int,
    batch_field: Optional[str] = None,
    group_sample_identity: str = "sample",
    selected_group_values=None, selected_samples=None, selected_samples_by_group=None,
    output_name: Optional[str] = None,
    module_name: str = "ml-analysis",
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 5, "机器学习分析", "正在读取样本指标、标签与批次身份", {"module": module_name})

        service = MLAnalysisService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))
        report = service.generate_report(
            profile_path=profile_path,
            mode=mode, output_name=output_name,
            label_col=label_col,
            sample_col=sample_col,
            group_col=group_col, batch_field=batch_field, group_sample_identity=group_sample_identity,
            selected_group_values=selected_group_values, selected_samples=selected_samples,
            selected_samples_by_group=selected_samples_by_group,
            param_begin=param_begin,
            param_over=param_over,
            usage_path=usage_path,
            filter_col=filter_col,
            filter_value=filter_value,
            feature_cols=feature_cols,
            usage_feature_cols=usage_feature_cols,
            model_keys=model_keys,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            use_stability_selection=use_stability_selection,
            stability_threshold=stability_threshold,
            stability_splits=stability_splits,
            stability_min_features=stability_min_features,
            progress_callback=lambda progress, stage, detail, meta=None: _record_stage(
                task_id, float(progress or 0.0), stage, detail,
                {"module": module_name, **(meta or {})}
            ),
        )

        def _urls(paths: List[str]) -> List[str]:
            urls: List[str] = []
            for path in paths:
                rel = Path(path).relative_to(report.output_base)
                urls.append(f"/api/script-hub/results/{report.job_id}/{rel.as_posix()}")
            return urls

        result = {
            "module": module_name,
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "png_urls": _urls(report.png_paths),
            "csv_urls": _urls(report.csv_paths),
            "text_urls": _urls(report.text_paths),
            "metadata": report.metadata,
        }
        data_mode = str(report.metadata.get("data_mode") or report.metadata.get("mode") or mode)
        result["viewer_items"] = [
            {
                "kind": "image",
                "url": url,
                "title": url.rsplit("/", 1)[-1],
                "category": data_mode,
                "data_mode": data_mode,
            }
            for url in result["png_urls"]
        ]
        report.metadata["viewer_items"] = result["viewer_items"]
        subtitle = (
            ("输出名称：" + str(report.metadata.get("output_name")) + " | " if report.metadata.get("output_name") else "") + "数据模式：" + {"profile": "样本指标", "vj": "V/J 特征", "profile_vj": "联合特征"}.get(str(report.metadata.get("mode", "")), "机器学习")
            + " | 分类标签：" + str(report.metadata.get("label_col", ""))
            + " | 特征数：" + str(report.metadata.get("selected_feature_number", ""))
        )
        _build_and_save_viewer(
            report.output_base,
            result,
            report.metadata,
            title="机器学习分析结果",
            subtitle=subtitle,
            dl_extras=[("csv_urls", None, "数据表"), ("text_urls", None, "分析说明")],
        )
        _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="机器学习分析结果",
            subtitle=subtitle,
            dl_extras=[("csv_urls", None, "数据表"), ("text_urls", None, "分析说明")],
            zip_name="ml_analysis_results.zip",
        )

        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name=module_name,
            detail=f"机器学习分析完成，生成 {len(result['png_urls'])} 张图",
            result=result,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("ML analysis task failed: %s", exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(task_id, status="failed", progress=float((_get_task_state(task_id) or {}).get("progress") or 0), stage="失败",
                        detail=str(exc), meta={"phase": "failed", "module": module_name},
                        history=history[-80:])


@bp.route("/ml-analysis/run", methods=["POST"])
def run_ml_analysis():
    try:
        data = request.get_json() or {}
        module_name = "ml-analysis"
        profile_path = _profile_path_from_request(data, "profile_path", "datapoint_path") or ""
        if not profile_path:
            raise ValidationError(message="请选择样本指标表。", details={"field": "profile_path"})

        mode = _normalize_ml_mode(data.get("mode"))
        usage_path = str(data.get("usage_path") or "").strip()
        if mode in {"vj", "profile_vj"}:
            usage_path = usage_path or _resolve_project_cached_usage_path(data, preferred="umapin")
            if not usage_path:
                raise ValidationError(message="请选择 V/J 基因使用特征来源。", details={"field": "usage_path"})

        label_col = str(data.get("label_col") or "").strip()
        if not label_col:
            raise ValidationError(message="请选择分类标签列。", details={"field": "label_col"})

        sample_col = str(data.get("sample_col") or "Sample").strip() or "Sample"
        group_col = str(data.get("group_col") or "").strip()
        if group_col:
            profile_columns = _read_table_columns(Path(profile_path))
            if group_col not in profile_columns:
                raise ValidationError(
                    message="受试者分组列不存在于样本指标表中",
                    details={"field": "group_col", "value": group_col},
                )
            if group_col in {sample_col, label_col}:
                raise ValidationError(
                    message="受试者分组列必须与样本编号列和分类标签列不同",
                    details={"field": "group_col"},
                )
        selection = _ml_selection_parameters(data)
        _validate_selected_samples_against_group_values(data)
        MLAnalysisService.prepare_profile(
            profile_path=profile_path, sample_col=sample_col, label_col=label_col,
            group_col=group_col, filter_col=str(data.get("filter_col") or "").strip(),
            filter_value=str(data.get("filter_value") or "").strip(), **selection,
        )
        param_begin = str(data.get("param_begin") or "").strip()
        param_over = str(data.get("param_over") or "").strip()
        filter_col = str(data.get("filter_col") or "").strip()
        filter_value = str(data.get("filter_value") or "").strip()
        feature_cols = _list_payload(data.get("feature_cols"))
        usage_feature_cols = _list_payload(data.get("usage_feature_cols"))
        model_keys = _list_payload(data.get("model_keys")) or ["random_forest"]
        unsupported_models = sorted(set(model_keys) - set(MLAnalysisService.SUPPORTED_ML_MODELS))
        if unsupported_models:
            raise ValidationError(
                message="包含不支持的机器学习模型",
                details={"field": "model_keys", "values": unsupported_models},
            )
        if mode == "profile":
            feature_cols = []
            if not param_begin or not param_over:
                raise ValidationError(message="请选择样本指标的起始列和结束列。", details={"fields": ["param_begin", "param_over"]})
            usage_feature_cols = []
        if mode == "profile_vj" and (not param_begin or not param_over):
            raise ValidationError(message="请选择样本指标的起始列和结束列。", details={"fields": ["param_begin", "param_over"]})
        if mode == "vj":
            if param_begin and param_over:
                usage_feature_cols = _ml_usage_feature_range(
                    profile_path=profile_path,
                    usage_path=usage_path,
                    sample_col=sample_col,
                    param_begin=param_begin,
                    param_over=param_over, **selection,
                )
                if not usage_feature_cols:
                    raise ValidationError(message="所选指标范围内未找到可用 V/J 特征，请重新选择。", details={"field": "param_begin,param_over"})
        custom_threshold = float(0.003 if data.get("custom_threshold") in (None, "") else data["custom_threshold"])
        cv_splits = int(data.get("cv_splits") or 3)
        raw_stability = data.get("use_stability_selection", True)
        if isinstance(raw_stability, bool):
            use_stability_selection = raw_stability
        elif str(raw_stability).strip().lower() in {"1", "true", "yes", "on"}:
            use_stability_selection = True
        elif str(raw_stability).strip().lower() in {"0", "false", "no", "off"}:
            use_stability_selection = False
        else:
            raise ValidationError(
                message="稳定特征筛选开关格式无效",
                details={"field": "use_stability_selection"},
            )
        try:
            stability_threshold = float(data.get("stability_threshold") or 0.60)
            stability_splits = int(data.get("stability_splits") or 5)
            stability_min_features = int(data.get("stability_min_features") or 5)
        except (TypeError, ValueError) as exc:
            raise ValidationError(
                message="稳定性筛选参数必须为有效数字",
                details={"fields": ["stability_threshold", "stability_splits", "stability_min_features"]},
            ) from exc
        if not 0 < stability_threshold <= 1:
            raise ValidationError(
                message="稳定特征入选频率阈值必须在 (0, 1] 范围内",
                details={"field": "stability_threshold"},
            )
        if stability_splits < 2:
            raise ValidationError(
                message="稳定性筛选折数至少为 2",
                details={"field": "stability_splits"},
            )
        if stability_min_features < 1:
            raise ValidationError(
                message="每类数据至少保留 1 个稳定特征",
                details={"field": "stability_min_features"},
            )
        project_id = str(data.get("project_id") or "").strip() or None

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "profile", "path": profile_path},
                *([{"asset_type": "cached_usage", "path": usage_path}] if usage_path else []),
            ],
            config_json=_ml_cache_config(data, profile_path, usage_path),
        )
        if not _force_rerun_requested(data):
            reused_response = _try_reuse_script_result(cache_context, module_name)
            if reused_response:
                return jsonify(reused_response)

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(task_id, status="queued", progress=0.0, stage="排队中",
                        detail="任务已创建", meta={"phase": "queued", "module": module_name},
                        history=[_history_entry(0.0, "排队中", "任务已创建", {"phase": "queued", "module": module_name})],
                        **cache_context)

        _script_executor.submit(
            _run_ml_analysis_task, task_id,
            results_root=_resolve_results_root(),
            profile_path=profile_path,
            mode=mode,
            label_col=label_col,
            sample_col=sample_col,
            group_col=group_col, **selection,
            param_begin=param_begin,
            param_over=param_over,
            usage_path=usage_path,
            filter_col=filter_col,
            filter_value=filter_value,
            feature_cols=feature_cols,
            usage_feature_cols=usage_feature_cols,
            model_keys=model_keys,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            use_stability_selection=use_stability_selection,
            stability_threshold=stability_threshold,
            stability_splits=stability_splits,
            stability_min_features=stability_min_features,
            output_name=str(data.get("output_name") or "").strip() or None,
            module_name=module_name,
            app_context_app=current_app._get_current_object() if project_id else None,
        )
        return jsonify({"success": True, "task_id": task_id, "status_url": f"/api/script-hub/task/{task_id}", "analysis_signature": cache_context.get("analysis_signature", "")})
    except (ValidationError, ValueError) as exc:
        return jsonify({"success": False, "error": getattr(exc, "error_code", "VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        logger.error("Error running ML analysis: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500

def _mait_selection_parameters(data):
    return {
        "group_field": str(data.get("group_field") or "__all_samples__").strip() or "__all_samples__",
        "group_order": str(data.get("group_order") or "").strip() or None,
        "batch_field": str(data.get("batch_field") or "").strip() or None,
        "selected_group_values": _selected_group_values_from_request(data),
        "selected_samples": _selected_samples_from_request(data),
        "selected_samples_by_group": _selected_samples_by_group_from_request(data),
        "group_sample_identity": _group_sample_identity_from_request(data),
    }


def _mait_profile_frame(profile_path):
    if not profile_path:
        return pd.DataFrame()
    return _robust_read_csv(PathAccessService.validate_read_path(profile_path), dtype=str, keep_default_na=False)


def _prepare_mait_selection(tra_df, profile_df, params):
    return MaitNktService.prepare_inputs(
        tra_df=tra_df, profile_df=profile_df, group_field=params["group_field"],
        batch_field=params["batch_field"], selected_group_values=params["selected_group_values"],
        selected_samples=params["selected_samples"], selected_samples_by_group=params["selected_samples_by_group"],
        group_sample_identity=params["group_sample_identity"],
    )


@bp.route("/mait-nkt/inspect", methods=["POST"])
def inspect_mait_nkt():
    try:
        data = request.get_json() or {}
        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path")

        # Resolve TRA data source
        tra_df = None
        resolved_tra_path = ""
        resolved_source_job_id = source_job_id
        resolved_source_kind = tra_source
        resolved_output_base = ""
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
            resolved_source_kind = "pep_analysis_resolved_path"
            tra_df = _robust_read_csv(Path(resolved_tra_path), dtype=str, keep_default_na=False)
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)
            resolved_source_kind = str(resolved.get("source_kind") or "pep_analysis")
            resolved_output_base = str(resolved.get("output_base") or "")
            tra_df = _robust_read_csv(Path(resolved_tra_path), dtype=str, keep_default_na=False)
        elif tra_path:
            dp = Path(tra_path)
            if not dp.exists() or not dp.is_file():
                raise ValidationError(message="受体 α 链数据文件不存在。", details={"file_path": tra_path})
            resolved_tra_path = tra_path
            tra_df = _robust_read_csv(PathAccessService.validate_read_path(dp), dtype=str, keep_default_na=False)
        else:
            raise ValidationError(
                message="请提供 TRA CSV 文件路径或选择 PEP 共享分析结果",
                details={"tra_source": tra_source},
            )

        params = _mait_selection_parameters(data)
        tra_df = _normalize_mait_tra_dataframe(tra_df, resolved_tra_path or tra_source, params["batch_field"])
        profile_df = _mait_profile_frame(profile_path)
        matrix, _, _ = _prepare_mait_selection(tra_df, profile_df, params)

        profile_groups = {}
        if profile_path:
            profile_groups = {
                str(column): profile_df[column].dropna().astype(str).drop_duplicates().tolist()
                for column in profile_df.columns
                if str(column) != str(profile_df.columns[0])
            }

        # Detect sample columns
        sample_cols = []
        has_category_row = False
        if tra_df is not None and len(tra_df.columns) > 1:
            sample_cols = [str(c) for c in matrix.columns]
            if len(tra_df) >= 1:
                second_row = tra_df.iloc[0, 1:]
                if str(tra_df.iloc[0, 0]).strip() in {params["group_field"], "group", "category", "Category"} or _looks_like_category_row(second_row):
                    has_category_row = True

        return jsonify(_sanitize_nan({
            "success": True,
            "tra_source": tra_source,
            "resolved_tra_path": resolved_tra_path,
            "source_job_id": resolved_source_job_id,
            "source_kind": resolved_source_kind,
            "pep_output_base": resolved_output_base,
            "sample_columns": sample_cols,
            "sample_count": len(sample_cols),
            "has_category_row": has_category_row,
            "profile_groups": profile_groups,
            "batch_field": params["batch_field"] or "",
        }))
    except (ValidationError, ValueError) as exc:
        logger.warning("Validation error in inspect_mait_nkt: %s", str(exc))
        return jsonify({"success": False, "error": getattr(exc, "error_code", "VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        logger.error("Error inspecting MAIT/NKT inputs: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_INSPECT_ERROR", "message": str(exc)}), 500


@bp.route("/mait-nkt/run", methods=["POST"])
def run_mait_nkt():
    try:
        data = request.get_json() or {}
        module_name = "mait-nkt"

        tra_source = str(data.get("tra_source") or "upload").strip()
        tra_path = str(data.get("tra_path") or "").strip()
        source_job_id = str(data.get("source_job_id") or "").strip()
        profile_path = _profile_path_from_request(data, "profile_path") or ""
        params = _mait_selection_parameters(data)
        group_field = params["group_field"]
        group_order = params["group_order"]
        _validate_selected_samples_against_group_values(data)

        project_id = str(data.get("project_id") or "").strip() or None
        resolved_tra_path = tra_path
        resolved_source_job_id = source_job_id
        resolved_tra_df = None
        if tra_source == "pep_analysis" and tra_path and Path(tra_path).exists() and Path(tra_path).is_file():
            resolved_tra_path = str(PathAccessService.validate_read_path(tra_path))
            resolved_tra_df = _robust_read_csv(Path(resolved_tra_path), dtype=str, keep_default_na=False)
        elif tra_source == "pep_analysis":
            resolved = _resolve_pep_analysis_tra_source(data)
            resolved_tra_path = resolved["path"]
            resolved_source_job_id = str(resolved.get("source_job_id") or source_job_id)
            resolved_tra_df = _robust_read_csv(Path(resolved_tra_path), dtype=str, keep_default_na=False)
        elif resolved_tra_path:
            dp = Path(resolved_tra_path)
            if not dp.exists() or not dp.is_file():
                raise ValidationError(
                    message="MAIT/NKT 分析需要 TRA 链数据。当前选择的 TRA 文件不存在。",
                    details={"file_path": resolved_tra_path},
                )
            resolved_tra_df = _robust_read_csv(PathAccessService.validate_read_path(dp), dtype=str, keep_default_na=False)
        else:
            raise ValidationError(
                message="MAIT/NKT 分析需要 TRA 链数据。请选择包含 TRA 的 克隆共享结果，或手动上传 TRA CSV。",
                details={"tra_source": tra_source},
            )

        normalized_tra_df = _normalize_mait_tra_dataframe(resolved_tra_df, resolved_tra_path or tra_source, params["batch_field"])
        matrix, _, _ = _prepare_mait_selection(normalized_tra_df, _mait_profile_frame(profile_path), params)

        cache_context = _build_script_cache_context(
            project_id=project_id,
            module_name=module_name,
            input_paths=[
                {"asset_type": "tra", "path": resolved_tra_path} if tra_source == "upload" else {"asset_type": "pep_analysis_tra", "path": resolved_tra_path, "source_job_id": resolved_source_job_id},
                *([{"asset_type": "profile", "path": profile_path}] if profile_path else []),
            ],
            config_json={
                **params,
                "tra_source": tra_source,
                "source_job_id": resolved_source_job_id,
                "tra_sample_count": len(matrix.columns),
            },
        )
        if not _force_rerun_requested(data):
            cached = _try_reuse_script_result(cache_context, module_name)
            if cached:
                return jsonify(_sanitize_nan(cached))

        task_id = f"script_task_{uuid.uuid4().hex[:12]}"
        _set_task_state(
            task_id,
            status="queued",
            module=module_name,
            progress=0.0,
            stage="等待执行",
            detail="MAIT/NKT 分析任务已加入队列。",
            created_at=datetime.now().strftime("%H:%M:%S"),
            history=[_history_entry(0, "等待执行", "MAIT/NKT 分析任务已加入队列。")],
            **cache_context,
        )

        analysis_signature = cache_context.get("analysis_signature", "")

        _script_executor.submit(
            _run_mait_nkt_task,
            task_id,
            results_root=Path(current_app.config.get("RESULTS_FOLDER", str(RESULTS_DIR))),
            tra_source=tra_source,
            tra_path=resolved_tra_path,
            source_job_id=resolved_source_job_id,
            profile_path=profile_path,
            group_field=group_field,
            group_order=group_order,
            batch_field=params["batch_field"],
            selected_group_values=params["selected_group_values"],
            selected_samples=params["selected_samples"],
            selected_samples_by_group=params["selected_samples_by_group"],
            group_sample_identity=params["group_sample_identity"],
            project_id=project_id,
            app_context_app=current_app._get_current_object() if project_id else None,
        )

        return jsonify(_sanitize_nan({
            "success": True,
            "task_id": task_id,
            "status": "queued",
            "module": module_name,
            "status_url": f"/api/script-hub/task/{task_id}",
            "analysis_signature": analysis_signature,
        }))
    except (ValidationError, ValueError) as exc:
        logger.warning("Validation error in run_mait_nkt: %s", str(exc))
        return jsonify({"success": False, "error": getattr(exc, "error_code", "VALIDATION_ERROR"), "message": getattr(exc, "message", str(exc)), "details": getattr(exc, "details", {})}), 400
    except Exception as exc:
        logger.error("Error running MAIT/NKT analysis: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_RUN_ERROR", "message": str(exc)}), 500


def _run_mait_nkt_task(
    task_id: str,
    *,
    results_root: Path,
    tra_source: str,
    tra_path: str,
    source_job_id: str,
    profile_path: str,
    group_field: str,
    group_order: Optional[str],
    batch_field: Optional[str] = None,
    selected_group_values: Optional[Dict[str, List[str]]] = None,
    selected_samples: Optional[List[str]] = None,
    selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
    group_sample_identity: str = "sample",
    project_id: Optional[str] = None,
    app_context_app: Optional[Any] = None,
) -> None:
    try:
        _record_stage(task_id, 2, "读取输入", "正在读取受体 α 链数据。")
        tra_df = None
        resolved_tra_path = tra_path
        if tra_source == "pep_analysis":
            dp = Path(tra_path) if tra_path else None
            if dp and dp.exists() and dp.is_file():
                tra_df = _robust_read_csv(PathAccessService.validate_read_path(dp), dtype=str, keep_default_na=False)
                resolved_tra_path = str(dp)
            else:
                resolved = _resolve_pep_analysis_tra_source({
                    "project_id": project_id or "",
                    "source_job_id": source_job_id,
                })
                resolved_tra_path = resolved["path"]
                tra_df = _robust_read_csv(Path(resolved_tra_path), dtype=str, keep_default_na=False)
        else:
            dp = Path(tra_path)
            if not dp.exists():
                raise ValidationError(
                    message="MAIT/NKT 分析需要 TRA 链数据。当前选择的 TRA 文件不存在。",
                    details={"file_path": tra_path},
                )
            tra_df = _robust_read_csv(PathAccessService.validate_read_path(dp), dtype=str, keep_default_na=False)

        tra_df = _normalize_mait_tra_dataframe(tra_df, resolved_tra_path or tra_source, batch_field)

        _record_stage(task_id, 8, "准备分组", "正在按样本与批次匹配分组。")
        profile_df = _mait_profile_frame(profile_path)

        group_order_list = None
        if group_order:
            group_order_list = [x.strip() for x in group_order.split(",") if x.strip()]

        service = MaitNktService(output_parent=script_output_parent(task_id, results_root / _RESULT_DIR, app_context_app))

        def _progress(percent, stage, detail):
            _record_stage(task_id, percent, stage, detail)

        report = service.generate_report(
            tra_df=tra_df,
            profile_df=profile_df,
            group_field=group_field,
            group_order=group_order_list,
            batch_field=batch_field,
            selected_group_values=selected_group_values,
            selected_samples=selected_samples,
            selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
            progress_callback=_progress,
            job_id=task_id,
            datapoint_path=resolved_tra_path or tra_path,
        )

        # Build result URLs
        png_urls = []
        for png in report.png_paths:
            rel = Path(png).relative_to(report.output_base).as_posix()
            png_urls.append(f"/api/script-hub/results/{report.job_id}/{rel}")

        result = {
            "module": "mait-nkt",
            "job_id": report.job_id,
            "output_base": str(report.output_base),
            "viewer_url": f"/api/script-hub/results/{report.job_id}/viewer.html",
            "png_urls": png_urls,
            "csv_urls": [f"/api/script-hub/results/{report.job_id}/{quote(Path(path).relative_to(report.output_base).as_posix(), safe='/')}" for path in report.csv_paths],
            "zip_url": f"/api/script-hub/results/{report.job_id}/mait_nkt_results.zip",
            "metadata": report.metadata,
        }

        normalized = _normalize_script_result(
            result,
            report.output_base,
            report.metadata,
            title="MAIT/NKT 分析",
            subtitle="受体 α 链参考序列比对与分组结果",
            dl_extras=[("csv_urls", None, "样本指标数据表")],
            zip_name="mait_nkt_results.zip",
        )
        history = (_get_task_state(task_id) or {}).get("history", [])
        _complete_script_task(
            task_id,
            module_name="mait-nkt",
            detail=f"MAIT/NKT 分析完成，生成 {len(png_urls)} 张图",
            result=normalized,
            history=history,
            app_context_app=app_context_app,
            stage="完成",
        )
    except Exception as exc:
        logger.error("MAIT/NKT task %s failed: %s", task_id, exc, exc_info=True)
        history = (_get_task_state(task_id) or {}).get("history", [])
        _set_task_state(
            task_id,
            status="failed",
            progress=float((_get_task_state(task_id) or {}).get("progress") or 0),
            stage="失败",
            detail=str(exc),
            error=str(exc),
            meta={"phase": "failed", "module": "mait-nkt"},
            history=history[-80:],
        )


# ── helper: looks like category row ────────────────────────────────────
