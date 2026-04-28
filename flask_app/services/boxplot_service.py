"""
BoxPlot analysis service for DB alignment results.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns
from scipy.stats import mannwhitneyu


@dataclass
class BoxPlotReport:
    job_id: str
    output_base: Path
    png_paths: List[str]
    pvalue_paths: List[str]
    metadata: Dict[str, Any]


class BoxPlotService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        datapoint_path: str,
        classification_begin: str,
        classification_over: str,
        param_begin: str,
        param_over: str,
        pvalue_threshold: float = 0.05,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> BoxPlotReport:
        datapoint = Path(datapoint_path)
        if not datapoint.exists():
            raise FileNotFoundError(f"Datapoint file not found: {datapoint_path}")

        df = pd.read_csv(datapoint, low_memory=False)
        df.fillna(0, inplace=True)

        columns = df.columns.tolist()
        begin_idx = columns.index(classification_begin)
        over_idx = columns.index(classification_over) + 1
        class_columns = columns[begin_idx:over_idx]

        param_begin_idx = columns.index(param_begin)
        param_over_idx = columns.index(param_over) + 1
        param_columns = columns[param_begin_idx:param_over_idx]

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "boxplot")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        png_paths: List[str] = []
        pvalue_paths: List[str] = []

        total_steps = len(class_columns) * len(param_columns)
        step = 0

        for class_col in class_columns:
            class_dir = output_base / class_col
            class_dir.mkdir(parents=True, exist_ok=True)
            csv_dir = class_dir / "csvfiles"
            csv_dir.mkdir(parents=True, exist_ok=True)

            class_types = sorted(df[class_col].dropna().unique().tolist())
            pvalue_records: List[Dict[str, Any]] = []

            for param in param_columns:
                step += 1
                if progress_callback:
                    progress_callback(
                        5 + int(step / max(total_steps, 1) * 90),
                        "BoxPlot analysis",
                        f"Processing {class_col} / {param}",
                        {"class_col": class_col, "param": param},
                    )

                combo_list = list(combinations(class_types, 2))
                significant_pairs: List[tuple] = []
                for combo in combo_list:
                    try:
                        group_a = df[df[class_col] == combo[0]][param].dropna()
                        group_b = df[df[class_col] == combo[1]][param].dropna()
                        if len(group_a) < 2 or len(group_b) < 2:
                            continue
                        pvalue = mannwhitneyu(group_a, group_b, alternative="two-sided").pvalue
                        pvalue_records.append({
                            "class": class_col,
                            "group_a": combo[0],
                            "group_b": combo[1],
                            "param": param,
                            "pvalue": pvalue,
                        })
                        if pvalue <= pvalue_threshold:
                            significant_pairs.append((combo[0], combo[1], pvalue))
                    except Exception:
                        continue

                if significant_pairs:
                    self._plot_boxplot(df, class_col, param, class_types,
                                       significant_pairs, class_dir)
                    png_paths.append(str(class_dir / f"{param}.png"))

                plot_df = df[["sample"] if "sample" in df.columns else [] + [class_col, param]]
                concat_df = pd.concat([
                    plot_df[plot_df[class_col] == t] for t in class_types
                ])
                concat_df.to_csv(csv_dir / f"{param}.csv", index=False)

            df_pvalues = pd.DataFrame(pvalue_records)
            if not df_pvalues.empty:
                pvalue_csv = class_dir / f"{class_col}_pvalues.csv"
                df_pvalues.to_csv(pvalue_csv, index=False)
                pvalue_paths.append(str(pvalue_csv))

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "datapoint_path": str(datapoint),
            "classification_begin": classification_begin,
            "classification_over": classification_over,
            "param_begin": param_begin,
            "param_over": param_over,
            "pvalue_threshold": pvalue_threshold,
            "class_columns": class_columns,
            "param_columns": param_columns,
            "png_paths": png_paths,
            "pvalue_paths": pvalue_paths,
        }
        (output_base / "boxplot_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        if progress_callback:
            progress_callback(100, "BoxPlot completed", f"Generated {len(png_paths)} plots")

        return BoxPlotReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            pvalue_paths=pvalue_paths,
            metadata=metadata,
        )

    @staticmethod
    def _plot_boxplot(
        df: pd.DataFrame,
        class_col: str,
        param: str,
        class_types: List[str],
        significant_pairs: List[tuple],
        output_dir: Path,
    ) -> None:
        plot_df = df[[class_col, param]].dropna()
        plot_df = pd.concat([
            plot_df[plot_df[class_col] == t] for t in class_types
        ])

        fig_width = max(1.0 * len(class_types), 6)
        sns.set(rc={"figure.figsize": (fig_width, 4)})
        sns.set_style("white")
        sns.set_palette("pastel")

        ax = sns.boxplot(x=class_col, y=param, data=plot_df, linewidth=2, width=0.6)
        sns.stripplot(x=class_col, y=param, data=plot_df, color="purple",
                       jitter=True, size=4, alpha=0.5, ax=ax)

        legend_text = ""
        for pair in significant_pairs:
            legend_text += f"{pair[0]} VS {pair[1]} p={float(f'{pair[2]:.4g}')}\n"

        if legend_text:
            bbox = dict(boxstyle="round", fc="w", ec="0.5", alpha=0.8)
            ax.text(0, 1, legend_text.strip(), backgroundcolor="white",
                    bbox=bbox, transform=ax.transAxes, fontsize=10,
                    verticalalignment="top")

        ax.set_ylabel(param, fontsize=14)
        ax.set_xlabel(class_col, fontsize=16)
        ax.tick_params(labelsize=12, length=0)
        plt.xticks(fontweight="semibold", size=12)
        plt.yticks(fontweight="semibold", size=12)
        ax.set_xticklabels(ax.get_xticklabels(), rotation=45, ha="right")

        fig_path = output_dir / f"{param}.png"
        ax.figure.savefig(fig_path, bbox_inches="tight", dpi=300)
        ax.figure.clf()
        plt.close("all")

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
