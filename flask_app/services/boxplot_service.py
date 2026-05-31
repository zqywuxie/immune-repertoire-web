"""
BoxPlot analysis service for DB alignment results.
"""

from __future__ import annotations

import json
import os
import zipfile
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
    csv_paths: List[str]
    significant_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


class BoxPlotService:
    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        datapoint_path: str,
        classification_begin: Optional[str] = None,
        classification_over: Optional[str] = None,
        grouptype_fields: Optional[List[str]] = None,
        param_begin: str,
        param_over: str,
        group_order: Optional[str] = None,
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

        param_begin_idx = columns.index(param_begin)
        param_over_idx = columns.index(param_over) + 1
        param_columns = columns[param_begin_idx:param_over_idx]

        if grouptype_fields:
            class_columns = [c for c in grouptype_fields if c in columns]
        elif classification_begin and classification_begin.strip():
            begin_idx = columns.index(classification_begin)
            over_idx = columns.index(classification_over) + 1
            class_columns = columns[begin_idx:over_idx]
        else:
            class_columns = []

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "boxplot")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        # Parse group_order: supports JSON dict per-field or simple comma-separated
        parsed_order = None
        if group_order and group_order.strip():
            s = group_order.strip()
            if s.startswith("{"):
                try:
                    parsed_order = json.loads(s)
                except json.JSONDecodeError:
                    parsed_order = [x.strip() for x in s.split(",") if x.strip()]
            else:
                parsed_order = [x.strip() for x in s.split(",") if x.strip()]

        png_paths: List[str] = []
        pvalue_paths: List[str] = []
        csv_paths: List[str] = []
        significant_paths: List[str] = []
        skipped_insufficient = 0

        if class_columns:
            png_paths, pvalue_paths, csv_paths, significant_paths, skipped_insufficient = self._generate_grouped(
                df, class_columns, param_columns,
                pvalue_threshold, output_base, progress_callback,
                parsed_order,
            )
        else:
            png_paths, csv_paths = self._generate_ungrouped(
                df, param_columns, output_base, progress_callback,
            )

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "datapoint_path": str(datapoint),
            "classification_begin": classification_begin,
            "classification_over": classification_over,
            "grouptype_fields": grouptype_fields,
            "param_begin": param_begin,
            "param_over": param_over,
            "group_order": group_order,
            "pvalue_threshold": pvalue_threshold,
            "class_columns": class_columns,
            "param_columns": param_columns,
            "png_paths": png_paths,
            "pvalue_paths": pvalue_paths,
            "csv_paths": csv_paths,
            "significant_paths": significant_paths,
            "class_type_counts": {class_col: len(df[class_col].dropna().unique()) for class_col in class_columns} if class_columns else {},
            "skipped_insufficient_data": skipped_insufficient,
        }
        (output_base / "boxplot_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        # Generate ZIP bundle
        zip_path = output_base / "boxplot_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for png_path in png_paths:
                p = Path(png_path)
                if p.exists():
                    # Store as boxplots/{class_col}/{param}.png
                    parts = p.relative_to(output_base).parts
                    arcname = "boxplots/" + "/".join(parts)
                    zf.write(p, arcname)
            for pv_path in pvalue_paths:
                p = Path(pv_path)
                if p.exists():
                    arcname = "pvalues/" + p.relative_to(output_base).name
                    zf.write(p, arcname)
            for csv_path in csv_paths:
                p = Path(csv_path)
                if p.exists():
                    # Store as data/{class_col}/csvfiles/{param}.csv
                    parts = p.relative_to(output_base).parts
                    arcname = "data/" + "/".join(parts)
                    zf.write(p, arcname)
            for sig_path in significant_paths:
                p = Path(sig_path)
                if p.exists():
                    arcname = "significance/" + p.relative_to(output_base).name
                    zf.write(p, arcname)

        if progress_callback:
            msg = f"Generated {len(png_paths)} plot(s)"
            if skipped_insufficient > 0:
                msg += f" — {skipped_insufficient} comparison(s) skipped (groups need ≥2 data points)"
            progress_callback(100, "BoxPlot completed", msg)

        return BoxPlotReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            pvalue_paths=pvalue_paths,
            csv_paths=csv_paths,
            significant_paths=significant_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    def _generate_grouped(
        self,
        df: pd.DataFrame,
        class_columns: List[str],
        param_columns: List[str],
        pvalue_threshold: float,
        output_base: Path,
        progress_callback,
        group_order: Optional[List[str]] = None,
    ):
        png_paths: List[str] = []
        pvalue_paths: List[str] = []
        csv_paths: List[str] = []
        significant_paths: List[str] = []
        total_steps = len(class_columns) * len(param_columns)
        step = 0
        skipped_insufficient = 0

        for class_col in class_columns:
            class_dir = output_base / class_col
            class_dir.mkdir(parents=True, exist_ok=True)
            csv_dir = class_dir / "csvfiles"
            csv_dir.mkdir(parents=True, exist_ok=True)

            raw_types = sorted(df[class_col].dropna().unique().tolist())
            if group_order:
                if isinstance(group_order, dict):
                    field_order = group_order.get(class_col, "")
                    if field_order:
                        ordered = [x.strip() for x in field_order.split(",") if x.strip()]
                        class_types = [t for t in ordered if t in raw_types] + [t for t in raw_types if t not in ordered]
                    else:
                        class_types = raw_types
                else:
                    class_types = [t for t in group_order if t in raw_types] + [t for t in raw_types if t not in group_order]
            else:
                class_types = raw_types
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
                            skipped_insufficient += 1
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

                self._plot_boxplot(df, class_col, param, class_types,
                                   significant_pairs, class_dir)
                png_paths.append(str(class_dir / f"{param}.png"))

                plot_df = df[(["sample"] if "sample" in df.columns else []) + [class_col, param]]
                concat_df = pd.concat([
                    plot_df[plot_df[class_col] == t] for t in class_types
                ])
                csv_path = csv_dir / f"{param}.csv"
                concat_df.to_csv(csv_path, index=False)
                csv_paths.append(str(csv_path))

            df_pvalues = pd.DataFrame(pvalue_records)
            if not df_pvalues.empty:
                pvalue_csv = class_dir / f"{class_col}_pvalues.csv"
                df_pvalues.to_csv(pvalue_csv, index=False)
                pvalue_paths.append(str(pvalue_csv))

                sig_df = df_pvalues[df_pvalues["pvalue"] <= pvalue_threshold]
                if not sig_df.empty:
                    sig_csv = class_dir / f"{class_col}_significant.csv"
                    sig_df.to_csv(sig_csv, index=False)
                    significant_paths.append(str(sig_csv))

        if significant_paths:
            all_significant_parts: List[pd.DataFrame] = []
            for sig_path in significant_paths:
                try:
                    all_significant_parts.append(pd.read_csv(sig_path))
                except Exception:
                    pass
            if all_significant_parts:
                all_sig_csv = output_base / "_all_significant.csv"
                pd.concat(all_significant_parts, ignore_index=True).to_csv(all_sig_csv, index=False)
                significant_paths.append(str(all_sig_csv))

        return png_paths, pvalue_paths, csv_paths, significant_paths, skipped_insufficient

    def _generate_ungrouped(
        self,
        df: pd.DataFrame,
        param_columns: List[str],
        output_base: Path,
        progress_callback,
    ):
        ungrouped_dir = output_base / "ungrouped"
        ungrouped_dir.mkdir(parents=True, exist_ok=True)
        csv_dir = ungrouped_dir / "csvfiles"
        csv_dir.mkdir(parents=True, exist_ok=True)

        png_paths: List[str] = []
        csv_paths: List[str] = []
        total_steps = len(param_columns)
        for i, param in enumerate(param_columns):
            if progress_callback:
                progress_callback(
                    5 + int((i + 1) / max(total_steps, 1) * 90),
                    "BoxPlot analysis (ungrouped)",
                    f"Processing {param}",
                    {"param": param},
                )

            self._plot_ungrouped_boxplot(df, param, ungrouped_dir)
            png_paths.append(str(ungrouped_dir / f"{param}.png"))

            param_data = df[[param]].dropna()
            csv_path = csv_dir / f"{param}.csv"
            param_data.to_csv(csv_path, index=False)
            csv_paths.append(str(csv_path))

        return png_paths, csv_paths

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

        fig_width = 1.0 * len(class_types)
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
    def _plot_ungrouped_boxplot(
        df: pd.DataFrame,
        param: str,
        output_dir: Path,
    ) -> None:
        plot_data = df[[param]].dropna()
        if plot_data.empty:
            return

        sns.set(rc={"figure.figsize": (4, 5)})
        sns.set_style("white")
        sns.set_palette("pastel")

        fig, ax = plt.subplots()
        sns.boxplot(y=param, data=plot_data, linewidth=2, width=0.4, ax=ax)
        sns.stripplot(y=param, data=plot_data, color="purple",
                       jitter=True, size=4, alpha=0.5, ax=ax)

        ax.set_ylabel(param, fontsize=14)
        ax.tick_params(labelsize=12, length=0)
        plt.yticks(fontweight="semibold", size=12)
        ax.set_xticklabels(["All Samples"], fontweight="semibold", size=12)

        fig_path = output_dir / f"{param}.png"
        fig.savefig(fig_path, bbox_inches="tight", dpi=300)
        plt.close("all")

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
