"""
UMAP analysis service — significance-driven UMAP projections.
"""

from __future__ import annotations

import json
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
from scipy.stats import mannwhitneyu
from sklearn.preprocessing import StandardScaler
import umap

from flask_app.services.figure_style import category_palette, apply_publication_style, soften_axes

_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

apply_publication_style(font_size=10, axes_linewidth=0.9)


def _try_read_csv(filepath, **kwargs):
    suffix = str(filepath).lower()
    sep = kwargs.pop("sep", ",")
    if suffix.endswith((".tsv", ".tsv.gz")):
        sep = "\t"
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(filepath, sep=sep, **kwargs)


@dataclass
class UmapReport:
    job_id: str
    output_base: Path
    png_paths: List[str]
    pdf_paths: List[str]
    csv_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


class UmapService:
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
        n_neighbors: int = 6,
        min_dist: float = 0.01,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> UmapReport:
        datapoint = Path(datapoint_path)
        if not datapoint.exists():
            raise FileNotFoundError(f"Datapoint file not found: {datapoint_path}")

        df = _try_read_csv(datapoint, low_memory=False)
        df.fillna(0, inplace=True)

        columns = df.columns.tolist()
        begin_idx = columns.index(classification_begin)
        over_idx = columns.index(classification_over) + 1
        class_columns = columns[begin_idx:over_idx]

        param_begin_idx = columns.index(param_begin)
        param_over_idx = columns.index(param_over) + 1
        param_columns = columns[param_begin_idx:param_over_idx]

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "umap")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        png_paths, pdf_paths, csv_paths = self._generate(
            df, class_columns, param_columns,
            pvalue_threshold, n_neighbors, min_dist,
            output_base, progress_callback,
        )

        # ZIP bundle
        zip_path = output_base / "umap_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for p in png_paths:
                pp = Path(p)
                if pp.exists():
                    parts = pp.relative_to(output_base).parts
                    zf.write(pp, "umaps/" + "/".join(parts))
            for p in pdf_paths:
                pp = Path(p)
                if pp.exists():
                    parts = pp.relative_to(output_base).parts
                    zf.write(pp, "umaps/" + "/".join(parts))
            for c in csv_paths:
                cp = Path(c)
                if cp.exists():
                    parts = cp.relative_to(output_base).parts
                    zf.write(cp, "data/" + "/".join(parts))

        if progress_callback:
            progress_callback(100, "UMAP completed", f"{len(png_paths)} UMAP plot(s)")

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "datapoint_path": str(datapoint),
            "classification_begin": classification_begin,
            "classification_over": classification_over,
            "param_begin": param_begin,
            "param_over": param_over,
            "pvalue_threshold": pvalue_threshold,
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
            "png_paths": png_paths,
            "pdf_paths": pdf_paths,
            "csv_paths": csv_paths,
        }
        (output_base / "umap_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

        return UmapReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            pdf_paths=pdf_paths,
            csv_paths=csv_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    def _generate(
        self,
        df: pd.DataFrame,
        class_columns: List[str],
        param_columns: List[str],
        pvalue_threshold: float,
        n_neighbors: int,
        min_dist: float,
        output_base: Path,
        progress_callback,
    ):
        png_paths: List[str] = []
        pdf_paths: List[str] = []
        csv_paths: List[str] = []

        total = len(class_columns)
        for ci, class_col in enumerate(class_columns):
            class_types = sorted(df[class_col].dropna().unique().tolist())
            if len(class_types) < 2:
                continue

            if progress_callback:
                progress_callback(
                    5 + int(ci / max(total, 1) * 80),
                    "UMAP analysis",
                    f"Processing {class_col}",
                    {"class_col": class_col},
                )

            # Compute significant params for this class
            category_dir = output_base / class_col
            category_dir.mkdir(parents=True, exist_ok=True)
            csv_dir = output_base / "csv_file" / class_col
            csv_dir.mkdir(parents=True, exist_ok=True)

            # Build param significance map
            all_dict = self._find_significant_params(
                df, class_col, class_types, param_columns, pvalue_threshold
            )

            # Determine min category size for n_neighbors
            min_cat = min(
                df[df[class_col] == t].shape[0] for t in class_types
            )
            local_nn = min(n_neighbors, max(2, min_cat))

            for type_tuple, params in all_dict.items():
                type_list = list(type_tuple)
                if not params:
                    continue

                # Subset dataframe
                use_df = pd.concat([
                    df[df[class_col] == t] for t in type_list
                ])
                if use_df.shape[0] < 3:
                    continue

                bio_data = use_df[params].values
                scaled = StandardScaler().fit_transform(bio_data)
                local_subset_nn = min(local_nn, max(2, use_df.shape[0] - 1))
                reducer = umap.UMAP(
                    n_neighbors=local_subset_nn,
                    min_dist=min_dist,
                    n_epochs=50,
                    random_state=42,
                )
                embedding = reducer.fit_transform(scaled)

                # Plot with restrained categorical colors.
                map_dic = {t: i for i, t in enumerate(type_list)}
                palette = category_palette(type_list)
                labels_for_rows = [str(row[class_col]) for _, row in use_df.iterrows()]

                fig, ax = plt.subplots(figsize=(5.4, 4.8))
                for type_name in type_list:
                    mask = [label == str(type_name) for label in labels_for_rows]
                    ax.scatter(
                        embedding[mask, 0],
                        embedding[mask, 1],
                        c=palette[str(type_name)],
                        label=str(type_name),
                        s=36,
                        alpha=0.88,
                        edgecolors="white",
                        linewidths=0.55,
                    )
                ax.legend(title=class_col, loc="best", markerscale=1.1)
                ax.set_aspect("equal", "datalim")
                name = str(type_tuple).replace("(", "").replace(")", "").replace(", ", "_").replace("'", "")
                ax.set_xlabel("UMAP1")
                ax.set_ylabel("UMAP2")
                ax.set_title("UMAP of " + name + " in " + class_col, fontsize=11, fontweight="bold")
                soften_axes(ax, grid_axis="both")

                pdf_path = category_dir / f"{name}.pdf"
                fig.savefig(pdf_path, bbox_inches="tight", dpi=300, facecolor="white")
                pdf_paths.append(str(pdf_path))
                fig_path = category_dir / f"{name}.png"
                fig.savefig(fig_path, bbox_inches="tight", dpi=300, facecolor="white")
                plt.close("all")
                png_paths.append(str(fig_path))

                # Save point CSV
                labels_int = [map_dic[row[class_col]] for _, row in use_df.iterrows()]
                int2type = {i: t for i, t in enumerate(type_list)}
                umap_points = use_df[[class_col] + list(params)].copy()
                umap_points["umap_x"] = embedding[:, 0]
                umap_points["umap_y"] = embedding[:, 1]
                umap_points["umap_label"] = labels_int
                umap_points["umap_type"] = [int2type[i] for i in labels_int]
                umap_points["umap_params"] = "|".join(list(params))
                umap_points["umap_category"] = class_col
                umap_points["umap_group"] = name
                csv_path = csv_dir / f"{name}_umap_points.csv"
                umap_points.to_csv(csv_path, index=False)
                csv_paths.append(str(csv_path))

        return png_paths, pdf_paths, csv_paths

    def _find_significant_params(
        self,
        df: pd.DataFrame,
        class_col: str,
        class_types: List[str],
        param_columns: List[str],
        pvalue_threshold: float,
    ) -> Dict[tuple, List[str]]:
        """Find params significant across ALL pairs of a type combination."""
        all_dict: Dict[tuple, List[str]] = {}

        # Multi-type combinations
        if len(class_types) > 3:
            cb_list = []
            for i in range(3, len(class_types) + 1):
                cb_list.extend(list(combinations(class_types, i)))
        else:
            cb_list = list(combinations(class_types, 2))

        for cb in cb_list:
            all_params: Dict[str, list] = {}
            for param in param_columns:
                # Check all pairwise p-values within cb
                pairwise_ok = True
                for (a, b) in combinations(list(cb), 2):
                    try:
                        group_a = df[df[class_col] == a][param].dropna()
                        group_b = df[df[class_col] == b][param].dropna()
                        if len(group_a) < 2 or len(group_b) < 2:
                            pairwise_ok = False
                            break
                        pv = mannwhitneyu(group_a, group_b, alternative="two-sided").pvalue
                        if pv > pvalue_threshold:
                            pairwise_ok = False
                            break
                    except Exception:
                        pairwise_ok = False
                        break
                if pairwise_ok:
                    all_params.setdefault(param, [])
                    for t in cb:
                        if t not in all_params[param]:
                            all_params[param].append(t)

            # Keep only params where ALL types in cb contributed
            params_ok = [p for p, types in all_params.items() if set(types) == set(cb)]
            if params_ok:
                all_dict[cb] = params_ok

        return all_dict

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
