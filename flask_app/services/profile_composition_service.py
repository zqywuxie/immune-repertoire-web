"""Sample-level receptor-chain and immunoglobulin-subclass composition plots."""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from flask_app.services.figure_style import PALETTE, apply_publication_style, save_publication_png


CHAIN_COLUMNS = {
    "TRA": ("TRA_Percent", "TRA_percent_reads"),
    "TRB": ("TRB_Percent", "TRB_percent_reads"),
    "TRD": ("TRD_Percent", "TRD_percent_reads"),
    "TRG": ("TRG_Percent", "TRG_percent_reads"),
    "IGH": ("IGH_Percent", "IGH_percent_reads"),
    "IGK": ("IGK_Percent", "IGK_percent_reads"),
    "IGL": ("IGL_Percent", "IGL_percent_reads"),
}
CHAIN_COLORS = ["#4E79A7", "#79A9CF", "#9CC9D5", "#A8D5C2", "#8F8CC2", "#B3A7D1", "#D5CDE5"]
SUBCLASS_ORDER = ["IGHM", "IGHD", "IGHA", "IGHA1", "IGHA2", "IGHG12", "IGHG34", "IGHG3", "IGHG4", "IGHGP", "IGHE"]
SUBCLASS_COLORS = ["#E58A72", "#F0A77E", "#F4C58A", "#D97983", "#C88AA1", "#AD88B5", "#8F80B8", "#D8C4D8"]


@dataclass
class ProfileCompositionReport:
    job_id: str
    output_base: Path
    png_paths: List[Path]
    csv_paths: List[Path]
    zip_path: Path
    metadata: Dict[str, object]


def _read_profile(path: Path) -> pd.DataFrame:
    last_error: Optional[Exception] = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            columns = pd.read_csv(path, encoding=encoding, nrows=0).columns
            sample_column = next((name for name in columns if str(name).strip().lower() in {"sample", "sample_id", "sample_name", "id"}), "sample")
            return pd.read_csv(path, encoding=encoding, dtype={sample_column: "string"})
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ValueError(f"无法读取样本指标表：{last_error}")


def discover_composition_columns(columns: Iterable[str], measure: str = "reads") -> Dict[str, List[str]]:
    names = [str(column) for column in columns]
    chains = [next((candidate for candidate in aliases if candidate in names), None) for aliases in CHAIN_COLUMNS.values()]
    chains = [column for column in chains if column]
    pattern = re.compile(rf"^((?:IGH[A-Z0-9]+)(?:_IGH[A-Z0-9]+)*)_percent_by_{re.escape(measure)}$", re.IGNORECASE)
    tokens = [match.group(1) for column in names if (match := pattern.match(column))]
    if not tokens and measure == "reads":
        tokens = [column[:-len("_percent_by_reads")] for column in names if re.match(r"^IGH[A-Z0-9]+_percent_by_reads$", column, re.IGNORECASE)]
    requested = set(tokens)
    subclasses = [token for token in SUBCLASS_ORDER if token in requested]
    subclasses += sorted(requested.difference(subclasses))
    return {"chains": chains, "subclass_columns": [f"{token}_percent_by_{measure}" for token in subclasses]}


class ProfileCompositionService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = Path(output_parent)

    def generate_report(
        self,
        *,
        datapoint_path: str,
        group_column: str,
        group_order: Optional[Iterable[str]] = None,
        sample_column: Optional[str] = None,
        measure: str = "reads",
        selected_samples: Optional[Iterable[str]] = None,
        selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
        output_name: Optional[str] = None,
    ) -> ProfileCompositionReport:
        if measure not in {"reads", "clone"}:
            raise ValueError("亚类统计口径必须为 reads 或 clone")
        source = Path(datapoint_path)
        if not source.is_file():
            raise ValueError("样本指标表不存在")
        frame = _read_profile(source)
        if sample_column is None:
            sample_column = next((name for name in frame.columns if str(name).strip().lower() in {"sample", "sample_id", "sample_name", "id"}), "")
        if not sample_column or sample_column not in frame.columns:
            raise ValueError("样本指标表缺少样本编号列")
        if not group_column or group_column not in frame.columns:
            raise ValueError("所选分组列不在样本指标表中")

        sample_ids = frame[sample_column].astype("string").str.strip()
        groups = frame[group_column].astype("string").str.strip()
        if sample_ids.isna().any() or sample_ids.eq("").any() or sample_ids.duplicated().any():
            raise ValueError("样本编号必须非空且唯一")
        if groups.isna().any() or groups.eq("").any():
            raise ValueError("分组列存在空值，请先补齐或排除对应样本")
        frame[sample_column] = sample_ids
        frame[group_column] = groups

        if selected_samples_by_group:
            allowed = {str(group): {str(sample).strip() for sample in samples} for field in selected_samples_by_group.values() for group, samples in field.items()}
            if allowed:
                mask = [sample in allowed.get(group, set()) for sample, group in zip(sample_ids, groups)]
                frame = frame.loc[mask].copy()
        elif selected_samples:
            selected = {str(sample).strip() for sample in selected_samples}
            frame = frame.loc[frame[sample_column].isin(selected)].copy()
        if frame.empty:
            raise ValueError("当前样本筛选没有可分析的样本")

        observed = list(dict.fromkeys(frame[group_column].astype(str)))
        requested = [str(group).strip() for group in (group_order or []) if str(group).strip()]
        group_levels = [group for group in requested if group in observed] + [group for group in observed if group not in requested]
        if any(group not in group_levels for group in observed):
            raise ValueError("分组顺序缺少当前样本中的组别")
        frame["__group_order"] = pd.Categorical(frame[group_column], categories=group_levels, ordered=True)

        columns = discover_composition_columns(frame.columns, measure)
        datasets: List[tuple[str, List[str], List[str], str]] = []
        if columns["chains"]:
            chain_labels = [next(name for name, aliases in CHAIN_COLUMNS.items() if column in aliases) for column in columns["chains"]]
            datasets.append(("受体链构成", columns["chains"], chain_labels, "受体链构成"))
        if columns["subclass_columns"]:
            subclass_labels = [column[: -len(f"_percent_by_{measure}")].replace("IGH", "Ig", 1) for column in columns["subclass_columns"]]
            datasets.append(("免疫球蛋白亚类构成", columns["subclass_columns"], subclass_labels, "免疫球蛋白亚类构成"))
        if not datasets:
            raise ValueError(f"未检测到链构成列或 {measure} 口径的免疫球蛋白亚类构成列")

        job_id = re.sub(r"[^A-Za-z0-9_-]+", "_", output_name or source.stem).strip("_") or "profile_composition"
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=False)
        png_paths: List[Path] = []
        csv_paths: List[Path] = []
        qc_rows: Optional[pd.DataFrame] = None

        for title, component_cols, labels, y_label in datasets:
            plot_frame, long_frame, qc = self._prepare(frame, sample_column, group_column, component_cols, group_levels)
            if qc_rows is None:
                qc_rows = qc
            colors = CHAIN_COLORS if title == "受体链构成" else SUBCLASS_COLORS
            png = output_base / f"{title}.png"
            self._plot(plot_frame, long_frame, component_cols, labels, colors, group_levels, group_column, y_label, png)
            png_paths.append(png)
            data_csv = output_base / f"{title}_样本构成.csv"
            long_frame.rename(columns={"sample": sample_column, "group": group_column}).to_csv(data_csv, index=False, encoding="utf-8-sig")
            csv_paths.append(data_csv)

        assert qc_rows is not None
        qc_path = output_base / "样本质量与排序.csv"
        qc_rows.rename(columns={"sample": sample_column, "group": group_column}).to_csv(qc_path, index=False, encoding="utf-8-sig")
        csv_paths.append(qc_path)
        metadata: Dict[str, object] = {
            "analysis": "样本级构成图",
            "datapoint_path": str(source.resolve()),
            "sample_column": sample_column,
            "group_column": group_column,
            "group_order": group_levels,
            "sample_count": int(len(frame)),
            "group_counts": frame[group_column].value_counts().reindex(group_levels).dropna().astype(int).to_dict(),
            "subclass_measure": measure,
            "missing_components_are_zero": True,
            "closure": "每个样本的选中构成分量按其合计值归一化至 100%",
            "components": {title: labels for title, _, labels, _ in datasets},
        }
        metadata_path = output_base / "analysis_metadata.json"
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
        archive = output_base / "profile_composition_results.zip"
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as bundle:
            for path in [*png_paths, *csv_paths, metadata_path]:
                bundle.write(path, arcname=path.name)
        return ProfileCompositionReport(job_id, output_base, png_paths, csv_paths, archive, metadata)

    @staticmethod
    def _prepare(frame, sample_column, group_column, component_cols, group_levels):
        data = frame[[sample_column, group_column, *component_cols]].copy()
        data.columns = ["sample", "group", *component_cols]
        matrix = data[component_cols].apply(pd.to_numeric, errors="coerce")
        if (matrix < 0).any().any():
            raise ValueError("构成百分比不能为负数")
        missing_count = matrix.isna().sum(axis=1)
        matrix = matrix.fillna(0.0)
        totals = matrix.sum(axis=1)
        if (~np.isfinite(totals)).any() or (totals <= 0).any():
            raise ValueError("每个样本至少要有一个大于 0 的有效构成分量")
        matrix = matrix.div(totals, axis=0)
        data[component_cols] = matrix
        data["__missing_count"] = missing_count
        data["__total_before"] = totals
        data["__group_order"] = pd.Categorical(data["group"], categories=group_levels, ordered=True)
        data = data.sort_values(["__group_order", *component_cols, "sample"], ascending=[True] + [False] * len(component_cols) + [True], kind="mergesort").reset_index(drop=True)
        data["plot_order"] = np.arange(1, len(data) + 1)
        long = data.melt(id_vars=["sample", "group", "plot_order"], value_vars=component_cols, var_name="component", value_name="fraction")
        long["component"] = pd.Categorical(long["component"], categories=component_cols, ordered=True)
        long = long.sort_values(["plot_order", "component"], kind="mergesort").reset_index(drop=True)
        long["percent"] = long["fraction"] * 100.0
        long["component"] = long["component"].astype(str)
        qc = pd.DataFrame({
            "sample": data["sample"], "group": data["group"],
            "missing_components_replaced_with_zero": data["__missing_count"].to_numpy(),
            "total_before_closure": data["__total_before"].to_numpy(),
            "total_after_closure": data[component_cols].sum(axis=1).to_numpy(),
            "plot_order": data["plot_order"].to_numpy(),
        })
        return data, long, qc

    @staticmethod
    def _plot(data, long, component_cols, labels, colors, group_levels, group_column, y_label, output_path):
        apply_publication_style(font_size=8.5)
        fig, ax = plt.subplots(figsize=(7.2, 4.8))
        positions = data["plot_order"].to_numpy()
        bottoms = np.zeros(len(data), dtype=float)
        for index, (column, label) in enumerate(zip(component_cols, labels)):
            values = data[column].to_numpy(dtype=float) * 100.0
            ax.bar(positions, values, bottom=bottoms, width=0.96, color=colors[index % len(colors)], label=label, linewidth=0)
            bottoms += values

        counts = data.groupby("group", observed=False).size().reindex(group_levels, fill_value=0)
        cursor = 0
        group_colors = [PALETTE["blue"], PALETTE["red"], PALETTE["green"], PALETTE["violet"], PALETTE["gold"], PALETTE["teal"]]
        for index, group in enumerate(group_levels):
            count = int(counts[group])
            if not count:
                continue
            start = cursor + 1
            end = cursor + count
            center = (start + end) / 2
            ax.axvline(end + 0.5, color="#333333", linewidth=0.45) if end < len(data) else None
            ax.add_patch(plt.Rectangle((start - 0.5, -8), count, 6.5, color=group_colors[index % len(group_colors)], clip_on=False, linewidth=0))
            ax.text(center, -4.75, f"{group}（n={count}）", ha="center", va="center", color="white", fontsize=7, weight="bold", clip_on=False)
            cursor += count

        ax.set_xlim(0.5, len(data) + 0.5)
        ax.set_ylim(-9, 102)
        ax.set_xticks([])
        ax.set_yticks([0, 20, 40, 60, 80, 100], ["0%", "20%", "40%", "60%", "80%", "100%"])
        ax.set_ylabel(y_label)
        ax.set_xlabel("")
        ax.grid(False)
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["bottom"].set_visible(False)
        ax.legend(loc="upper left", bbox_to_anchor=(1.01, 1.0), frameon=False, fontsize=7.5)
        fig.subplots_adjust(left=0.09, right=0.82, top=0.98, bottom=0.12)
        save_publication_png(fig, output_path, dpi=600, bbox_inches="tight")
        plt.close(fig)
