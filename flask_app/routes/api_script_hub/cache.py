"""Cache check and quick-scan routes for the Script Hub API."""

from pathlib import Path

import pandas as pd
from flask import Blueprint, jsonify, request

from flask_app.exceptions import ValidationError
from ._common import (
    _ALLOWED_MODULES,
    _SUPPORTED_CHAINS_WIDE,
    _sanitize_nan,
    _normalize_chain,
    _robust_read_csv,
    _cache_context_from_script_request,
    _find_reusable_script_result,
    logger,
)

bp = Blueprint("script_hub_cache", __name__)


@bp.route("/cache/check", methods=["POST"])
def check_script_hub_cache():
    try:
        data = request.get_json() or {}
        module_name = str(data.get("module") or "db-alignment").strip().lower()
        if module_name not in _ALLOWED_MODULES:
            raise ValidationError(message="Unsupported script hub module", details={"module": module_name})

        cache_context = _cache_context_from_script_request(data, module_name)
        result = _find_reusable_script_result(cache_context, module_name)
        return jsonify(_sanitize_nan({
            "success": True,
            "hit": bool(result),
            "reused_result": bool(result),
            "module": module_name,
            "analysis_signature": cache_context.get("analysis_signature", ""),
            "result_id": result.get("result_id", "") if result else "",
            "result": result,
            "project_id": cache_context.get("project_id", ""),
            "config_json": cache_context.get("config_json", {}),
            "input_assets": cache_context.get("input_assets", []),
        }))
    except ValidationError as exc:
        return jsonify({"success": False, "error": exc.error_code, "message": exc.message, "details": exc.details}), 400
    except Exception as exc:
        logger.error("Error checking Script Hub cache: %s", exc, exc_info=True)
        return jsonify({"success": False, "error": "SCRIPT_HUB_CACHE_CHECK_ERROR", "message": str(exc)}), 500


@bp.route("/quick-scan", methods=["POST"])
def quick_scan():
    """Lightweight scan of a single directory or file. Returns stats for the UI preview panel."""
    data = request.get_json() or {}
    paths = data.get("paths") or []
    if isinstance(paths, str):
        paths = [paths]
    if not isinstance(paths, list) or len(paths) == 0:
        return jsonify({"success": False, "message": "paths is required"}), 400

    results = []
    total_samples = 0
    total_pep_files = 0
    all_chains = set()

    for p in paths:
        target = Path(str(p))
        entry = {"path": str(p), "type": "file", "name": target.name}
        try:
            if target.is_dir():
                entry["type"] = "directory"
                # Scan for PEP files: {Sample}__{Chain}.csv
                pep_files = list(target.glob("*.csv")) + list(target.glob("*.csv.gz")) + list(target.glob("*.tsv")) + list(target.glob("*.tsv.gz"))
                samples = set()
                chains = set()
                for f in pep_files:
                    name = f.name
                    if "__" in name:
                        parts = name.rsplit("__", 1)
                        stem = parts[0]
                        chain_raw = parts[1].rsplit(".", 1)[0]
                        chain = _normalize_chain(chain_raw)
                        if chain in _SUPPORTED_CHAINS_WIDE:
                            samples.add(stem)
                            chains.add(chain)
                entry["sample_count"] = len(samples)
                entry["pep_file_count"] = len(pep_files)
                entry["chains"] = sorted(chains)
                total_samples += len(samples)
                total_pep_files += len(pep_files)
                all_chains.update(chains)
            elif target.is_file():
                entry["type"] = "file"
                if target.suffix.lower() == '.xlsx':
                    xl = pd.ExcelFile(target)
                    entry["sheets"] = xl.sheet_names
                    entry["sheet_count"] = len(xl.sheet_names)
                    # Preview first sheet
                    df = pd.read_excel(target, sheet_name=0, nrows=0)
                    entry["columns"] = df.columns.tolist()
                    entry["column_count"] = len(entry["columns"])
                else:
                    df = _robust_read_csv(target, nrows=0)
                    entry["columns"] = df.columns.tolist()
                    entry["column_count"] = len(entry["columns"])
            else:
                entry["error"] = "Path does not exist"
        except Exception as e:
            entry["error"] = str(e)
        results.append(entry)

    column_sets = [set(r.get("columns", [])) for r in results if r.get("type") == "file" and "columns" in r]
    columns_aligned = True
    if len(column_sets) > 1:
        first = column_sets[0]
        columns_aligned = all(s == first for s in column_sets[1:])

    return jsonify({
        "success": True,
        "results": results,
        "summary": {
            "pep_dir_count": sum(1 for r in results if r.get("type") == "directory"),
            "dp_file_count": sum(1 for r in results if r.get("type") == "file"),
            "total_samples": total_samples,
            "total_pep_files": total_pep_files,
            "all_chains": sorted(all_chains),
            "columns_aligned": columns_aligned,
        },
    })
