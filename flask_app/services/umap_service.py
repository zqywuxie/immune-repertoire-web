"""
UMAP analysis service — significance-driven UMAP projections.
"""

from __future__ import annotations

import json
import os
import zipfile
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime
from itertools import combinations
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]
_REMOVE_CLASS_VALUES = {0, "0"}

_STYLE_APPLIED = False


def _load_umap_dependencies():
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("NUMBA_NUM_THREADS", "1")
    try:
        from sklearn.preprocessing import StandardScaler
        import umap
    except ImportError as exc:  # pragma: no cover - depends on deployment environment
        raise RuntimeError(
            "UMAP dependencies are missing. Please install scikit-learn and umap-learn from flask_app/requirements.txt."
        ) from exc
    return StandardScaler, umap


def _load_plot_dependencies():
    global _STYLE_APPLIED
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from flask_app.services.figure_style import (
        apply_publication_style,
        category_palette,
        save_publication_png,
        soften_axes,
    )
    if not _STYLE_APPLIED:
        apply_publication_style(font_size=10, axes_linewidth=0.9)
        _STYLE_APPLIED = True
    return plt, category_palette, save_publication_png, soften_axes


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
        valid_param_columns = []
        for column in param_columns:
            numeric = pd.to_numeric(df[column], errors="coerce")
            if numeric.notna().any():
                df[column] = numeric.fillna(0)
                valid_param_columns.append(column)
        if not valid_param_columns:
            raise ValueError("No numeric parameter columns were found in the selected UMAP parameter range.")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "umap")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        viable_class_columns, warnings = self._preflight_class_columns(df, class_columns)
        if viable_class_columns:
            png_paths, pdf_paths, csv_paths, generate_warnings = self._generate(
                df, viable_class_columns, valid_param_columns,
                pvalue_threshold, n_neighbors, min_dist,
                output_base, progress_callback,
            )
            warnings.extend(generate_warnings)
        else:
            png_paths, pdf_paths, csv_paths = [], [], []

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

        no_result_message = ""
        if not png_paths:
            details = "; ".join(warnings[:3])
            no_result_message = details or (
                "No UMAP plots were generated. Check that the selected classification field has at least two groups "
                "and at least one parameter passes the Mann-Whitney U p-value threshold."
            )

        if progress_callback:
            progress_callback(100, "UMAP completed", no_result_message or f"{len(png_paths)} UMAP plot(s)")

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "datapoint_path": str(datapoint),
            "classification_begin": classification_begin,
            "classification_over": classification_over,
            "param_begin": param_begin,
            "param_over": param_over,
            "numeric_param_count": len(valid_param_columns),
            "pvalue_threshold": pvalue_threshold,
            "n_neighbors": n_neighbors,
            "min_dist": min_dist,
            "projection_backend": "umap-learn",
            "png_paths": png_paths,
            "pdf_paths": pdf_paths,
            "csv_paths": csv_paths,
            "message": no_result_message,
            "warnings": warnings,
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
        warnings: List[str] = []
        plot_deps = None
        reducer_deps = None

        total = len(class_columns)
        for ci, class_col in enumerate(class_columns):
            class_types = self._class_types_for_column(df, class_col)
            if len(class_types) < 2:
                warnings.append(f"Skipped {class_col}: fewer than two groups.")
                continue
            if progress_callback:
                progress_callback(
                    5 + int(ci / max(total, 1) * 80),
                    "UMAP analysis",
                    f"Processing {class_col}",
                    {"class_col": class_col},
                )

            category_dir = output_base / class_col
            category_dir.mkdir(parents=True, exist_ok=True)
            csv_dir = output_base / "csv_file" / class_col
            csv_dir.mkdir(parents=True, exist_ok=True)

            p_value_all = self._pvalue_list_for_category(
                df, class_col, class_types, param_columns, pvalue_threshold
            )
            _, all_dict, all_dict_pvalue = self._find_cate_to_param_reference(
                class_col, class_types, p_value_all, pvalue_threshold
            )
            if not all_dict:
                warnings.append(f"Skipped {class_col}: no parameter combinations matched the reference p-value rule.")
                continue

            min_cat = min(
                df[df[class_col] == t].shape[0] for t in class_types
            )
            local_nn = min(n_neighbors, min_cat) if min_cat < n_neighbors else n_neighbors
            local_nn = max(2, local_nn)

            for type_tuple, params in all_dict.items():
                type_list = list(type_tuple)
                if not params:
                    continue

                # Subset dataframe
                use_df = pd.concat([
                    df[df[class_col] == t] for t in type_list
                ])
                if use_df.shape[0] < 3:
                    warnings.append(f"Skipped {class_col} / {', '.join(map(str, type_list))}: fewer than three samples.")
                    continue

                bio_data = use_df[params].values
                if reducer_deps is None:
                    if progress_callback:
                        progress_callback(30, "UMAP projection", "Loading UMAP runtime", {"phase": "load_umap"})
                    reducer_deps = _load_umap_dependencies()
                StandardScaler, umap_module = reducer_deps
                scaled = StandardScaler().fit_transform(bio_data)
                local_subset_nn = min(local_nn, max(2, use_df.shape[0] - 1))
                reducer = umap_module.UMAP(
                    n_neighbors=local_subset_nn,
                    min_dist=min_dist,
                    n_epochs=50,
                    random_state=42,
                )
                embedding = reducer.fit_transform(scaled)
                if plot_deps is None:
                    plot_deps = _load_plot_dependencies()
                plt, category_palette, save_publication_png, soften_axes = plot_deps

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
                name = self._safe_plot_name(type_tuple)
                ax.set_xlabel("UMAP1")
                ax.set_ylabel("UMAP2")
                ax.set_title("UMAP of " + name + " in " + class_col, fontsize=11, fontweight="bold")
                soften_axes(ax, grid_axis="both")

                pdf_path = category_dir / f"{name}.pdf"
                fig.savefig(pdf_path, bbox_inches="tight", dpi=300)
                pdf_paths.append(str(pdf_path))
                fig_path = category_dir / f"{name}.png"
                save_publication_png(fig, fig_path)
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
                umap_points["umap_n_neighbors"] = local_subset_nn
                umap_points["umap_min_dist"] = min_dist
                umap_points["umap_random_state"] = 42
                umap_points["umap_n_epochs"] = 50
                csv_path = csv_dir / f"{name}_umap_points.csv"
                umap_points.to_csv(csv_path, index=False)
                csv_paths.append(str(csv_path))
                meta_path = csv_dir / f"{name}_umap_meta.txt"
                with meta_path.open("w", encoding="utf-8") as handle:
                    handle.write(f"category={class_col}\n")
                    handle.write(f"group={name}\n")
                    handle.write(f"types={type_list}\n")
                    handle.write(f"params={list(params)}\n")
                    handle.write(f"pvalue_records={all_dict_pvalue.get(type_tuple, [])}\n")
                    handle.write(f"n_neighbors={local_subset_nn}\n")
                    handle.write(f"min_dist={min_dist}\n")
                    handle.write("random_state=42\n")
                    handle.write("n_epochs=50\n")

        return png_paths, pdf_paths, csv_paths, warnings

    @staticmethod
    def _safe_plot_name(type_tuple: tuple) -> str:
        raw = "_".join(str(item) for item in type_tuple)
        safe = "".join(ch if ch.isalnum() or ch in {"_", "-", "."} else "_" for ch in raw).strip("_")
        if len(safe) > 120:
            safe = safe[:100].rstrip("_") + f"_and_{len(type_tuple)}groups"
        return safe or "groups"

    @staticmethod
    def _preflight_class_columns(df: pd.DataFrame, class_columns: List[str]) -> Tuple[List[str], List[str]]:
        viable: List[str] = []
        warnings: List[str] = []
        for class_col in class_columns:
            if class_col not in df.columns:
                warnings.append(f"Skipped {class_col}: column not found.")
                continue
            values = UmapService._class_types_for_column(df, class_col)
            if len(values) < 2:
                warnings.append(f"Skipped {class_col}: fewer than two groups.")
                continue
            viable.append(class_col)
        return viable, warnings

    @staticmethod
    def _class_types_for_column(df: pd.DataFrame, class_col: str) -> List[Any]:
        values: List[Any] = []
        for value in df[class_col].tolist():
            if pd.isna(value):
                continue
            if value in _REMOVE_CLASS_VALUES or str(value) in _REMOVE_CLASS_VALUES:
                continue
            if value not in values:
                values.append(value)
        return values

    @staticmethod
    def _pvalue_list_for_category(
        df: pd.DataFrame,
        class_col: str,
        class_types: List[str],
        param_columns: List[str],
        pvalue_threshold: float,
    ) -> List[Tuple[Any, Any, str, float]]:
        from scipy.stats import mannwhitneyu
        pvalue_tuples: List[Tuple[Any, Any, str, float]] = []
        for cb in combinations(class_types, 2):
            for param in param_columns:
                try:
                    pvalue = mannwhitneyu(
                        df[df[class_col] == cb[0]][param],
                        df[df[class_col] == cb[1]][param],
                        alternative="two-sided",
                    ).pvalue
                    pvalue_tuples.append((cb[0], cb[1], param, float(pvalue)))
                except Exception:
                    continue
        return pvalue_tuples

    @staticmethod
    def _find_cate_to_param_reference(
        category: str,
        class_types: List[Any],
        pvalue_tuples_list: List[Tuple[Any, Any, str, float]],
        pvalue_threshold: float,
    ) -> Tuple[Dict[tuple, Dict[str, float]], Dict[tuple, List[str]], Dict[tuple, List[Tuple[Any, Any, str, float]]]]:
        pair_dict: Dict[tuple, Dict[str, float]] = {}
        all_dict: Dict[tuple, List[str]] = {}
        all_dict_pvalue: Dict[tuple, List[Tuple[Any, Any, str, float]]] = {}

        cb_list: List[tuple] = []
        if len(class_types) > 3:
            for i in range(3, len(class_types) + 1):
                cb_list.extend(list(combinations(class_types, i)))
        else:
            cb_list = list(combinations(class_types, 2))

        for pvalue_tuple in pvalue_tuples_list:
            pair_tuple = (pvalue_tuple[0], pvalue_tuple[1])
            if pvalue_tuple[3] <= pvalue_threshold:
                if pair_tuple not in pair_dict:
                    pair_dict[pair_tuple] = {pvalue_tuple[2]: pvalue_tuple[3]}
                else:
                    pair_dict[pair_tuple][pvalue_tuple[2]] = pvalue_tuple[3]

                for cb in cb_list:
                    if pvalue_tuple[0] in cb and pvalue_tuple[1] in cb:
                        if cb not in all_dict:
                            all_dict[cb] = [pvalue_tuple[2]]
                            all_dict_pvalue[cb] = [pvalue_tuple]
                            continue
                        if pvalue_tuple[2] not in all_dict[cb]:
                            all_dict[cb].append(pvalue_tuple[2])
                        all_dict_pvalue[cb].append(pvalue_tuple)

        temporary_dict = deepcopy(all_dict_pvalue)
        for cb, tuple_params_list in temporary_dict.items():
            params = []
            for pvalue_tuple in tuple_params_list:
                if pvalue_tuple[0] not in params:
                    params.append(pvalue_tuple[0])
                if pvalue_tuple[1] not in params:
                    params.append(pvalue_tuple[1])
            if len(params) != len(cb):
                del all_dict_pvalue[cb]
                del all_dict[cb]
        return pair_dict, all_dict, all_dict_pvalue

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{name}_{ts}"
