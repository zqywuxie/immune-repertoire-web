"""
Pipeline comparison integration service.

This service integrates the standalone `pipeline_comparison_heatmap.py` workflow
into the Flask project while reusing existing in-project components:
- AutoHeatmapService for similarity matrix computation
- HeatmapGenerator for rendering heatmaps
- (optional) CDR3ExportService for export packaging

The external script is reused for:
- 3-pipeline Venn rendering
- Interactive HTML report generation
"""

from __future__ import annotations

import importlib.util
import json
import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from flask_app.exceptions import ValidationError
from flask_app.services.auto_heatmap_service import AutoHeatmapService
from flask_app.services.result_path_resolver import candidate_job_roots
from flask_app.services.heatmap_generator import HeatmapConfig, HeatmapGenerator

try:
    from flask_app.services.cdr3_export_service import get_cdr3_export_service
except ModuleNotFoundError:
    get_cdr3_export_service = None

logger = logging.getLogger(__name__)


DEFAULT_PIPELINE_CONFIG: Dict[str, Dict[str, str]] = {
    "YXJ": {
        "dir_name": "YXJ",
        "cdr3_col": "cdr3_aa",
        "copy_col": "umi_counts",
        "file_pattern": "{sample}_{chain}.csv",
    },
    "DW": {
        "dir_name": "DW",
        "cdr3_col": "CDR3(pep)",
        "copy_col": "copy",
        "file_pattern": "SS03P_{sample}__{chain}.csv",
    },
    "YPL": {
        "dir_name": "YPL",
        "cdr3_col": "CDR3(pep)",
        "copy_col": "umi_number",
        "file_pattern": "{sample}-PER_{sample}_{chain}.csv",
    },
}

METRICS: List[str] = [
    "expression_sharing",
    "morisita_horn",
    "cdr3_sharing",
    "r2_inner",
    "r2_outer",
    "sorensen",
]

METRIC_LABELS: Dict[str, str] = {
    "expression_sharing": "Expression Sharing",
    "morisita_horn": "Morisita-Horn Index",
    "cdr3_sharing": "Unique CDR3 Sharing",
    "r2_inner": "R2 Inner",
    "r2_outer": "R2 Outer",
    "sorensen": "Sorensen-Dice Index",
}


@dataclass
class PipelineDefinition:
    """Resolved pipeline input definition."""

    name: str
    directory: Path
    cdr3_col: str
    copy_col: str
    file_pattern: str


@dataclass
class PipelineComparisonRunResult:
    """Pipeline comparison run output metadata."""

    job_id: str
    output_base: Path
    metadata_path: Path
    report_path: Optional[Path]
    metadata: Dict[str, Any]


class PipelineComparisonIntegrationService:
    """
    Integrates pipeline comparison generation into the Flask app.

    Result directory layout:
    <results_root>/pipeline_comparison/<job_id>/shared_analysis/
    """

    _PIPELINE_RESULT_DIR = "pipeline_comparison"
    _PIPELINE_SCRIPT_NAME = "pipeline_comparison_heatmap.py"
    _SCAN_FILE_LIMIT = 200

    def __init__(self, results_root: Path):
        self.results_root = Path(results_root).resolve()
        self.auto_heatmap_service = AutoHeatmapService()
        self.heatmap_generator = HeatmapGenerator()
        self.results_root.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _normalize_bool(value: Any, default: bool) -> bool:
        if value is None:
            return default
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)

    @staticmethod
    def _sanitize_job_id(raw_name: Optional[str]) -> str:
        if raw_name:
            candidate = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name.strip())
            candidate = candidate.strip("_")
            if candidate:
                return candidate
        return f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:8]}"

    def _allocate_job_id(self, requested_name: Optional[str]) -> str:
        base_id = self._sanitize_job_id(requested_name)
        run_root = self.results_root / self._PIPELINE_RESULT_DIR
        run_root.mkdir(parents=True, exist_ok=True)

        candidate = base_id
        suffix = 1
        while (run_root / candidate).exists():
            candidate = f"{base_id}_{suffix}"
            suffix += 1
        return candidate

    def _pipeline_script_path(self) -> Path:
        # .../immune-repertoire-web/flask_app/services -> parent[3] == workspace root
        return Path(__file__).resolve().parents[3] / self._PIPELINE_SCRIPT_NAME

    def _load_external_pipeline_module(self) -> Any:
        script_path = self._pipeline_script_path()
        if not script_path.exists():
            raise ValidationError(
                message=f"Pipeline script not found: {script_path}",
                details={"script_path": str(script_path)},
            )

        module_name = f"pipeline_comparison_heatmap_web_{uuid.uuid4().hex}"
        spec = importlib.util.spec_from_file_location(module_name, script_path)
        if spec is None or spec.loader is None:
            raise ValidationError(
                message="Unable to load pipeline comparison script module.",
                details={"script_path": str(script_path)},
            )

        module = importlib.util.module_from_spec(spec)
        try:
            spec.loader.exec_module(module)
        except Exception as exc:
            raise ValidationError(
                message=f"Failed to import pipeline comparison script: {exc}",
                details={"script_path": str(script_path)},
            ) from exc

        return module

    @staticmethod
    def _build_pattern_regex(file_pattern: str) -> re.Pattern[str]:
        token_pattern = re.compile(r"\{(sample|chain)\}")
        seen_tokens: set = set()
        parts: List[str] = []
        cursor = 0

        for match in token_pattern.finditer(file_pattern):
            parts.append(re.escape(file_pattern[cursor:match.start()]))
            token = match.group(1)
            if token in seen_tokens:
                parts.append(f"(?P={token})")
            elif token == "sample":
                parts.append(r"(?P<sample>.+?)")
                seen_tokens.add(token)
            else:
                parts.append(r"(?P<chain>[A-Za-z0-9]+)")
                seen_tokens.add(token)
            cursor = match.end()

        parts.append(re.escape(file_pattern[cursor:]))
        pattern = "^" + "".join(parts) + "$"
        return re.compile(pattern, re.IGNORECASE)

    def _read_columns_preview(self, file_path: Path) -> Tuple[List[str], int]:
        """Read columns and a small row preview size from a data file."""
        try:
            sep = self.auto_heatmap_service._detect_separator(str(file_path))
            preview_df = pd.read_csv(
                file_path,
                sep=sep,
                nrows=20,
                encoding="utf-8",
                on_bad_lines="skip",
            )
            return preview_df.columns.tolist(), len(preview_df)
        except Exception:
            return [], 0

    def _guess_file_pattern_from_filename(self, filename: str) -> str:
        """
        Guess a {sample}/{chain} filename template from one filename.
        This is a best-effort fallback for custom pipelines.
        """
        if not filename:
            return "{sample}_{chain}.csv"

        path_obj = Path(filename)
        stem = path_obj.stem
        suffix = path_obj.suffix or ".csv"

        chain_tokens = sorted(
            set(self.auto_heatmap_service.CHAIN_TYPES),
            key=len,
            reverse=True,
        )
        chain_regex = re.compile("|".join(re.escape(token) for token in chain_tokens), re.IGNORECASE)
        chain_matches = list(chain_regex.finditer(stem))

        if not chain_matches:
            return f"{{sample}}_{{chain}}{suffix}"

        chain_match = chain_matches[-1]
        before_chain = stem[:chain_match.start()]
        after_chain = stem[chain_match.end():]

        sample_token = ""
        sample_candidates = [token for token in re.split(r"[_\-]+", before_chain) if token]
        if sample_candidates:
            sample_token = sample_candidates[-1]

        if sample_token:
            sample_token_regex = re.compile(
                rf"(?<![A-Za-z0-9]){re.escape(sample_token)}(?![A-Za-z0-9])",
                re.IGNORECASE,
            )
            before_chain = sample_token_regex.sub("{sample}", before_chain)
        elif "{sample}" not in before_chain:
            before_chain = "{sample}_" + before_chain

        guessed = f"{before_chain}{{chain}}{after_chain}{suffix}"
        if "{sample}" not in guessed:
            guessed = "{sample}_" + guessed
        if "{chain}" not in guessed:
            guessed = guessed.replace(suffix, "") + "_{chain}" + suffix
        return guessed

    def scan_pipeline_root(self, base_path: str) -> Dict[str, Any]:
        """
        Scan a root folder and detect:
        - Pipeline subfolders
        - pep files under each pipeline
        - Suggested file pattern and cdr3/copy fields per pipeline
        """
        if not str(base_path or "").strip():
            raise ValidationError(
                message="base_path is required",
                details={"field": "base_path"},
            )
        base_dir = Path(str(base_path).strip()).expanduser().resolve()
        if not base_dir.exists():
            raise ValidationError(
                message=f"Path does not exist: {base_dir}",
                details={"field": "base_path"},
            )
        if not base_dir.is_dir():
            raise ValidationError(
                message=f"Path is not a directory: {base_dir}",
                details={"field": "base_path"},
            )

        pipeline_dirs = sorted(
            [
                item
                for item in base_dir.iterdir()
                if item.is_dir() and not item.name.startswith(".")
            ],
            key=lambda p: p.name.lower(),
        )
        if not pipeline_dirs:
            raise ValidationError(
                message="No subfolders found under base_path.",
                details={"field": "base_path"},
            )

        supported_exts = set(ext.lower() for ext in self.auto_heatmap_service.SUPPORTED_EXTENSIONS)
        pipelines: List[Dict[str, Any]] = []
        total_recognized_files = 0

        for pipeline_dir in pipeline_dirs:
            pipeline_name = pipeline_dir.name
            default_cfg = DEFAULT_PIPELINE_CONFIG.get(pipeline_name, {})
            default_cdr3 = str(default_cfg.get("cdr3_col", "")).strip()
            default_copy = str(default_cfg.get("copy_col", "")).strip()
            default_pattern = str(default_cfg.get("file_pattern", "")).strip()

            default_regex: Optional[re.Pattern[str]] = None
            if default_pattern:
                try:
                    default_regex = self._build_pattern_regex(default_pattern)
                except Exception:
                    default_regex = None

            recognized_files: List[Dict[str, Any]] = []
            visited_candidates = 0

            for file_path in sorted(pipeline_dir.rglob("*"), key=lambda p: str(p).lower()):
                if not file_path.is_file():
                    continue
                if file_path.suffix.lower() not in supported_exts:
                    continue
                visited_candidates += 1
                if visited_candidates > self._SCAN_FILE_LIMIT:
                    break

                columns, preview_rows = self._read_columns_preview(file_path)

                suggested_cdr3 = self.auto_heatmap_service._find_matching_column(
                    columns,
                    self.auto_heatmap_service.CDR3_COLUMN_PATTERNS,
                )
                suggested_copy = self.auto_heatmap_service._find_matching_column(
                    columns,
                    self.auto_heatmap_service.COPY_COLUMN_PATTERNS,
                )

                name_has_pep = "pep" in file_path.name.lower()
                matched_default_pattern = bool(default_regex and default_regex.match(file_path.name))
                has_cdr3_copy = bool(suggested_cdr3 and suggested_copy)

                # Intelligent recognition rules:
                # 1) filename contains "pep", OR
                # 2) columns indicate both CDR3 and copy/count-like fields, OR
                # 3) filename matches default pipeline pattern (YXJ/DW/YPL, etc.)
                if not (name_has_pep or has_cdr3_copy or matched_default_pattern):
                    continue

                if not suggested_cdr3 and default_cdr3 and default_cdr3 in columns:
                    suggested_cdr3 = default_cdr3
                if not suggested_copy and default_copy and default_copy in columns:
                    suggested_copy = default_copy

                score = 0
                if matched_default_pattern:
                    score += 5
                if name_has_pep:
                    score += 4
                if suggested_cdr3:
                    score += 3
                if suggested_copy:
                    score += 2

                recognized_files.append(
                    {
                        "filename": file_path.name,
                        "filepath": str(file_path),
                        "relative_path": str(file_path.relative_to(pipeline_dir)),
                        "columns": columns,
                        "preview_rows": preview_rows,
                        "suggested_cdr3": suggested_cdr3,
                        "suggested_copy": suggested_copy,
                        "name_has_pep": name_has_pep,
                        "matched_default_pattern": matched_default_pattern,
                        "recognition_score": score,
                    }
                )

            recognized_files.sort(
                key=lambda item: (-int(item.get("recognition_score", 0)), str(item.get("filename", "")).lower())
            )

            total_recognized_files += len(recognized_files)
            suggested_pattern = default_pattern
            suggested_cdr3 = default_cdr3
            suggested_copy = default_copy

            if recognized_files:
                first_file = recognized_files[0]
                if not suggested_pattern:
                    suggested_pattern = self._guess_file_pattern_from_filename(first_file["filename"])
                if first_file.get("suggested_cdr3"):
                    suggested_cdr3 = first_file["suggested_cdr3"]
                if first_file.get("suggested_copy"):
                    suggested_copy = first_file["suggested_copy"]
            elif not suggested_pattern:
                fallback_files = sorted(
                    [
                        file_path
                        for file_path in pipeline_dir.rglob("*")
                        if file_path.is_file() and file_path.suffix.lower() in supported_exts
                    ],
                    key=lambda p: str(p).lower(),
                )
                if fallback_files:
                    suggested_pattern = self._guess_file_pattern_from_filename(fallback_files[0].name)
                else:
                    suggested_pattern = "{sample}_{chain}.csv"

            pipelines.append(
                {
                    "name": pipeline_name,
                    "directory": str(pipeline_dir),
                    "default_config_matched": pipeline_name in DEFAULT_PIPELINE_CONFIG,
                    # Keep key name for backward compatibility in frontend.
                    # Data now includes intelligently recognized compatible files.
                    "pep_files": recognized_files,
                    "pep_file_count": len(recognized_files),
                    "suggested_file_pattern": suggested_pattern,
                    "suggested_cdr3": suggested_cdr3,
                    "suggested_copy": suggested_copy,
                }
            )

        return {
            "base_path": str(base_dir),
            "pipelines": pipelines,
            "summary": (
                f"Detected {len(pipelines)} pipeline folders, "
                f"{total_recognized_files} compatible files in total."
            ),
        }

    def _resolve_pipeline_definitions(
        self,
        base_path: Path,
        pipelines: Optional[Iterable[str]],
        pipeline_configs: Optional[Any],
    ) -> List[PipelineDefinition]:
        merged: Dict[str, Dict[str, Any]] = {
            name: dict(config) for name, config in DEFAULT_PIPELINE_CONFIG.items()
        }

        if pipeline_configs:
            if isinstance(pipeline_configs, dict):
                config_items = pipeline_configs.items()
            elif isinstance(pipeline_configs, list):
                config_items = [
                    (item.get("name", ""), item) for item in pipeline_configs if isinstance(item, dict)
                ]
            else:
                raise ValidationError(
                    message="pipeline_configs must be an object or list.",
                    details={"field": "pipeline_configs"},
                )

            for name, cfg in config_items:
                if not name:
                    continue
                if name not in merged:
                    merged[name] = {}
                merged[name].update(cfg)

        pipeline_order = [p.strip() for p in pipelines or merged.keys() if str(p).strip()]
        pipeline_order = list(dict.fromkeys(pipeline_order))
        if len(pipeline_order) < 2:
            raise ValidationError(
                message="At least 2 pipelines are required.",
                details={"field": "pipelines"},
            )

        definitions: List[PipelineDefinition] = []
        for pipeline_name in pipeline_order:
            cfg = merged.get(pipeline_name)
            if not cfg:
                raise ValidationError(
                    message=f"Pipeline config missing: {pipeline_name}",
                    details={"pipeline": pipeline_name},
                )

            dir_value = cfg.get("dir") or cfg.get("directory")
            if dir_value:
                directory = Path(dir_value).expanduser().resolve()
            else:
                dir_name = cfg.get("dir_name", pipeline_name)
                directory = (base_path / dir_name).resolve()

            cdr3_col = str(cfg.get("cdr3_col", "")).strip()
            copy_col = str(cfg.get("copy_col", "")).strip()
            file_pattern = str(cfg.get("file_pattern", "")).strip()

            if not cdr3_col or not copy_col or not file_pattern:
                raise ValidationError(
                    message=f"Incomplete config for pipeline {pipeline_name}.",
                    details={"pipeline": pipeline_name},
                )

            definitions.append(
                PipelineDefinition(
                    name=pipeline_name,
                    directory=directory,
                    cdr3_col=cdr3_col,
                    copy_col=copy_col,
                    file_pattern=file_pattern,
                )
            )

        return definitions

    def _discover_files(
        self,
        definitions: List[PipelineDefinition],
    ) -> Tuple[Dict[Tuple[str, str, str], Path], List[str], List[str]]:
        file_records: Dict[Tuple[str, str, str], Path] = {}
        samples: set = set()
        chains: set = set()

        for definition in definitions:
            if not definition.directory.exists() or not definition.directory.is_dir():
                raise ValidationError(
                    message=f"Pipeline directory not found: {definition.directory}",
                    details={"pipeline": definition.name, "directory": str(definition.directory)},
                )

            regex = self._build_pattern_regex(definition.file_pattern)
            for file_path in definition.directory.rglob("*"):
                if not file_path.is_file():
                    continue

                match = regex.match(file_path.name)
                if not match:
                    continue

                sample = str(match.group("sample")).strip()
                chain = str(match.group("chain")).strip().upper()
                if not sample or not chain:
                    continue

                record_key = (sample, chain, definition.name)
                if record_key in file_records:
                    try:
                        existing_size = file_records[record_key].stat().st_size
                        current_size = file_path.stat().st_size
                    except OSError:
                        existing_size = 0
                        current_size = 0
                    if current_size > existing_size:
                        file_records[record_key] = file_path
                else:
                    file_records[record_key] = file_path

                samples.add(sample)
                chains.add(chain)

        return file_records, sorted(samples), sorted(chains)

    @staticmethod
    def _resolve_requested_values(
        available_values: List[str],
        requested_values: Optional[Any],
        field_name: str,
    ) -> List[str]:
        if requested_values is None:
            return available_values

        if isinstance(requested_values, str):
            requested = [item.strip() for item in requested_values.split(",") if item.strip()]
        elif isinstance(requested_values, list):
            requested = [str(item).strip() for item in requested_values if str(item).strip()]
        else:
            raise ValidationError(
                message=f"{field_name} must be a list or comma-separated string.",
                details={"field": field_name},
            )

        requested = list(dict.fromkeys(requested))
        unknown = [value for value in requested if value not in available_values]
        if unknown:
            raise ValidationError(
                message=f"Unknown {field_name}: {', '.join(unknown)}",
                details={"field": field_name, "unknown": unknown},
            )
        return requested

    @staticmethod
    def _normalize_cdr3(value: Any) -> str:
        cdr3 = str(value).strip().upper().replace(" ", "")
        if cdr3 in {"", "NAN", "NONE"}:
            return ""
        if len(cdr3) > 1 and cdr3[0] == "C":
            cdr3 = cdr3[1:]
        if len(cdr3) > 1 and cdr3[-1] in {"F", "W"}:
            cdr3 = cdr3[:-1]
        return cdr3

    def _load_normalized_data(self, file_path: Path, definition: PipelineDefinition) -> Optional[pd.DataFrame]:
        try:
            sep = self.auto_heatmap_service._detect_separator(str(file_path))
            df = pd.read_csv(file_path, sep=sep, low_memory=False)
        except Exception as exc:
            logger.warning("Failed to read file %s: %s", file_path, exc)
            return None

        if definition.cdr3_col not in df.columns:
            logger.warning("CDR3 column '%s' not found in %s", definition.cdr3_col, file_path)
            return None
        if definition.copy_col not in df.columns:
            logger.warning("Copy column '%s' not found in %s", definition.copy_col, file_path)
            return None

        normalized_df = pd.DataFrame(
            {
                "cdr3": df[definition.cdr3_col].astype(str).map(self._normalize_cdr3),
                "copy": pd.to_numeric(df[definition.copy_col], errors="coerce").fillna(0),
            }
        )
        normalized_df = normalized_df[normalized_df["cdr3"] != ""]
        normalized_df = normalized_df.groupby("cdr3", as_index=False)["copy"].sum()

        if normalized_df.empty:
            return None
        return normalized_df

    @staticmethod
    def _save_matrix(matrix: pd.DataFrame, output_path: Path) -> None:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        matrix.to_csv(output_path, index=True)

    @staticmethod
    def _ordered_chain_labels(
        chain_data: Dict[str, pd.DataFrame],
        sample_order: List[str],
        pipeline_order: List[str],
        mode: str,
    ) -> List[str]:
        labels: List[str] = []
        if mode == "by_sample":
            for sample in sample_order:
                for pipeline in pipeline_order:
                    label = f"{sample}_{pipeline}"
                    if label in chain_data:
                        labels.append(label)
        else:
            for pipeline in pipeline_order:
                for sample in sample_order:
                    label = f"{sample}_{pipeline}"
                    if label in chain_data:
                        labels.append(label)
        return labels

    def _write_heatmap_outputs(
        self,
        sample_data: Dict[str, pd.DataFrame],
        title_prefix: str,
        heatmap_dir: Path,
        metric_dir: Path,
        file_suffix: str,
    ) -> None:
        metrics = self.auto_heatmap_service.calculate_all_metrics(sample_data)
        for metric in METRICS:
            matrix = metrics.get(metric)
            if matrix is None or matrix.empty:
                continue

            title = f"{title_prefix} - {METRIC_LABELS.get(metric, metric)}"
            config = HeatmapConfig(
                title=title,
                annotation=True,
                figure_width=10,
                figure_height=8,
                dpi=300,
            )

            image_bytes, _ = self.heatmap_generator.generate_heatmap(
                matrix,
                config=config,
                metric_name=metric,
            )

            heatmap_path = heatmap_dir / f"{metric}_{file_suffix}.png"
            metric_path = metric_dir / f"{metric}_{file_suffix}.csv"
            heatmap_path.parent.mkdir(parents=True, exist_ok=True)
            heatmap_path.write_bytes(image_bytes)
            self._save_matrix(matrix, metric_path)

    def generate_pipeline_comparison(
        self,
        base_path: str,
        pipelines: Optional[Any] = None,
        pipeline_configs: Optional[Any] = None,
        samples: Optional[Any] = None,
        chains: Optional[Any] = None,
        output_name: Optional[str] = None,
        enable_heatmap: bool = True,
        enable_venn: bool = True,
        enable_html_report: bool = True,
        include_cdr3_analysis: bool = False,
        embed_images: bool = False,
    ) -> PipelineComparisonRunResult:
        """
        Run integrated pipeline comparison generation.
        """
        base_dir = Path(str(base_path).strip()).expanduser().resolve()
        if not base_dir.exists() or not base_dir.is_dir():
            raise ValidationError(
                message=f"Invalid base_path: {base_path}",
                details={"base_path": str(base_path)},
            )

        if isinstance(pipelines, str):
            pipelines = [item.strip() for item in pipelines.split(",") if item.strip()]
        elif pipelines is not None and not isinstance(pipelines, list):
            raise ValidationError(message="pipelines must be a list or comma-separated string.")

        enable_heatmap = self._normalize_bool(enable_heatmap, True)
        enable_venn = self._normalize_bool(enable_venn, True)
        enable_html_report = self._normalize_bool(enable_html_report, True)
        include_cdr3_analysis = self._normalize_bool(include_cdr3_analysis, False)
        embed_images = self._normalize_bool(embed_images, False)

        definitions = self._resolve_pipeline_definitions(base_dir, pipelines, pipeline_configs)
        pipeline_order = [definition.name for definition in definitions]

        file_records, detected_samples, detected_chains = self._discover_files(definitions)
        if not file_records:
            raise ValidationError(
                message="No files matched pipeline naming patterns under the provided directories.",
                details={"base_path": str(base_dir)},
            )

        sample_order = self._resolve_requested_values(detected_samples, samples, "samples")
        chain_order = self._resolve_requested_values(detected_chains, chains, "chains")
        if not sample_order:
            raise ValidationError(message="No valid samples available for comparison.")
        if not chain_order:
            raise ValidationError(message="No valid chains available for comparison.")

        job_id = self._allocate_job_id(output_name)
        run_root = self.results_root / self._PIPELINE_RESULT_DIR / job_id
        output_base = run_root / "shared_analysis"
        output_base.mkdir(parents=True, exist_ok=True)

        heatmap_base = output_base / "heatmap"
        metric_base = output_base / "metric"
        venn_ucdr3_base = output_base / "venn_ucdr3"
        venn_abundance_base = output_base / "venn_abundance"

        if enable_heatmap:
            (heatmap_base / "single_sample").mkdir(parents=True, exist_ok=True)
            (heatmap_base / "multi_sample_by_sample").mkdir(parents=True, exist_ok=True)
            (heatmap_base / "multi_sample_by_pipeline").mkdir(parents=True, exist_ok=True)
            (metric_base / "single_sample").mkdir(parents=True, exist_ok=True)
            (metric_base / "multi_sample_by_sample").mkdir(parents=True, exist_ok=True)
            (metric_base / "multi_sample_by_pipeline").mkdir(parents=True, exist_ok=True)

        external_module = None
        if enable_venn or enable_html_report:
            external_module = self._load_external_pipeline_module()
            external_module.PIPELINE_ORDER = list(pipeline_order)
            external_module.SAMPLES = list(sample_order)
            external_module.CHAINS = list(chain_order)

        if enable_venn:
            venn_ucdr3_base.mkdir(parents=True, exist_ok=True)
            venn_abundance_base.mkdir(parents=True, exist_ok=True)

        definition_map = {definition.name: definition for definition in definitions}
        loaded_cache: Dict[Tuple[str, str, str], Optional[pd.DataFrame]] = {}
        chain_loaded_data: Dict[str, Dict[str, pd.DataFrame]] = {chain: {} for chain in chain_order}
        valid_single_targets = 0

        for sample in sample_order:
            for chain in chain_order:
                pipeline_data: Dict[str, pd.DataFrame] = {}
                for pipeline in pipeline_order:
                    key = (sample, chain, pipeline)
                    file_path = file_records.get(key)
                    if file_path is None:
                        continue

                    if key not in loaded_cache:
                        loaded_cache[key] = self._load_normalized_data(file_path, definition_map[pipeline])
                    normalized_df = loaded_cache[key]
                    if normalized_df is None:
                        continue

                    pipeline_data[f"{pipeline}_{sample}"] = normalized_df
                    chain_loaded_data[chain][f"{sample}_{pipeline}"] = normalized_df

                if len(pipeline_data) < 2:
                    continue

                valid_single_targets += 1
                target_label = f"{sample}_{chain}"

                if enable_heatmap:
                    self._write_heatmap_outputs(
                        sample_data=pipeline_data,
                        title_prefix=target_label,
                        heatmap_dir=heatmap_base / "single_sample" / target_label,
                        metric_dir=metric_base / "single_sample" / target_label,
                        file_suffix="pipeline_comparison",
                    )

                if enable_venn and external_module is not None and len(pipeline_data) >= 3:
                    venn_ucdr3_dir = venn_ucdr3_base / target_label
                    venn_abundance_dir = venn_abundance_base / target_label
                    venn_ucdr3_dir.mkdir(parents=True, exist_ok=True)
                    venn_abundance_dir.mkdir(parents=True, exist_ok=True)
                    external_module.generate_venn_plots(
                        pipeline_data=pipeline_data,
                        sample=sample,
                        chain=chain,
                        ucdr3_venn_path=venn_ucdr3_dir / "ucdr3_venn.png",
                        abundance_venn_path=venn_abundance_dir / "abundance_venn.png",
                    )

        if valid_single_targets == 0:
            raise ValidationError(
                message="No valid sample-chain targets with at least 2 pipelines were found.",
                details={
                    "pipelines": pipeline_order,
                    "samples": sample_order,
                    "chains": chain_order,
                },
            )

        if enable_heatmap:
            for chain in chain_order:
                chain_data = chain_loaded_data.get(chain, {})
                if len(chain_data) < 2:
                    continue

                labels_by_sample = self._ordered_chain_labels(
                    chain_data=chain_data,
                    sample_order=sample_order,
                    pipeline_order=pipeline_order,
                    mode="by_sample",
                )
                if len(labels_by_sample) >= 2:
                    ordered_data = {label: chain_data[label] for label in labels_by_sample}
                    self._write_heatmap_outputs(
                        sample_data=ordered_data,
                        title_prefix=f"{chain} (Order: by sample)",
                        heatmap_dir=heatmap_base / "multi_sample_by_sample" / chain,
                        metric_dir=metric_base / "multi_sample_by_sample" / chain,
                        file_suffix="by_sample",
                    )

                labels_by_pipeline = self._ordered_chain_labels(
                    chain_data=chain_data,
                    sample_order=sample_order,
                    pipeline_order=pipeline_order,
                    mode="by_pipeline",
                )
                if len(labels_by_pipeline) >= 2:
                    ordered_data = {label: chain_data[label] for label in labels_by_pipeline}
                    self._write_heatmap_outputs(
                        sample_data=ordered_data,
                        title_prefix=f"{chain} (Order: by pipeline)",
                        heatmap_dir=heatmap_base / "multi_sample_by_pipeline" / chain,
                        metric_dir=metric_base / "multi_sample_by_pipeline" / chain,
                        file_suffix="by_pipeline",
                    )

        cdr3_archive_path: Optional[Path] = None
        if include_cdr3_analysis and get_cdr3_export_service is not None:
            try:
                export_service = get_cdr3_export_service()
                zip_bytes = export_service.generate_complete_export_zip(
                    sample_data=chain_loaded_data,
                    include_summary=True,
                    top_n=100,
                )
                cdr3_archive_path = output_base / "cdr3_analysis" / "CDR3_Export.zip"
                cdr3_archive_path.parent.mkdir(parents=True, exist_ok=True)
                cdr3_archive_path.write_bytes(zip_bytes)
            except Exception as exc:
                logger.warning("Failed to generate CDR3 export package: %s", exc)

        metadata = {
            "timestamp": datetime.now().isoformat(),
            "base_path": str(base_dir),
            "job_id": job_id,
            "samples": sample_order,
            "chains": chain_order,
            "pipelines": pipeline_order,
            "metrics": METRICS,
            "modules_enabled": {
                "heatmap": enable_heatmap,
                "venn": enable_venn,
                "cdr3_analysis": include_cdr3_analysis,
                "html_report": enable_html_report,
            },
            "output_modes": {
                "single_sample": "single-sample pipeline comparison",
                "multi_sample_by_sample": "single-chain multi-sample, ordered by sample",
                "multi_sample_by_pipeline": "single-chain multi-sample, ordered by pipeline",
                "venn_ucdr3": "single-sample/single-chain uCDR3 venn",
                "venn_abundance": "single-sample/single-chain abundance venn",
                "html_report": "interactive HTML report",
            },
            "pipeline_config": {
                definition.name: {
                    "directory": str(definition.directory),
                    "cdr3_col": definition.cdr3_col,
                    "copy_col": definition.copy_col,
                    "file_pattern": definition.file_pattern,
                }
                for definition in definitions
            },
            "stats": {
                "detected_samples": len(detected_samples),
                "detected_chains": len(detected_chains),
                "matched_files": len(file_records),
                "valid_single_targets": valid_single_targets,
            },
        }
        if cdr3_archive_path:
            metadata["cdr3_archive"] = str(cdr3_archive_path.relative_to(output_base))

        metadata_path = output_base / "metadata.json"
        with open(metadata_path, "w", encoding="utf-8") as file_obj:
            json.dump(metadata, file_obj, ensure_ascii=False, indent=2)

        report_path: Optional[Path] = None
        if enable_html_report and external_module is not None:
            report_path = external_module.generate_html_report(
                output_base=output_base,
                metadata=metadata,
                embed_images=embed_images,
                include_tables=False,
            )
            if report_path is not None:
                report_path = Path(report_path)

        return PipelineComparisonRunResult(
            job_id=job_id,
            output_base=output_base,
            metadata_path=metadata_path,
            report_path=report_path,
            metadata=metadata,
        )

    def resolve_result_file(self, job_id: str, relative_path: str) -> Path:
        """Resolve a generated report asset path with traversal protection."""
        if not job_id:
            raise ValidationError(message="job_id is required.")
        if not relative_path:
            raise ValidationError(message="relative_path is required.")

        base_dir = None
        for candidate in candidate_job_roots(self.results_root, self._PIPELINE_RESULT_DIR, job_id, nested_dir="shared_analysis"):
            if candidate.exists() and candidate.is_dir():
                base_dir = candidate.resolve()
                break
        if base_dir is None:
            raise FileNotFoundError(f"Report job not found: {job_id}")

        target_path = (base_dir / relative_path).resolve()
        try:
            target_path.relative_to(base_dir)
        except ValueError as exc:
            raise ValidationError(
                message="Invalid path.",
                details={"relative_path": relative_path},
            ) from exc

        if not target_path.exists() or not target_path.is_file():
            raise FileNotFoundError(f"Result file not found: {relative_path}")

        return target_path


_pipeline_comparison_service: Optional[PipelineComparisonIntegrationService] = None


def get_pipeline_comparison_service(
    results_root: Optional[Path] = None,
) -> PipelineComparisonIntegrationService:
    """Get or create global pipeline comparison integration service."""
    global _pipeline_comparison_service

    if results_root is None:
        results_root = Path(__file__).resolve().parents[1] / "data" / "results"
    resolved_root = Path(results_root).resolve()

    if (
        _pipeline_comparison_service is None
        or _pipeline_comparison_service.results_root != resolved_root
    ):
        _pipeline_comparison_service = PipelineComparisonIntegrationService(resolved_root)
    return _pipeline_comparison_service
