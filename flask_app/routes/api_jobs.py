"""Global background job API.

.. attention:: **DEPRECATED — superseded by FastAPI** ``backend-api/app/api/jobs.py``.

   New code should use ``GET/POST/DELETE /api/jobs`` via the FastAPI router.
   This blueprint is retained only for legacy worker ``call_json_endpoint``
   compatibility during migration.  Will be removed once all workers use
   ``analysis_workers.results.WorkerResults`` directly.
"""

from __future__ import annotations

import json
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from flask_app.models.database import AnalysisJob, ProjectAsset, db
from flask_app.services.background_job_service import TERMINAL_STATUSES, get_background_job_service
from flask_app.services.api_job_runner import ALLOWED_API_JOBS, get_job_runner
from flask_app.services.job_queue import get_job_queue
from flask_app.services.user_scope import current_user_id, is_admin


jobs_bp = Blueprint("jobs", __name__, url_prefix="/api/jobs")


def _truthy(value: Any) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _json_error(error_code: str, message: str, status_code: int = 500, **details: Any):
    payload = {
        "success": False,
        "error": error_code,
        "message": message,
    }
    if details:
        payload["details"] = details
    return jsonify(payload), status_code


def _sse_event(event: str, data: Dict[str, Any], *, event_id: str = "") -> str:
    parts = []
    if event_id:
        parts.append(f"id: {event_id}")
    if event:
        parts.append(f"event: {event}")
    payload = json.dumps(data, ensure_ascii=False, default=str)
    for line in payload.splitlines() or [""]:
        parts.append(f"data: {line}")
    return "\n".join(parts) + "\n\n"


def _sse_comment(value: str) -> str:
    return f": {value}\n\n"


def _event_stream_interval() -> float:
    try:
        requested = float(request.args.get("interval", 1.0))
    except (TypeError, ValueError):
        requested = 1.0
    return max(0.2, min(requested, 30.0))


def _event_stream_max_events() -> int:
    try:
        requested = int(request.args.get("max_events", 300))
    except (TypeError, ValueError):
        requested = 300
    return max(1, min(requested, 1000))


def _analysis_input_descriptor(path_value: str, asset_type: str) -> Dict[str, Any]:
    path = Path(str(path_value or "").strip())
    descriptor: Dict[str, Any] = {
        "asset_type": asset_type,
        "path": str(path_value or "").strip(),
        "exists": path.exists(),
    }
    try:
        resolved = path.resolve()
        descriptor["path"] = str(resolved)
        stat = resolved.stat()
        descriptor["mtime"] = int(stat.st_mtime)
        descriptor["size"] = int(stat.st_size) if resolved.is_file() else 0
        descriptor["kind"] = "file" if resolved.is_file() else "directory"
    except OSError:
        descriptor["mtime"] = 0
        descriptor["size"] = 0
        descriptor["kind"] = ""
    return descriptor


def _build_charts_cache_context(project_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    project_id = str(project_id or "").strip()
    selected = [str(item) for item in payload.get("selected_modules") or ["heatmap", "treemap", "chord"]]
    samples = payload.get("samples") if isinstance(payload.get("samples"), list) else []
    input_paths: List[str] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        for file_info in sample.get("data_files") or []:
            if isinstance(file_info, dict) and str(file_info.get("filepath") or "").strip():
                input_paths.append(str(file_info.get("filepath")).strip())
        if str(sample.get("folder_path") or "").strip():
            input_paths.append(str(sample.get("folder_path")).strip())
    input_assets = [
        _analysis_input_descriptor(path, "sample")
        for path in sorted(dict.fromkeys(input_paths))
    ]
    transcriptome_path = str(payload.get("transcriptome_path") or "").strip()
    if transcriptome_path:
        input_assets.append(_analysis_input_descriptor(transcriptome_path, "transcriptome"))
    config_json = {
        "selected_modules": sorted(selected),
        "selected_chains": [str(item) for item in payload.get("selected_chains") or []],
        "field_mapping": payload.get("field_mapping") if isinstance(payload.get("field_mapping"), dict) else {},
        "sample_count": len(samples),
        "sample_keys": sorted(str(sample.get("sample_key") or sample.get("display_name") or sample.get("original_name") or "") for sample in samples if isinstance(sample, dict)),
        "has_transcriptome": bool(transcriptome_path),
    }
    if not project_id:
        return {"project_id": "", "analysis_signature": "", "input_assets": input_assets, "config_json": config_json}
    try:
        from flask_app.services.mongo_service import build_analysis_signature
        analysis_signature = build_analysis_signature(
            project_id=project_id,
            analysis_type="charts.combined",
            input_assets=input_assets,
            config_json=config_json,
        )
    except Exception:
        analysis_signature = ""
    return {
        "project_id": project_id,
        "analysis_signature": analysis_signature,
        "input_assets": input_assets,
        "config_json": config_json,
    }


def _string_list(value: Any) -> List[str]:
    if not isinstance(value, list):
        return []
    return [str(item or "").strip() for item in value if str(item or "").strip()]


def _sample_name(sample: Dict[str, Any]) -> str:
    return str(
        sample.get("sample_key")
        or sample.get("display_name")
        or sample.get("original_name")
        or ""
    ).strip()


def _guess_column(columns: List[str], candidates: List[str]) -> str:
    exact = {str(column): str(column) for column in columns}
    lowered = {str(column).lower(): str(column) for column in columns}
    for candidate in candidates:
        if candidate in exact:
            return exact[candidate]
        lower = candidate.lower()
        if lower in lowered:
            return lowered[lower]
    for candidate in candidates:
        lower = candidate.lower()
        for column in columns:
            if lower in str(column).lower():
                return str(column)
    return candidates[0]


def _default_charts_field_mapping(samples: List[Dict[str, Any]], current: Dict[str, Any]) -> Dict[str, Any]:
    columns: List[str] = []
    for sample in samples:
        for file_info in sample.get("data_files") or []:
            if isinstance(file_info, dict):
                columns.extend(str(column) for column in file_info.get("columns") or [] if str(column or "").strip())
    unique_columns = list(dict.fromkeys(columns))
    mapping = dict(current or {})
    defaults = {
        "cdr3_column": _guess_column(unique_columns, ["CDR3(pep)", "CDR3", "cdr3", "junction_aa"]),
        "copy_column": _guess_column(unique_columns, ["copy", "Copy", "count", "cloneCount", "frequency"]),
        "v_column": _guess_column(unique_columns, ["V", "v_call", "v_gene", "VGene"]),
        "j_column": _guess_column(unique_columns, ["J", "j_call", "j_gene", "JGene"]),
    }
    for key, value in defaults.items():
        if not str(mapping.get(key) or "").strip():
            mapping[key] = value
    return mapping


def _charts_module_config(payload: Dict[str, Any]) -> Dict[str, Any]:
    sample_names: List[str] = []
    for sample in payload.get("samples") if isinstance(payload.get("samples"), list) else []:
        if isinstance(sample, dict):
            name = _sample_name(sample)
            if name:
                sample_names.append(name)
        elif str(sample or "").strip():
            sample_names.append(str(sample).strip())
    config = {
        "selected_modules": _string_list(payload.get("selected_modules")),
        "samples": list(dict.fromkeys(sample_names)),
        "selected_chains": _string_list(payload.get("selected_chains")),
    }
    for key in ("group_spec_id", "output_name", "field_mapping"):
        value = payload.get(key)
        if value not in (None, "", [], {}):
            config[key] = value
    return config


def _resolve_project_pep_paths(project_id: str, asset_set: str) -> List[str]:
    if not project_id:
        return []
    query = ProjectAsset.query.filter(
        ProjectAsset.project_id == project_id,
        ProjectAsset.asset_type == "pep",
    )
    paths: List[str] = []
    for asset in query.all():
        metadata = asset.metadata_json or {}
        if asset_set and str(metadata.get("asset_set") or metadata.get("group_label") or "") != asset_set:
            continue
        if asset.storage_path:
            paths.append(str(asset.storage_path))
    return list(dict.fromkeys(paths))


def _normalize_charts_payload(project_id: Optional[str], payload: Dict[str, Any]) -> Dict[str, Any]:
    normalized = dict(payload)
    normalized.setdefault("_module_config", _charts_module_config(payload))

    raw_samples = normalized.get("samples") if isinstance(normalized.get("samples"), list) else []
    if raw_samples and all(isinstance(sample, dict) for sample in raw_samples):
        normalized["field_mapping"] = _default_charts_field_mapping(raw_samples, normalized.get("field_mapping") or {})
        normalized["_module_config"] = _charts_module_config(normalized)
        return normalized

    selected_names = set(_string_list(raw_samples))
    pep_paths = _string_list(normalized.get("pep_paths"))
    if not pep_paths:
        pep_paths = _resolve_project_pep_paths(
            str(project_id or normalized.get("project_id") or "").strip(),
            str(normalized.get("asset_set") or "").strip(),
        )
    if not selected_names or not pep_paths:
        return normalized

    try:
        from flask_app.services.auto_heatmap_service import get_auto_heatmap_service
        service = get_auto_heatmap_service()
        scanned_samples: Dict[str, Dict[str, Any]] = {}
        for pep_path in pep_paths:
            scan_result = service.scan_base_folder(pep_path).to_dict()
            for sample in scan_result.get("samples") or []:
                if not isinstance(sample, dict):
                    continue
                name = _sample_name(sample)
                if name:
                    scanned_samples[name] = sample
        resolved = [
            sample
            for name, sample in scanned_samples.items()
            if name in selected_names
        ]
    except Exception as exc:
        raise ValueError(f"Failed to resolve selected PEP samples: {exc}") from exc

    missing = sorted(selected_names - {_sample_name(sample) for sample in resolved})
    if missing:
        raise ValueError(f"Selected samples not found in PEP assets: {', '.join(missing)}")
    normalized["samples"] = resolved
    normalized["field_mapping"] = _default_charts_field_mapping(resolved, normalized.get("field_mapping") or {})
    normalized["_module_config"] = _charts_module_config(normalized)
    return normalized


def _mongo_result_to_charts_result(doc: Dict[str, Any]) -> Dict[str, Any]:
    metadata = doc.get("metadata_json") if isinstance(doc.get("metadata_json"), dict) else {}
    return {
        "module": "charts.combined",
        "job_id": doc.get("job_id", ""),
        "viewer_url": doc.get("viewer_url", ""),
        "zip_url": doc.get("zip_url", ""),
        "output_base": doc.get("output_base", ""),
        "chart_results": metadata.get("chart_results", []),
        "metadata": metadata.get("metadata", metadata),
        "analysis_signature": doc.get("analysis_signature", ""),
        "result_id": str(doc.get("_id") or ""),
        "reused_result": True,
    }


def _find_reusable_charts_result(cache_context: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    project_id = cache_context.get("project_id") or ""
    signature = cache_context.get("analysis_signature") or ""
    if not project_id or not signature:
        return None
    try:
        from flask_app.services.mongo_service import find_result_by_signature
        doc = find_result_by_signature(project_id, "charts.combined", signature)
    except Exception:
        return None
    return _mongo_result_to_charts_result(doc) if doc else None


def _can_access_job(job: Dict[str, Any]) -> bool:
    return is_admin() or job.get("user_id") in {None, current_user_id()}


def _append_output(
    outputs: List[Dict[str, Any]],
    seen: set[str],
    *,
    label: str,
    url: str,
    kind: str,
    module: str = "",
    category: str = "",
    download_url: str = "",
    asset_id: str = "",
) -> None:
    url = str(url or "").strip()
    download_url = str(download_url or "").strip()
    raw_identity = url or download_url
    if not raw_identity:
        return
    identity = f"{module or ''}:{raw_identity}"
    if identity in seen:
        return
    seen.add(identity)
    kind = str(kind or _kind_from_url(identity)).strip().lower()
    outputs.append({
        "label": label,
        "url": url or download_url,
        "kind": kind,
        "module": str(module or "").strip(),
        "category": str(category or _default_output_category(kind)).strip(),
        "download_url": download_url or (url if kind == "zip" else ""),
        "asset_id": str(asset_id or "").strip() or None,
    })


def _collect_result_outputs(result: Dict[str, Any]) -> List[Dict[str, Any]]:
    outputs: List[Dict[str, Any]] = []
    seen: set[str] = set()
    module_label = _module_label(result)
    chart_results = result.get("chart_results") or []
    _append_output(
        outputs,
        seen,
        label="Viewer",
        url=result.get("viewer_url", ""),
        kind="html",
        module=module_label,
        category="Viewer",
    )
    _append_output(
        outputs,
        seen,
        label="Bundle",
        url=result.get("zip_url", ""),
        kind="zip",
        module=module_label,
        category="Archive",
        download_url=result.get("zip_url", ""),
    )
    _append_output(
        outputs,
        seen,
        label="Metadata",
        url=result.get("metadata_url", ""),
        kind="json",
        module=module_label,
        category="Metadata",
    )
    for item in chart_results:
        if not isinstance(item, dict):
            continue
        module = str(item.get("label") or item.get("module") or item.get("name") or item.get("key") or "Result")
        _append_output(
            outputs,
            seen,
            label=f"{module} viewer",
            url=item.get("viewer_url", ""),
            kind="html",
            module=module,
            category="Viewer",
        )
        _append_output(
            outputs,
            seen,
            label=f"{module} bundle",
            url=item.get("zip_url", ""),
            kind="zip",
            module=module,
            category="Archive",
            download_url=item.get("zip_url", ""),
        )
        _append_output(
            outputs,
            seen,
            label=f"{module} metadata",
            url=item.get("metadata_url", ""),
            kind="json",
            module=module,
            category="Metadata",
        )
    for item in result.get("files") or []:
        if not isinstance(item, dict):
            continue
        label = str(item.get("label") or item.get("name") or item.get("kind") or "File")
        kind = str(item.get("kind") or _kind_from_url(str(item.get("url") or "")) or "data")
        _append_output(
            outputs,
            seen,
            label=label,
            url=item.get("url", ""),
            kind=kind,
            module=str(item.get("module") or module_label),
            category=str(item.get("category") or _default_output_category(kind)),
            download_url=item.get("download_url", ""),
            asset_id=str(item.get("asset_id") or ""),
        )
    _append_url_list(outputs, seen, result, key="png_urls", module=module_label, category="Plots", kind="image")
    _append_url_list(outputs, seen, result, key="plot_urls", module=module_label, category="Plots", kind="image")
    _append_url_list(outputs, seen, result, key="plot_heatmap_urls", module=module_label, category="Heatmaps", kind="image")
    return outputs


def _unwrap_result_payload(result: Dict[str, Any]) -> Dict[str, Any]:
    """Return the actual analysis result from a worker envelope if present."""
    if not isinstance(result, dict):
        return {}
    data = result.get("data")
    if isinstance(data, dict) and (
        data.get("viewer_url")
        or data.get("zip_url")
        or data.get("chart_results")
        or data.get("outputs")
        or data.get("files")
    ):
        return data
    return result


def _append_url_list(
    outputs: List[Dict[str, Any]],
    seen: set[str],
    result: Dict[str, Any],
    *,
    key: str,
    module: str,
    category: str,
    kind: str,
) -> None:
    values = result.get(key)
    if not isinstance(values, list):
        return
    for index, url in enumerate(values, start=1):
        if not isinstance(url, str):
            continue
        _append_output(
            outputs,
            seen,
            label=f"{category} {index}",
            url=url,
            kind=kind,
            module=module,
            category=category,
        )


def _module_label(result: Dict[str, Any]) -> str:
    return str(
        result.get("label")
        or result.get("module")
        or result.get("payload_module")
        or result.get("analysis_type")
        or "Result"
    )


def _kind_from_url(url: str) -> str:
    lower = str(url or "").split("?", 1)[0].lower()
    if lower.endswith((".html", ".htm")):
        return "html"
    if lower.endswith((".png", ".jpg", ".jpeg", ".svg", ".webp")):
        return "image"
    if lower.endswith(".zip"):
        return "zip"
    if lower.endswith(".pdf"):
        return "pdf"
    if lower.endswith((".csv", ".tsv", ".xlsx", ".xls")):
        return "csv"
    if lower.endswith(".json"):
        return "json"
    if lower.endswith((".ppt", ".pptx")):
        return "ppt"
    return "data"


def _default_output_category(kind: str) -> str:
    kind = str(kind or "").lower()
    if kind == "zip":
        return "Archive"
    if kind == "html":
        return "Viewer"
    if kind in {"png", "image"}:
        return "Plots"
    if kind == "json":
        return "Metadata"
    return kind.upper() if kind else "File"


def _job_result_assets(job: Dict[str, Any]) -> List[Dict[str, Any]]:
    project_id = str(job.get("project_id") or "").strip()
    if not project_id:
        return []
    matched: List[Dict[str, Any]] = []
    job_id = str(job.get("job_id") or job.get("id") or "").strip()
    module = str(job.get("module") or "").strip()
    try:
        candidates = ProjectAsset.query.filter(
            ProjectAsset.project_id == project_id,
            ProjectAsset.asset_type == "processed_result",
        ).limit(500).all()
    except SQLAlchemyError:
        db.session.rollback()
        current_app.logger.warning(
            "Failed to query result assets for job %s; returning viewer outputs without registered assets.",
            job_id,
            exc_info=True,
        )
        return []

    broad_matches: List[ProjectAsset] = []
    for asset in candidates:
        metadata = asset.metadata_json or {}
        if str(metadata.get("job_id") or "").strip() == job_id or str(metadata.get("task_id") or "").strip() == job_id:
            matched.append(_asset_result_dict(asset))
            continue
        if module and metadata.get("analysis_type") == module:
            broad_matches.append(asset)
    if not matched:
        matched.extend(_asset_result_dict(asset) for asset in broad_matches[:20])
    return matched


def _asset_result_dict(asset: ProjectAsset) -> Dict[str, Any]:
    item = asset.to_dict()
    item["preview_url"] = f"/api/assets/{asset.id}/preview"
    item["download_url"] = f"/api/assets/{asset.id}/download"
    return item


def _strict_job_result_assets(job: Dict[str, Any]) -> List[ProjectAsset]:
    project_id = str(job.get("project_id") or "").strip()
    job_id = str(job.get("job_id") or job.get("id") or "").strip()
    if not project_id or not job_id:
        return []
    candidates = ProjectAsset.query.filter(
        ProjectAsset.project_id == project_id,
        ProjectAsset.asset_type == "processed_result",
    ).all()
    matched: List[ProjectAsset] = []
    for asset in candidates:
        metadata = asset.metadata_json or {}
        if str(metadata.get("job_id") or "").strip() == job_id:
            matched.append(asset)
            continue
        if str(metadata.get("task_id") or "").strip() == job_id:
            matched.append(asset)
    return matched


def _allowed_result_delete_roots() -> List[Path]:
    base_dir = Path(current_app.config.get("BASE_DIR", Path(__file__).resolve().parents[1])).resolve()
    roots = [
        Path(current_app.config.get("RESULTS_FOLDER", base_dir / "data" / "results")),
        base_dir / "data" / "projects",
    ]
    return [root.resolve() for root in roots]


def _path_under_roots(path: Path, roots: List[Path]) -> bool:
    try:
        resolved = path.resolve()
    except OSError:
        return False
    for root in roots:
        try:
            resolved.relative_to(root)
            return resolved != root
        except ValueError:
            continue
    return False


def _collect_result_paths(value: Any) -> List[str]:
    paths: List[str] = []
    path_keys = {
        "output_base",
        "report_path",
        "metadata_path",
        "zip_path",
        "viewer_path",
        "file_path",
        "path",
    }

    def walk(item: Any, key_hint: str = "") -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                walk(child, str(key))
            return
        if isinstance(item, list):
            for child in item:
                walk(child, key_hint)
            return
        if key_hint not in path_keys:
            return
        raw = str(item or "").strip()
        if not raw or raw.startswith(("http://", "https://", "/api/")):
            return
        paths.append(raw)

    walk(value)
    return paths


def _delete_job_assets_and_paths(job: Dict[str, Any]) -> Dict[str, Any]:
    job_id = str(job.get("job_id") or job.get("id") or "").strip()
    assets = _strict_job_result_assets(job)
    paths = set(_collect_result_paths(job.get("result") if isinstance(job.get("result"), dict) else {}))
    for asset in assets:
        if asset.storage_path:
            paths.add(str(asset.storage_path))
        metadata = asset.metadata_json or {}
        for key in ("output_base", "report_path", "metadata_path", "zip_path"):
            if metadata.get(key):
                paths.add(str(metadata.get(key)))

    deleted_paths: List[str] = []
    skipped_paths: List[str] = []
    errors: List[str] = []
    roots = _allowed_result_delete_roots()
    for raw_path in sorted(paths, key=len, reverse=True):
        path = Path(raw_path)
        if not path.exists():
            skipped_paths.append(raw_path)
            continue
        if not _path_under_roots(path, roots):
            skipped_paths.append(raw_path)
            continue
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink(missing_ok=True)
            deleted_paths.append(str(path))
        except OSError as exc:
            errors.append(f"{path}: {exc}")

    deleted_assets: List[str] = []
    try:
        if job_id:
            db.session.execute(text("DELETE FROM job_assets WHERE job_id = :job_id"), {"job_id": job_id})
    except Exception:
        db.session.rollback()

    for asset in assets:
        deleted_assets.append(str(asset.id))
        db.session.delete(asset)
    db.session.commit()

    return {
        "deleted_assets": deleted_assets,
        "deleted_paths": deleted_paths,
        "skipped_paths": skipped_paths,
        "errors": errors,
    }


def _child_job_ids(parent_job_id: str) -> List[str]:
    child_ids: List[str] = []
    for job in AnalysisJob.query.all():
        payload = job.payload or {}
        if isinstance(payload, dict) and str(payload.get("parent_job_id") or "") == parent_job_id:
            child_ids.append(str(job.id))
    return child_ids


def _delete_job_record_and_results(job_id: str, *, delete_results: bool) -> tuple[Dict[str, Any], int]:
    service = get_background_job_service()
    job = service.get_job(job_id)
    if job is None:
        raise KeyError("JOB_NOT_FOUND")
    if not _can_access_job(job):
        raise KeyError("JOB_NOT_FOUND")
    if job.get("status") not in TERMINAL_STATUSES:
        raise RuntimeError("JOB_NOT_TERMINAL")

    deleted_children = 0
    child_ids = [] if job.get("parent_job_id") else _child_job_ids(job_id)
    summary = {
        "deleted_job": None,
        "deleted_children": 0,
        "deleted_assets": [],
        "deleted_paths": [],
        "skipped_paths": [],
        "errors": [],
    }

    for child_id in child_ids:
        child = service.get_job(child_id)
        if not child:
            continue
        if delete_results:
            cleanup = _delete_job_assets_and_paths(child)
            for key in ("deleted_assets", "deleted_paths", "skipped_paths", "errors"):
                summary[key].extend(cleanup[key])
        if service.delete_job(child_id):
            deleted_children += 1

    if delete_results:
        cleanup = _delete_job_assets_and_paths(job)
        for key in ("deleted_assets", "deleted_paths", "skipped_paths", "errors"):
            summary[key].extend(cleanup[key])

    deleted = service.delete_job(job_id)
    summary["deleted_job"] = deleted
    summary["deleted_children"] = deleted_children
    return summary, 200


@jobs_bp.route("", methods=["POST"])
def create_job():
    data = request.get_json() or {}
    module = str(data.get("module") or "").strip()
    payload = data.get("payload") if isinstance(data.get("payload"), dict) else {}
    project_id = str(data.get("project_id") or payload.get("project_id") or "").strip() or None
    if module not in ALLOWED_API_JOBS:
        return jsonify({
            "success": False,
            "error": "UNSUPPORTED_JOB_MODULE",
            "message": f"Unsupported background job module: {module or '-'}",
            "supported_modules": sorted(ALLOWED_API_JOBS),
        }), 400

    service = get_background_job_service()
    user_id = current_user_id()
    if module == "charts.combined":
        try:
            payload = _normalize_charts_payload(project_id, payload)
        except ValueError as exc:
            return jsonify({
                "success": False,
                "error": "CHARTS_PAYLOAD_ERROR",
                "message": str(exc),
            }), 400
        cache_context = _build_charts_cache_context(project_id, payload)
        if not _truthy(data.get("force_rerun")) and not _truthy(payload.get("force_rerun")):
            cached_result = _find_reusable_charts_result(cache_context)
            if cached_result:
                return jsonify({
                    "success": True,
                    "job_id": cached_result.get("job_id"),
                    "task_id": cached_result.get("job_id"),
                    "status": "completed",
                    "reused_result": True,
                    "analysis_signature": cache_context.get("analysis_signature", ""),
                    "result_id": cached_result.get("result_id", ""),
                    "result": cached_result,
                })
        payload = {
            **payload,
            **cache_context,
            "_project_id": project_id,
        }
    job = service.create_job(
        job_type="api_request",
        module=module,
        payload=payload,
        user_id=user_id,
        project_id=project_id,
    )
    queue = get_job_queue()
    queue.submit(job["job_id"], get_job_runner(module), module=module)
    return jsonify({
        "success": True,
        "job_id": job["job_id"],
        "task_id": job["job_id"],
        "status_url": f"/api/jobs/{job['job_id']}",
        "status": job["status"],
    })


@jobs_bp.route("", methods=["GET"])
def list_jobs():
    try:
        service = get_background_job_service()
        include_children = _truthy(request.args.get("include_children"))
        jobs = service.list_jobs(
            module=request.args.get("module") or None,
            project_id=request.args.get("project_id") or None,
            status=request.args.get("status") or None,
            user_id=current_user_id(),
            include_admin_scope=is_admin(),
            include_children=include_children,
            limit=request.args.get("limit", default=100, type=int) or 100,
        )
        return jsonify({"success": True, "jobs": jobs})
    except Exception as exc:
        current_app.logger.error("Failed to list background jobs: %s", exc, exc_info=True)
        return _json_error(
            "JOBS_LIST_ERROR",
            "Failed to load background jobs. If this is a local database, run migrations/add_analysis_jobs.py --apply and restart the server.",
            detail=str(exc),
        )


@jobs_bp.route("/modules", methods=["GET"])
def list_job_modules():
    labels = {
        "charts.combined": "综合图表",
    }
    visible_modules = ["charts.combined"]
    return jsonify({
        "success": True,
        "modules": [
            {"key": key, "label": labels.get(key, key.replace(".", " / "))}
            for key in visible_modules
            if key in ALLOWED_API_JOBS
        ],
    })


@jobs_bp.route("/bulk-delete", methods=["POST"])
def bulk_delete_jobs():
    data = request.get_json(silent=True) or {}
    job_ids = data.get("job_ids") if isinstance(data.get("job_ids"), list) else []
    delete_results = _truthy(data.get("delete_results"))
    results = []
    for raw_id in job_ids:
        job_id = str(raw_id or "").strip()
        if not job_id:
            continue
        try:
            summary, _ = _delete_job_record_and_results(job_id, delete_results=delete_results)
            results.append({"job_id": job_id, "success": True, **summary})
        except KeyError:
            results.append({"job_id": job_id, "success": False, "error": "JOB_NOT_FOUND"})
        except RuntimeError as exc:
            results.append({"job_id": job_id, "success": False, "error": str(exc)})
        except Exception as exc:
            current_app.logger.error("Failed to bulk delete job %s: %s", job_id, exc, exc_info=True)
            results.append({"job_id": job_id, "success": False, "error": str(exc)})
    return jsonify({"success": True, "results": results})


@jobs_bp.route("/<job_id>", methods=["GET"])
def get_job(job_id: str):
    try:
        job = get_background_job_service().get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        return jsonify({"success": True, "job": job, **job})
    except Exception as exc:
        current_app.logger.error("Failed to get background job %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_GET_ERROR", "Failed to load background job.", detail=str(exc))


@jobs_bp.route("/<job_id>/events", methods=["GET"])
def stream_job_events(job_id: str):
    service = get_background_job_service()
    job = service.get_job(job_id)
    if job is None:
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
    if not _can_access_job(job):
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404

    interval = _event_stream_interval()
    max_events = _event_stream_max_events()

    @stream_with_context
    def generate():
        last_payload = ""
        sent_events = 0
        while sent_events < max_events:
            current = service.get_job(job_id)
            if current is None:
                yield _sse_event("error", {
                    "success": False,
                    "error": "JOB_NOT_FOUND",
                    "message": "Job not found",
                }, event_id=job_id)
                break

            status = str(current.get("status") or "")
            event_name = "completed" if status in TERMINAL_STATUSES else "update"
            payload = {
                "success": True,
                "job": current,
                "status": status,
            }
            serialized = json.dumps(payload, ensure_ascii=False, default=str)
            if serialized != last_payload:
                yield _sse_event(event_name, payload, event_id=job_id)
                last_payload = serialized
                sent_events += 1
            else:
                yield _sse_comment("heartbeat")

            if status in TERMINAL_STATUSES:
                break
            time.sleep(interval)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@jobs_bp.route("/<job_id>/results", methods=["GET"])
def get_job_results(job_id: str):
    try:
        job = get_background_job_service().get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404

        raw_result = job.get("result") if isinstance(job.get("result"), dict) else {}
        result = _unwrap_result_payload(raw_result)
        outputs = _collect_result_outputs(result)
        assets = _job_result_assets(job)
        return jsonify({
            "success": True,
            "job": job,
            "status": job.get("status"),
            "result": result,
            "outputs": outputs,
            "assets": assets,
        })
    except Exception as exc:
        current_app.logger.error("Failed to get background job results %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_RESULTS_ERROR", "Failed to load background job results.", detail=str(exc))


@jobs_bp.route("/<job_id>/cancel", methods=["POST"])
def cancel_job(job_id: str):
    try:
        job = get_background_job_service().get_job(job_id)
        if job is None:
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        if not _can_access_job(job):
            return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
        updated = get_background_job_service().request_cancel(job_id)
        return jsonify({"success": True, "job": updated})
    except Exception as exc:
        current_app.logger.error("Failed to cancel background job %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_CANCEL_ERROR", "Failed to cancel background job.", detail=str(exc))


@jobs_bp.route("/<job_id>", methods=["DELETE"])
def delete_job(job_id: str):
    try:
        delete_results = _truthy(request.args.get("delete_results"))
        summary, _ = _delete_job_record_and_results(job_id, delete_results=delete_results)
        return jsonify({"success": True, **summary})
    except KeyError:
        return jsonify({"success": False, "error": "JOB_NOT_FOUND", "message": "Job not found"}), 404
    except RuntimeError as exc:
        if str(exc) == "JOB_NOT_TERMINAL":
            return jsonify({
                "success": False,
                "error": "JOB_NOT_TERMINAL",
                "message": "Running or queued jobs must be cancelled before they can be deleted.",
            }), 409
        return _json_error("JOB_DELETE_ERROR", "Failed to delete background job.", detail=str(exc))
    except Exception as exc:
        current_app.logger.error("Failed to delete background job %s: %s", job_id, exc, exc_info=True)
        return _json_error("JOB_DELETE_ERROR", "Failed to delete background job.", detail=str(exc))
