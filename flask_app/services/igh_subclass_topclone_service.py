"""IGH subclass Top-N clone analysis based on sample PEP files."""

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
from scipy.stats import mannwhitneyu

from flask_app.services.figure_style import apply_publication_style, save_publication_png


TOP_NS = (10, 20, 50, 100)
SUBCLASS_ORDER = (
    "IGHM", "IGHD", "IGHA", "IGHA1", "IGHA2", "IGHG12", "IGHG34",
    "IGHG1", "IGHG2", "IGHG3", "IGHG4", "IGHGP", "IGHE",
)
C_CALL_PATTERN = re.compile(r"^(IGH(?:A\d*|G\d+|GP|D|E|M))")


@dataclass
class IgSubclassTopCloneReport:
    job_id: str
    output_base: Path
    png_paths: List[Path]
    csv_paths: List[Path]
    zip_path: Path
    metadata: Dict[str, object]


def normalize_c_call(value: object) -> tuple[str, str]:
    if value is None or pd.isna(value) or not str(value).strip():
        return "Unmatched", "empty"
    text = str(value).strip().upper()
    if text in {"NAN", "NONE", "NA"}:
        return "Unmatched", "empty"
    genes = {part.split("*")[0].strip() for part in re.split(r"[/,;|]+", text) if part.strip()}
    classes = sorted({match.group(1) for gene in genes if (match := C_CALL_PATTERN.match(gene))})
    if len(classes) == 1:
        return classes[0], "matched"
    if len(classes) > 1:
        return "Ambiguous", "ambiguous"
    return "Unmatched", "unmatched"


def _read_table(path: Path, *, dtype=None) -> pd.DataFrame:
    last_error = None
    options = {"low_memory": False, "sep": "\t" if path.name.lower().endswith((".tsv", ".tsv.gz")) else ","}
    if dtype is not None:
        options["dtype"] = dtype
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, **options)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ValueError(f"无法读取文件 {path.name}：{last_error}")


def _find_column(columns: Iterable[object], candidates: Iterable[str]) -> Optional[str]:
    by_lower = {str(column).strip().lower(): str(column) for column in columns}
    return next((by_lower[name.lower()] for name in candidates if name.lower() in by_lower), None)


def discover_igh_files(
    pep_paths: Iterable[str], batch_values: Optional[set[str]] = None
) -> List[tuple[Path, str, Optional[str]]]:
    selected: List[tuple[Path, str, Optional[str]]] = []
    seen = set()
    for raw in pep_paths:
        root = Path(str(raw)).expanduser()
        if not root.exists():
            continue
        candidates = [root] if root.is_file() else sorted(
            path for path in root.rglob("*")
            if path.is_file() and path.name.lower().endswith((".csv", ".csv.gz", ".tsv", ".tsv.gz"))
        )
        for path in candidates:
            if not path.is_file() or path.name.lower().startswith("profile"):
                continue
            stem = re.sub(r"\.(?:csv|tsv)(?:\.gz)?$", "", path.name, flags=re.IGNORECASE)
            upper = stem.upper()
            chain_in_name = any(
                upper.endswith(marker) or f"{marker}_" in upper or f"{marker}-" in upper
                for marker in ("__IGH", "_IGH", "-IGH")
            )
            chain_in_parent = any(parent.name.upper() == "IGH" for parent in path.parents[:4])
            if not (chain_in_name or chain_in_parent):
                continue
            resolved = str(path.resolve())
            if resolved in seen:
                continue
            seen.add(resolved)
            sample = re.sub(r"(?:__|[_-])IGH$", "", stem, flags=re.IGNORECASE)
            if chain_in_parent and sample == stem:
                sample = stem
            if sample:
                batch = None
                if batch_values:
                    matches = [
                        ancestor.name.strip()
                        for ancestor in path.parents
                        if ancestor.name.strip() in batch_values and ancestor.name.upper() != "IGH"
                    ]
                    if len(matches) > 1:
                        raise ValueError(f"IGH 文件路径中匹配到多个批次目录：{path}")
                    batch = next(iter(matches)) if matches else None
                selected.append((path.resolve(), sample, batch))
    return selected


def resolve_group_order(values: Iterable[str], requested_order: Optional[Iterable[str]] = None) -> List[str]:
    observed = list(dict.fromkeys(str(value).strip() for value in values if str(value).strip()))
    requested = [str(value).strip() for value in (requested_order or []) if str(value).strip()]
    resolved = [value for value in requested if value in observed]
    resolved.extend(value for value in observed if value not in resolved)
    return resolved


def _bh_fdr(values: Iterable[float]) -> np.ndarray:
    pvalues = np.asarray(list(values), dtype=float)
    qvalues = np.full(len(pvalues), np.nan)
    valid = np.flatnonzero(np.isfinite(pvalues))
    if not len(valid):
        return qvalues
    order = np.argsort(pvalues[valid])
    sorted_positions = valid[order]
    ordered = pvalues[sorted_positions]
    adjusted = ordered * len(ordered) / np.arange(1, len(ordered) + 1)
    adjusted = np.minimum.accumulate(adjusted[::-1])[::-1].clip(0, 1)
    qvalues[sorted_positions] = adjusted
    return qvalues


def _significance(value: float) -> str:
    if not np.isfinite(value):
        return "NA"
    return "***" if value <= 0.001 else "**" if value <= 0.01 else "*" if value <= 0.05 else ""


class IgSubclassTopCloneService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = Path(output_parent)

    def generate_report(
        self,
        *,
        pep_paths: Iterable[str],
        datapoint_path: str,
        group_column: str,
        group_order: Optional[Iterable[str]] = None,
        sample_column: Optional[str] = None,
        batch_field: Optional[str] = None,
        selected_samples: Optional[Iterable[str]] = None,
        output_name: Optional[str] = None,
    ) -> IgSubclassTopCloneReport:
        profile_path = Path(datapoint_path)
        if not profile_path.is_file():
            raise ValueError("样本指标表不存在")
        profile = _read_table(profile_path, dtype=str)
        if sample_column is None:
            sample_column = _find_column(profile.columns, ("sample", "sample_id", "sample_name", "id"))
        if not sample_column or sample_column not in profile.columns:
            raise ValueError("样本指标表缺少样本编号列")
        if not group_column or group_column not in profile.columns:
            raise ValueError("所选分组列不在样本指标表中")
        batch_field = str(batch_field or "").strip() or None
        if batch_field and batch_field not in profile.columns:
            raise ValueError("所选批次列不在样本指标表中")
        source_columns = [sample_column, group_column] + ([batch_field] if batch_field else [])
        metadata = profile[source_columns].copy()
        metadata.columns = ["sample", "group"] + (["batch"] if batch_field else [])
        metadata["sample"] = metadata["sample"].astype("string").str.strip()
        metadata["group"] = metadata["group"].astype("string").str.strip()
        if metadata["sample"].isna().any() or metadata["sample"].eq("").any():
            raise ValueError("样本指标表的样本编号存在空值")
        if metadata["group"].isna().any() or metadata["group"].eq("").any():
            raise ValueError("样本指标表的分组值存在空值")
        key_columns = ["sample"] + (["batch"] if batch_field else [])
        if batch_field:
            metadata["batch"] = metadata["batch"].astype("string").str.strip()
            if metadata["batch"].isna().any() or metadata["batch"].eq("").any():
                raise ValueError("样本指标表的批次值存在空值")
        if not batch_field and metadata["sample"].duplicated().any():
            raise ValueError("样本指标表存在重复样本编号，请选择批次字段")
        if metadata.duplicated(key_columns).any():
            raise ValueError("样本指标表存在重复的批次与样本组合")
        if selected_samples is not None:
            selected = {str(value).strip() for value in selected_samples if str(value).strip()}
            metadata = metadata[metadata["sample"].isin(selected)].copy()
        if metadata.empty:
            raise ValueError("所选样本没有可分析的数据")

        groups = resolve_group_order(metadata["group"].astype(str).tolist(), group_order)
        if len(groups) < 2:
            raise ValueError("亚类 TopClone 至少需要两个分组")
        batch_values = set(metadata["batch"].astype(str)) if batch_field else None
        files = discover_igh_files(pep_paths, batch_values)
        if not files:
            raise ValueError("所选克隆数据中未识别到 IGH 文件；请使用 IGH 链文件或按 IGH 目录组织输入")
        selected_ids = set(map(tuple, metadata[key_columns].astype(str).itertuples(index=False, name=None)))
        seen: Dict[tuple[str, ...], Path] = {}
        rows: List[pd.DataFrame] = []
        qc_rows: List[Dict[str, object]] = []
        call_rows: List[pd.DataFrame] = []
        discovered: List[str] = []
        processed: set[tuple[str, ...]] = set()
        for path, sample, batch in files:
            identity = (sample, batch) if batch_field else (sample,)
            if batch_field and batch is None and any(key[0] == sample for key in selected_ids):
                raise ValueError(f"IGH 文件 {path.name} 未能从目录路径匹配批次，请确保文件位于批次目录下")
            if identity in seen:
                raise ValueError(f"IGH 输入中存在重复批次与样本组合：{identity}")
            seen[identity] = path
            if identity not in selected_ids:
                qc_rows.append({"file": path.name, "sample": sample, **({"batch": batch} if batch_field else {}), "status": "not_selected_in_datapoint"})
                continue
            data, qc = self._read_igh(path, sample, batch)
            qc["status"] = "selected"
            processed.add(identity)
            discovered.extend(data.loc[~data["subclass"].isin(("Unmatched", "Ambiguous")), "subclass"].drop_duplicates().tolist())
            subclass_order = self._subclass_order(discovered)
            calculated = self._calculate_topclone(data, subclass_order)
            if not calculated.empty:
                rows.append(calculated.assign(sample=sample, **({"batch": batch} if batch_field else {})))
                call_rows.append(data.groupby(key_columns + ["subclass"], as_index=False)["copy"].sum())
            qc_rows.append(qc)
        missing = sorted(selected_ids.difference(processed))
        if missing:
            raise ValueError(f"以下所选批次与样本没有对应的 IGH 文件：{'、'.join('/'.join(key) for key in missing[:20])}")
        if not rows:
            raise ValueError("没有可用于 IGH 亚类 TopClone 的有效序列")

        order = self._subclass_order(discovered)
        long = pd.concat(rows, ignore_index=True).merge(metadata, on=key_columns, how="left", validate="many_to_one")
        long["group"] = long["group"].astype(str)
        comparisons = list(combinations(groups, 2))
        stats_rows: List[pd.DataFrame] = []
        for pair in comparisons:
            stats = self._compute_stats(long[long["group"].isin(pair)].copy(), list(pair))
            if not stats.empty:
                stats.insert(0, "comparison", f"{pair[0]} - {pair[1]}")
                stats.insert(1, "group_a", pair[0])
                stats.insert(2, "group_b", pair[1])
                stats_rows.append(stats)
        if not stats_rows:
            raise ValueError("所选分组没有可比较的亚类 TopClone 数据")
        stats_df = pd.concat(stats_rows, ignore_index=True)

        output_base = self.output_parent / (output_name or "igh-subclass-topclone")
        output_base.mkdir(parents=True, exist_ok=True)
        file_dir, figure_dir = output_base / "file", output_base / "figure"
        file_dir.mkdir(parents=True, exist_ok=True)
        figure_dir.mkdir(parents=True, exist_ok=True)
        wide = long.pivot_table(index=key_columns + ["group"], columns=["top_n", "subclass"], values="fraction")
        wide.columns = [f"top{int(n)}{subclass}" for n, subclass in wide.columns]
        wide_path = file_dir / "subclass_topclone.csv"
        wide.reset_index().to_csv(wide_path, index=False)
        stats_path = file_dir / "subclass_topclone_statistics.csv"
        stats_df.to_csv(stats_path, index=False)
        qc_path = file_dir / "subclass_topclone_input_qc.csv"
        pd.DataFrame(qc_rows).to_csv(qc_path, index=False)
        subclass_totals_path = file_dir / "subclass_copy_totals.csv"
        (pd.concat(call_rows, ignore_index=True) if call_rows else pd.DataFrame(columns=key_columns + ["subclass", "copy"]))\
            .merge(metadata, on=key_columns, how="left", validate="many_to_one")\
            .to_csv(subclass_totals_path, index=False)
        png_paths = self._plot(stats_df, comparisons, order, figure_dir)
        metadata_json: Dict[str, object] = {
            "analysis_type": "igh_subclass_topclone", "group_column": group_column,
            "group_order": groups, "comparisons": [list(pair) for pair in comparisons],
            "sample_count": int(len(metadata)), "batch_field": batch_field,
            "batch_count": int(metadata["batch"].nunique()) if batch_field else None,
            "sample_counts_by_group": {group: int((metadata["group"].astype(str) == group).sum()) for group in groups},
            "input_file_count": len(files), "selected_igh_file_count": len(processed),
            "top_n_values": list(TOP_NS), "denominator": "all copy counts within each IGH subclass and sample",
            "statistics": "two-sided Mann-Whitney U; BH FDR across subclass and top-N rows within each group comparison",
            "subclasses": order, "unmatched_or_ambiguous_rows_are_excluded_from_subclass_totals": True,
        }
        metadata_path = output_base / "analysis_metadata.json"
        metadata_path.write_text(json.dumps(metadata_json, ensure_ascii=False, indent=2), encoding="utf-8")
        zip_path = output_base / "IGH_亚类TopClone分析结果.zip"
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in [wide_path, stats_path, qc_path, subclass_totals_path, *png_paths, metadata_path]:
                bundle.write(path, path.relative_to(output_base).as_posix())
        return IgSubclassTopCloneReport(output_base.name, output_base, png_paths,
                                        [wide_path, stats_path, qc_path, subclass_totals_path],
                                        zip_path, metadata_json)

    @staticmethod
    def _read_igh(path: Path, sample: str, batch: Optional[str] = None):
        raw = _read_table(path)
        c_call = _find_column(raw.columns, ("c_call", "c_call_IGH", "isotype", "C"))
        cdr3 = _find_column(raw.columns, ("CDR3(pep)", "cdr3_aa", "cdr3", "CDR3"))
        copy = _find_column(raw.columns, ("copy", "copies", "cloneCount", "count"))
        missing = [label for label, value in (("c_call", c_call), ("CDR3", cdr3), ("copy", copy)) if value is None]
        if missing:
            raise ValueError(f"{path.name} 缺少必要列：{'、'.join(missing)}")
        data = raw[[c_call, cdr3, copy]].copy()
        data.columns = ["c_call", "cdr3", "copy"]
        data["copy"] = pd.to_numeric(data["copy"], errors="coerce")
        data["cdr3"] = data["cdr3"].astype("string").str.strip()
        data = data.replace([np.inf, -np.inf], np.nan).dropna(subset=["cdr3", "copy"])
        data = data[data["cdr3"].ne("") & data["copy"].ge(0)].copy()
        data["subclass"] = data["c_call"].map(lambda value: normalize_c_call(value)[0])
        data["sample"] = sample
        if batch is not None:
            data["batch"] = batch
        qc = {
            "file": path.name, "sample": sample, "n_rows": int(len(data)),
            "n_unmatched": int((data["subclass"] == "Unmatched").sum()),
            "n_ambiguous": int((data["subclass"] == "Ambiguous").sum()),
            "total_copy": float(data["copy"].sum()),
        }
        if batch is not None:
            qc["batch"] = batch
        return data, qc

    @staticmethod
    def _subclass_order(discovered: Iterable[str]) -> List[str]:
        present = set(map(str, discovered))
        order = [item for item in SUBCLASS_ORDER if item in present]
        order.extend(sorted(present.difference(order)))
        return order

    @staticmethod
    def _calculate_topclone(data: pd.DataFrame, subclass_order: Iterable[str]) -> pd.DataFrame:
        classified = data[data["subclass"].isin(subclass_order) & ~data["subclass"].isin(("Unmatched", "Ambiguous"))]
        output = []
        for subclass in subclass_order:
            subset = classified[classified["subclass"] == subclass]
            if subset.empty:
                continue
            clones = subset.groupby("cdr3", as_index=False)["copy"].sum().sort_values("copy", ascending=False)
            total = float(subset["copy"].sum())
            for top_n in TOP_NS:
                top_copy = float(clones.head(top_n)["copy"].sum())
                output.append({"subclass": subclass, "top_n": int(top_n), "top_clone_copy": top_copy,
                               "subclass_total_copy": total, "fraction": top_copy / total if total else np.nan,
                               "n_unique_cdr3": int(clones.shape[0])})
        return pd.DataFrame(output)

    @staticmethod
    def _compute_stats(data: pd.DataFrame, groups: List[str]) -> pd.DataFrame:
        rows = []
        for (subclass, top_n), subset in data.groupby(["subclass", "top_n"], observed=True):
            first = subset.loc[subset["group"] == groups[0], "fraction"].dropna()
            second = subset.loc[subset["group"] == groups[1], "fraction"].dropna()
            pvalue = mannwhitneyu(first, second, alternative="two-sided").pvalue if len(first) and len(second) else np.nan
            rows.append({
                "subclass": subclass, "top_n": int(top_n), f"n_{groups[0]}": len(first), f"n_{groups[1]}": len(second),
                f"median_{groups[0]}": first.median() if len(first) else np.nan,
                f"median_{groups[1]}": second.median() if len(second) else np.nan,
                f"median_delta_{groups[1]}_minus_{groups[0]}": second.median() - first.median() if len(first) and len(second) else np.nan,
                "p_value": pvalue,
            })
        stats = pd.DataFrame(rows)
        if stats.empty:
            return stats
        stats["fdr"] = _bh_fdr(stats["p_value"])
        stats["q_value"] = stats["fdr"]
        stats["raw_p_significance"] = stats["p_value"].map(_significance)
        stats["fdr_significance"] = stats["fdr"].map(_significance)
        stats["label"] = stats["raw_p_significance"]
        return stats

    @staticmethod
    def _plot(stats: pd.DataFrame, comparisons, subclass_order, output_dir: Path) -> List[Path]:
        paths = []
        apply_publication_style(font_size=8.5)
        colors = ["#4E79A7", "#F5F5F2", "#C96557"]
        from matplotlib.colors import LinearSegmentedColormap
        cmap = LinearSegmentedColormap.from_list("igh_subclass_effect", colors)
        for group_a, group_b in comparisons:
            subset = stats[(stats["group_a"] == group_a) & (stats["group_b"] == group_b)]
            if subset.empty:
                # `group_a/group_b` are added after this method's input is built below.
                subset = stats
            delta_col = next((column for column in subset.columns if column.startswith("median_delta_") and column.endswith("_minus_" + group_a)), None)
            if delta_col is None:
                continue
            delta = subset.pivot(index="subclass", columns="top_n", values=delta_col).reindex(index=[name for name in subclass_order if name in set(subset["subclass"])], columns=list(TOP_NS))
            labels = subset.pivot(index="subclass", columns="top_n", values="label").reindex(index=delta.index, columns=list(TOP_NS))
            values = delta.to_numpy(dtype=float)
            finite = np.abs(values[np.isfinite(values)])
            vmax = max(float(np.max(finite)) if len(finite) else 0.0, 0.02)
            fig, ax = plt.subplots(figsize=(max(6.8, 1.0 * len(TOP_NS) + 3.0), max(4.2, 0.48 * len(delta.index) + 1.8)))
            image = ax.imshow(np.ma.masked_invalid(values), cmap=cmap, vmin=-vmax, vmax=vmax, aspect="auto")
            for i in range(len(delta.index)):
                for j in range(len(TOP_NS)):
                    if np.isfinite(values[i, j]):
                        ax.text(j, i, str(labels.iloc[i, j]), ha="center", va="center", fontsize=9, fontweight="bold", color="#344054")
            ax.set_xticks(range(len(TOP_NS)), [f"前 {value} 位" for value in TOP_NS])
            ax.set_yticks(range(len(delta.index)), delta.index)
            ax.set_title(f"{group_b} 组相对 {group_a} 组的亚类 TopClone 差异", loc="left", fontsize=12, fontweight="bold", pad=12)
            ax.set_xlabel("各免疫球蛋白亚类内排名")
            ax.set_ylabel("免疫球蛋白亚类")
            fig.colorbar(image, ax=ax, fraction=0.045, pad=0.04, label=f"中位数差异（{group_b} − {group_a}）")
            ax.spines[["top", "right"]].set_visible(False)
            fig.tight_layout()
            target = output_dir / f"subclass_topclone_effect_{_safe_name(group_b)}_vs_{_safe_name(group_a)}.png"
            save_publication_png(fig, target, dpi=300, bbox_inches="tight")
            plt.close(fig)
            paths.append(target)
        return paths


def _safe_name(value: str) -> str:
    clean = re.sub(r"[^\w.-]+", "_", str(value), flags=re.UNICODE).strip("._")
    return clean or "group"
