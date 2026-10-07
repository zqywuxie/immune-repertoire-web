"""Class-switch recombination summaries from datapoint CSR ratio fields."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.stats import kruskal, mannwhitneyu

from flask_app.services.figure_style import PALETTE, apply_publication_style, save_publication_png


CANONICAL_CLASSES = [
    "IGHM", "IGHD", "IGHM_IGHD", "IGHA", "IGHA1", "IGHA2", "IGHG12",
    "IGHG34", "IGHG1", "IGHG2", "IGHG3", "IGHG4", "IGHGP", "IGHE",
]
FIELD_PATTERN = re.compile(
    r"^([A-Za-z0-9_]+)-([A-Za-z0-9_]+)_(CSR_ratio|CSR0|CSR1)$", re.IGNORECASE
)
MEASURE_PREFERENCE = ("CSR_RATIO", "CSR1", "CSR0")
MIN_GROUP_N = 2
PSEUDOCOUNT = 1e-6


@dataclass
class ProfileCsrReport:
    job_id: str
    output_base: Path
    png_paths: List[Path]
    csv_paths: List[Path]
    zip_path: Path
    metadata: Dict[str, object]


def discover_csr_measures(columns: Iterable[str]) -> Dict[str, List[str]]:
    found: Dict[str, List[str]] = {key: [] for key in ("CSR_ratio", "CSR1", "CSR0")}
    for column in map(str, columns):
        match = FIELD_PATTERN.fullmatch(column)
        if match:
            measure = match.group(3).upper()
            key = "CSR_ratio" if measure == "CSR_RATIO" else measure
            found[key].append(column)
    rank = {name: index for index, name in enumerate(CANONICAL_CLASSES)}
    for key, fields in found.items():
        fields.sort(key=lambda field: _field_sort_key(field, rank))
    return {key: value for key, value in found.items() if value}


def _field_sort_key(field: str, rank: Dict[str, int]):
    left, right, _measure = FIELD_PATTERN.fullmatch(field).groups()
    left, right = left.upper(), right.upper()
    return rank.get(left, len(rank)), rank.get(right, len(rank)), left, right, field


def _classes_for_fields(fields: Iterable[str]) -> List[str]:
    classes = set()
    for field in fields:
        match = FIELD_PATTERN.fullmatch(field)
        classes.update((match.group(1).upper(), match.group(2).upper()))
    ordered = [name for name in CANONICAL_CLASSES if name in classes]
    ordered.extend(sorted(classes.difference(ordered)))
    return ordered


def _pair_label(field: str) -> str:
    match = FIELD_PATTERN.fullmatch(field)
    return "-".join(sorted((match.group(1).upper(), match.group(2).upper())))


def _bh_fdr(values: Iterable[float]) -> np.ndarray:
    pvalues = np.asarray(list(values), dtype=float)
    qvalues = np.full_like(pvalues, np.nan)
    valid = np.flatnonzero(~np.isnan(pvalues))
    if not len(valid):
        return qvalues
    sorted_valid = valid[np.argsort(pvalues[valid])]
    ordered = pvalues[sorted_valid]
    adjusted = ordered * len(ordered) / np.arange(1, len(ordered) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1]
    qvalues[sorted_valid] = np.clip(adjusted, 0, 1)
    return qvalues


def _read_table(path: Path) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, low_memory=False)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ValueError(f"无法读取样本指标表：{last_error}")


class ProfileCsrService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = Path(output_parent)

    def generate_report(
        self,
        *,
        datapoint_path: str,
        group_column: str,
        measure: str = "auto",
        group_order: Optional[Iterable[str]] = None,
        sample_column: Optional[str] = None,
        selected_samples: Optional[Iterable[str]] = None,
        output_name: Optional[str] = None,
    ) -> ProfileCsrReport:
        source = Path(datapoint_path)
        if not source.is_file():
            raise ValueError("样本指标表不存在")
        frame = _read_table(source)
        if sample_column is None:
            sample_column = next(
                (str(name) for name in frame.columns if str(name).strip().lower() in {"sample", "sample_id", "sample_name", "id"}),
                "",
            )
        if not sample_column or sample_column not in frame.columns:
            raise ValueError("样本指标表缺少样本编号列")
        if not group_column or group_column not in frame.columns:
            raise ValueError("所选分组列不在样本指标表中")

        available = discover_csr_measures(frame.columns)
        requested = str(measure or "auto").strip().upper()
        if requested == "AUTO":
            requested = next((item for item in MEASURE_PREFERENCE if ("CSR_ratio" if item == "CSR_RATIO" else item) in available), "")
        selected_measure = "CSR_ratio" if requested == "CSR_RATIO" else requested
        fields = available.get(selected_measure, [])
        if not fields:
            available_text = "、".join(available) or "无"
            raise ValueError(f"没有可用的 CSR 指标列（当前可用：{available_text}）")

        data = frame[[sample_column, group_column, *fields]].copy()
        data.columns = ["sample", "group", *fields]
        data["sample"] = data["sample"].astype("string").str.strip()
        data["group"] = data["group"].astype("string").str.strip()
        if data["sample"].isna().any() or data["sample"].eq("").any():
            raise ValueError("样本编号存在空值")
        if data["group"].isna().any() or data["group"].eq("").any():
            raise ValueError("分组列存在空值")
        if data["sample"].duplicated().any():
            raise ValueError("样本指标表存在重复样本编号，请先明确批次与样本对应关系")
        if selected_samples is not None:
            selected = {str(item).strip() for item in selected_samples if str(item).strip()}
            data = data[data["sample"].isin(selected)].copy()
        if data.empty:
            raise ValueError("所选样本没有可分析的数据")

        # Match the pipeline's policy: pandas-numeric columns receive NA -> 0;
        # mixed/text columns are coerced later and invalid observations are dropped.
        for field in fields:
            values = data[field]
            numeric = pd.to_numeric(values, errors="coerce")
            data[field] = numeric.fillna(0.0) if pd.api.types.is_numeric_dtype(values) else numeric
        observed = list(dict.fromkeys(data["group"].astype(str).tolist()))
        requested_order = [str(item).strip() for item in (group_order or []) if str(item).strip()]
        groups = [group for group in requested_order if group in observed]
        groups.extend(group for group in observed if group not in groups)
        classes = _classes_for_fields(fields)
        pairs = list(combinations(groups, 2))

        median_rows: List[Dict[str, object]] = []
        medians: Dict[str, Dict[str, float]] = {}
        for group in groups:
            group_data = data[data["group"].astype(str) == group]
            medians[group] = {}
            for field in fields:
                values = group_data[field].dropna()
                median = float(values.median()) if len(values) >= MIN_GROUP_N else np.nan
                label = _pair_label(field)
                medians[group][field] = median
                median_rows.append({"group": group, "csr_pair": label, "field": field, "n": int(len(values)), "median": median})
        median_df = pd.DataFrame(median_rows)

        stats_rows: List[Dict[str, object]] = []
        for group_a, group_b in pairs:
            rows = []
            for field in fields:
                values_a = data.loc[data["group"].astype(str) == group_a, field].dropna()
                values_b = data.loc[data["group"].astype(str) == group_b, field].dropna()
                pvalue = float(mannwhitneyu(values_a, values_b, alternative="two-sided").pvalue) if len(values_a) >= MIN_GROUP_N and len(values_b) >= MIN_GROUP_N else np.nan
                median_a = float(values_a.median()) if len(values_a) else np.nan
                median_b = float(values_b.median()) if len(values_b) else np.nan
                effect = float(np.log2((median_a + PSEUDOCOUNT) / (median_b + PSEUDOCOUNT))) if np.isfinite(median_a) and np.isfinite(median_b) else np.nan
                rows.append({
                    "comparison": f"{group_a} - {group_b}", "group_a": group_a, "group_b": group_b,
                    "csr_pair": _pair_label(field), "field": field, "n_a": int(len(values_a)), "n_b": int(len(values_b)),
                    "median_a": median_a, "median_b": median_b,
                    "delta_median": median_a - median_b if np.isfinite(median_a) and np.isfinite(median_b) else np.nan,
                    "log2_median_ratio": effect, "effect_size_method": "log2((median_a + pseudocount) / (median_b + pseudocount))",
                    "effect_size_pseudocount": PSEUDOCOUNT, "pvalue": pvalue,
                })
            qvalues = _bh_fdr(row["pvalue"] for row in rows)
            for row, qvalue in zip(rows, qvalues):
                row["qvalue"] = qvalue
                row["p_value"] = row["pvalue"]
                row["q_value"] = qvalue
                row["significance_value"] = row["pvalue"]
                row["significance_method"] = "pvalue"
                row["marker"] = "" if pd.isna(row["pvalue"]) or row["pvalue"] >= 0.05 else "***" if row["pvalue"] <= 0.001 else "**" if row["pvalue"] <= 0.01 else "*"
                stats_rows.append(row)
        stats_df = pd.DataFrame(stats_rows)

        kruskal_rows = []
        for field in fields:
            samples = []
            group_ns = {}
            for group in groups:
                values = data.loc[data["group"].astype(str) == group, field].dropna()
                group_ns[group] = int(len(values))
                if len(values) >= MIN_GROUP_N:
                    samples.append(values.to_numpy(dtype=float))
            pvalue = float(kruskal(*samples).pvalue) if len(samples) >= 2 else np.nan
            kruskal_rows.append({"csr_pair": _pair_label(field), "field": field, "kruskal_pvalue": pvalue, **{f"n_{group}": group_ns[group] for group in groups}})
        kruskal_df = pd.DataFrame(kruskal_rows)
        if not kruskal_df.empty:
            kruskal_df["kruskal_qvalue"] = _bh_fdr(kruskal_df["kruskal_pvalue"])

        qc_rows = []
        for subtype in classes:
            subtype_fields = [field for field in fields if subtype in {part.upper() for part in FIELD_PATTERN.fullmatch(field).groups()[:2]}]
            values = data[subtype_fields] if subtype_fields else pd.DataFrame(index=data.index)
            qc_rows.append({"subtype": subtype, "available_pairs": len(subtype_fields), "expected_pairs": max(len(classes) - 1, 0), "valid_n": int(values.notna().any(axis=1).sum()) if subtype_fields else 0, "nonzero_n": int(values.fillna(0).ne(0).any(axis=1).sum()) if subtype_fields else 0, "fields": ";".join(subtype_fields), "skipped_reason": "" if subtype_fields else "no CSR field in input"})
        qc_df = pd.DataFrame(qc_rows)

        output_base = self.output_parent / (output_name or "csr-report")
        output_base.mkdir(parents=True, exist_ok=True)
        file_dir, figure_dir = output_base / "file", output_base / "figure"
        file_dir.mkdir(parents=True, exist_ok=True)
        figure_dir.mkdir(parents=True, exist_ok=True)
        csv_paths = [file_dir / "CSR_group_median_matrix_source.csv", file_dir / "CSR_pairwise_mannwhitney_stats.csv", file_dir / "CSR_kruskal_fdr.csv", file_dir / "CSR_subtype_discovery_qc.csv"]
        for table, path in zip((median_df, stats_df, kruskal_df, qc_df), csv_paths):
            table.to_csv(path, index=False)
        png_paths = self._plot(medians, stats_df, groups, fields, classes, figure_dir)
        metadata = {
            "analysis_type": "csr", "measure": selected_measure, "group_column": group_column,
            "group_order": groups, "sample_count": int(len(data)), "sample_counts_by_group": {group: int((data["group"].astype(str) == group).sum()) for group in groups},
            "classes": classes, "csr_field_count": len(fields), "comparisons": [list(pair) for pair in pairs],
            "missing_value_policy": "numeric missing values are treated as 0, matching the reference script",
            "minimum_group_n": MIN_GROUP_N, "effect_size_pseudocount": PSEUDOCOUNT,
        }
        metadata_path = output_base / "analysis_metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        archive = output_base / "CSR_免疫球蛋白类别转换分析.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in [*csv_paths, *png_paths, metadata_path]:
                bundle.write(path, path.relative_to(output_base).as_posix())
        return ProfileCsrReport(output_base.name, output_base, png_paths, csv_paths, archive, metadata)

    @staticmethod
    def _plot(medians, stats_df, groups, fields, classes, figure_dir):
        if not fields or not classes:
            return []
        field_pairs = {field: tuple(part.upper() for part in FIELD_PATTERN.fullmatch(field).groups()[:2]) for field in fields}
        positions = {name: index for index, name in enumerate(classes)}
        outputs = []
        comparisons = [("group", (group,)) for group in groups]
        comparisons.extend(("difference", tuple(pair)) for pair in combinations(groups, 2))
        apply_publication_style(font_size=8.5)
        palette = ["#DCEBF4", "#F5F5F2", "#E9C4BB"]
        from matplotlib.colors import LinearSegmentedColormap
        cmap = LinearSegmentedColormap.from_list("csr_platform", palette)
        for kind, selection in comparisons:
            values_by_pair = {}
            markers = {}
            if kind == "group":
                group = selection[0]
                for field in fields:
                    values_by_pair[field_pairs[field]] = medians[group].get(field, np.nan)
                title, label, filename = f"{group} 组 CSR 中位数", "CSR 中位数", f"CSR_association_{_safe_name(group)}.png"
                v = [value for value in values_by_pair.values() if np.isfinite(value)]
                maximum = float(np.quantile(v, 0.95)) if v else 1.0
                vmin, vmax = 0.0, maximum if maximum > 0 else 1.0
            else:
                group_a, group_b = selection
                subset = stats_df[(stats_df["group_a"] == group_a) & (stats_df["group_b"] == group_b)]
                for row in subset.to_dict("records"):
                    pair = field_pairs[row["field"]]
                    values_by_pair[pair] = row["log2_median_ratio"]
                    markers[pair] = row["marker"]
                title, label, filename = f"{group_a} 与 {group_b} 组 CSR 差异", "log2 中位数比值", f"CSR_differential_{_safe_name(group_a)}_vs_{_safe_name(group_b)}.png"
                v = [abs(value) for value in values_by_pair.values() if np.isfinite(value)]
                maximum = float(np.quantile(v, 0.95)) if v else 1.0
                maximum = maximum if maximum > 0 else 1.0
                vmin, vmax = -maximum, maximum

            matrix = np.full((len(classes), len(classes)), np.nan)
            annot = np.full((len(classes), len(classes)), "", dtype=object)
            for pair, value in values_by_pair.items():
                i, j = positions[pair[0]], positions[pair[1]]
                row_idx, col_idx = max(i, j), min(i, j)
                matrix[row_idx, col_idx] = value
                if kind == "difference":
                    annot[row_idx, col_idx] = markers.get(pair, "")
            fig, ax = plt.subplots(figsize=(max(4.8, len(classes) * 0.42), max(4.5, len(classes) * 0.38)))
            masked = np.ma.masked_invalid(matrix)
            image = ax.imshow(masked, cmap=cmap, vmin=vmin, vmax=vmax, aspect="equal")
            for i in range(len(classes)):
                for j in range(len(classes)):
                    if i > j and np.isfinite(matrix[i, j]):
                        text = f"{matrix[i, j]:.2f}" if kind == "group" else (annot[i, j] or f"{matrix[i, j]:.2f}")
                        ax.text(j, i, text, ha="center", va="center", fontsize=7, color="#334155")
            ax.set_xticks(range(len(classes)), classes, rotation=45, ha="right")
            ax.set_yticks(range(len(classes)), classes)
            ax.set_title(title, loc="left", fontsize=11, fontweight="bold", pad=10)
            ax.set_xlabel("免疫球蛋白类别")
            ax.set_ylabel("免疫球蛋白类别")
            fig.colorbar(image, ax=ax, fraction=0.046, pad=0.04, label=label)
            ax.spines[["top", "right"]].set_visible(False)
            fig.tight_layout()
            target = figure_dir / filename
            save_publication_png(fig, target, dpi=300, bbox_inches="tight")
            plt.close(fig)
            outputs.append(target)
        return outputs


def _safe_name(value: str) -> str:
    name = re.sub(r"[^\w.-]+", "_", str(value), flags=re.UNICODE).strip("._")
    return name or "group"
