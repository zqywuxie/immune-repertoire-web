"""Unified VJ/Profile UMAP analysis aligned with pipeline/10.Umap."""

from __future__ import annotations

import json
import hashlib
import re
import zipfile
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from scipy.spatial.distance import pdist, squareform
from scipy.stats import chi2, mannwhitneyu
from sklearn.preprocessing import StandardScaler

from matplotlib.patches import Ellipse


@dataclass
class UnifiedUmapReport:
    job_id: str
    output_base: Path
    png_paths: list[Path]
    csv_paths: list[Path]
    zip_path: Path
    metadata: dict[str, object]


def canonical_ids(values: pd.Series) -> pd.Series:
    return values.astype("string").str.strip()


def _safe_name(value: str) -> str:
    return "".join(char if char.isalnum() or char in "-_+" else "_" for char in str(value)).strip("_") or "value"


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    last_error = None
    for encoding in ("utf-8-sig", "utf-8", "gb18030", "latin-1"):
        try:
            return pd.read_csv(path, encoding=encoding, compression="infer", low_memory=False, **kwargs)
        except (UnicodeDecodeError, pd.errors.ParserError) as exc:
            last_error = exc
    raise ValueError(f"无法读取文件 {path}: {last_error}")


def select_features_by_raw_p(
    frame: pd.DataFrame, features: list[str], left: str, right: str, threshold: float
) -> tuple[list[str], pd.DataFrame]:
    rows = []
    for feature in features:
        left_values = pd.to_numeric(frame.loc[frame["label"].astype(str).eq(left), feature], errors="coerce")
        right_values = pd.to_numeric(frame.loc[frame["label"].astype(str).eq(right), feature], errors="coerce")
        if str(feature).startswith(("VJ__", "PROFILE__")):
            left_values, right_values = left_values.fillna(0), right_values.fillna(0)
            missing_rule = "zero_before_raw_p"
        else:
            left_values, right_values = left_values.dropna(), right_values.dropna()
            missing_rule = "exclude_missing_before_raw_p"
        if not len(left_values) or not len(right_values):
            p_value, status = np.nan, "insufficient_nonmissing_values"
        else:
            p_value = float(mannwhitneyu(left_values, right_values, alternative="two-sided").pvalue)
            status = "selected" if p_value <= threshold else "not_selected"
        rows.append({
            "feature": feature,
            "modality": str(feature).split("__", 1)[0].lower(),
            "group1": left,
            "group2": right,
            "raw_p_value": p_value,
            "raw_p_threshold": threshold,
            "selection_missing_rule": missing_rule,
            "selection_status": status,
        })
    table = pd.DataFrame(rows)
    return table.loc[table["selection_status"].eq("selected"), "feature"].tolist(), table


def preprocess_features(frame: pd.DataFrame, features: list[str]) -> tuple[np.ndarray, list[str], pd.DataFrame]:
    processed, retained, rows = {}, [], []
    for feature in features:
        values = pd.to_numeric(frame[feature], errors="coerce")
        zero_fill = str(feature).startswith(("VJ__", "PROFILE__"))
        missing_count = int(values.isna().sum())
        if not zero_fill and not values.notna().any():
            rows.append({"feature": feature, "modality": feature.split("__", 1)[0].lower(), "missing_rule": "mean", "imputation_value": np.nan, "missing_count": missing_count, "status": "removed_all_missing", "reason": "non-VJ feature has no defined mean"})
            continue
        fill_value = 0.0 if zero_fill else float(values.mean())
        rule = "zero" if zero_fill else "mean"
        filled = values.fillna(fill_value)
        if np.nanstd(filled.to_numpy(dtype=float)) <= np.finfo(float).eps:
            rows.append({"feature": feature, "modality": feature.split("__", 1)[0].lower(), "missing_rule": rule, "imputation_value": fill_value, "missing_count": missing_count, "status": "removed_constant", "reason": "constant after imputation"})
            continue
        processed[feature] = filled.to_numpy(dtype=float)
        retained.append(feature)
        rows.append({"feature": feature, "modality": feature.split("__", 1)[0].lower(), "missing_rule": rule, "imputation_value": fill_value, "missing_count": missing_count, "status": "retained", "reason": ""})
    if not retained:
        raise ValueError("显著性筛选后没有可用于 UMAP 的非恒定特征。")
    values = StandardScaler().fit_transform(pd.DataFrame(processed, columns=retained))
    return values, retained, pd.DataFrame(rows)


def calculate_permanova(values: np.ndarray, labels: pd.Series | np.ndarray, permutations: int = 999, random_state: int = 42) -> dict[str, object]:
    labels = np.asarray(pd.Series(labels).astype(str))
    unique_labels = np.unique(labels)
    n_samples, n_groups = len(labels), len(unique_labels)
    counts = pd.Series(labels).value_counts().sort_index()
    result = {"n_samples": n_samples, "n_groups": n_groups, "group_counts": json.dumps(counts.to_dict(), ensure_ascii=False), "pseudo_F": np.nan, "R2": np.nan, "raw_p_value": np.nan, "permutations": permutations, "random_state": random_state, "status": "unavailable", "reason": ""}
    if n_groups < 2:
        result["reason"] = "少于两个分组"
        return result
    if n_samples <= n_groups:
        result["reason"] = "样本数不足以估计组内离散度"
        return result
    if values.ndim != 2 or len(values) != n_samples:
        result["reason"] = "特征矩阵与分组长度不一致"
        return result
    distance_sq = squareform(pdist(values, metric="euclidean")) ** 2
    total_ss = distance_sq.sum() / (2 * n_samples)
    if not np.isfinite(total_ss) or total_ss <= np.finfo(float).eps:
        result["reason"] = "特征空间没有可用变异"
        return result

    def pseudo_f(current_labels: np.ndarray) -> float:
        within_ss = 0.0
        for group in np.unique(current_labels):
            indices = np.flatnonzero(current_labels == group)
            if len(indices) > 1:
                within_ss += distance_sq[np.ix_(indices, indices)].sum() / (2 * len(indices))
        between_ss = total_ss - within_ss
        if within_ss <= np.finfo(float).eps:
            return np.nan
        return (between_ss / (n_groups - 1)) / (within_ss / (n_samples - n_groups))

    observed_f = pseudo_f(labels)
    if not np.isfinite(observed_f):
        result["reason"] = "组内离散度为零，无法计算 pseudo-F"
        return result
    within_ss = sum(
        distance_sq[np.ix_(indices, indices)].sum() / (2 * len(indices))
        for group in unique_labels
        if len(indices := np.flatnonzero(labels == group)) > 1
    )
    r_squared = (total_ss - within_ss) / total_ss
    rng = np.random.default_rng(random_state)
    permuted_f = np.array([pseudo_f(rng.permutation(labels)) for _ in range(permutations)])
    valid = permuted_f[np.isfinite(permuted_f)]
    if not len(valid):
        result["reason"] = "没有有效的置换统计量"
        return result
    result.update({"pseudo_F": float(observed_f), "R2": float(r_squared), "raw_p_value": float((1 + np.count_nonzero(valid >= observed_f)) / (1 + len(valid))), "status": "ok"})
    return result


def sample_id_hash(values: Iterable[str]) -> str:
    return hashlib.sha256("\n".join(sorted(str(value) for value in values)).encode("utf-8")).hexdigest()


def add_confidence_ellipse(ax, coordinates: np.ndarray, color, confidence: float = 0.95):
    if len(coordinates) < 3:
        return False, "n<3", None
    covariance = np.cov(coordinates, rowvar=False)
    if covariance.shape != (2, 2) or not np.isfinite(covariance).all():
        return False, "协方差不可用", None
    eigenvalues, eigenvectors = np.linalg.eigh(covariance)
    order = np.argsort(eigenvalues)[::-1]
    eigenvalues, eigenvectors = eigenvalues[order], eigenvectors[:, order]
    if eigenvalues[-1] <= np.finfo(float).eps or np.linalg.matrix_rank(covariance) < 2:
        return False, "坐标协方差退化", None
    scale = np.sqrt(chi2.ppf(confidence, df=2))
    angle = np.degrees(np.arctan2(eigenvectors[1, 0], eigenvectors[0, 0]))
    center = np.mean(coordinates, axis=0)
    semi_major, semi_minor = scale * np.sqrt(eigenvalues)
    radians = np.deg2rad(angle)
    x_radius = np.hypot(semi_major * np.cos(radians), semi_minor * np.sin(radians))
    y_radius = np.hypot(semi_major * np.sin(radians), semi_minor * np.cos(radians))
    bounds = (float(center[0] - x_radius), float(center[0] + x_radius), float(center[1] - y_radius), float(center[1] + y_radius))
    ax.add_patch(Ellipse(xy=center, width=2 * scale * np.sqrt(eigenvalues[0]), height=2 * scale * np.sqrt(eigenvalues[1]), angle=angle, facecolor="white", edgecolor=color, linestyle="--", linewidth=1.8, alpha=0.9, zorder=3))
    return True, "", bounds


def square_axis_limits(x_values, y_values, padding_fraction: float = 0.03, min_span: float = 1.0):
    x = np.asarray(x_values, dtype=float)
    y = np.asarray(y_values, dtype=float)
    if not x.size or not y.size or not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("UMAP 坐标为空或包含非有限值，无法设定坐标范围。")
    x_lower, x_upper = float(x.min()), float(x.max())
    y_lower, y_upper = float(y.min()), float(y.max())
    span = max(x_upper - x_lower, y_upper - y_lower, min_span) * (1 + 2 * padding_fraction)
    x_center, y_center = (x_lower + x_upper) / 2, (y_lower + y_upper) / 2
    half = span / 2
    return (x_center - half, x_center + half), (y_center - half, y_center + half)


def draw_feature_barplot(frame: pd.DataFrame, features: list[str], left: str, right: str, output_path: Path) -> None:
    rows = []
    for feature in features:
        a = pd.to_numeric(frame.loc[frame["label"].astype(str).eq(left), feature], errors="coerce").dropna()
        b = pd.to_numeric(frame.loc[frame["label"].astype(str).eq(right), feature], errors="coerce").dropna()
        if len(a) and len(b):
            p = float(mannwhitneyu(a, b, alternative="two-sided").pvalue)
            score = -np.log10(max(p, 1e-300)) * np.sign(float(a.mean() - b.mean()))
            rows.append((feature, score))
    if not rows:
        return
    import matplotlib.pyplot as plt
    from flask_app.services.figure_style import apply_publication_style, save_publication_png
    plot = pd.DataFrame(rows, columns=["feature", "signed_log10_raw_p"]).sort_values("signed_log10_raw_p", ascending=False)
    apply_publication_style(font_size=8)
    fig, ax = plt.subplots(figsize=(max(7, 0.3 * len(plot) + 2), 5))
    colors = np.where(plot["signed_log10_raw_p"] >= 0, "#C44E52", "#4C72B0")
    ax.bar(plot["feature"], plot["signed_log10_raw_p"], color=colors)
    ax.axhline(0, color="black", linewidth=0.8)
    ax.set_ylabel("有方向的 -log10(p 值)")
    ax.set_xticks(range(len(plot)), plot["feature"], rotation=90, fontsize=8)
    ax.set_title(f"特征差异：{left} vs {right}")
    fig.tight_layout()
    save_publication_png(fig, output_path)
    plt.close(fig)


class UnifiedUmapService:
    """VJ/Profile multimodal projection and pairwise PERMANOVA."""

    def __init__(self, *, output_parent: Path):
        self.output_parent = Path(output_parent)

    @staticmethod
    def prepare_profile(*, profile_path, sample_column, label_column, batch_field="",
                        include_labels=(), exclude_groups=(), selected_samples=(),
                        selected_samples_by_group=None, group_sample_identity="sample"):
        from flask_app.services.pep_analysis_service import _batch_sample_identity
        profile = _read_csv(Path(profile_path), dtype=str, keep_default_na=False)
        if sample_column not in profile or label_column not in profile:
            raise ValueError("样本指标表缺少样本编号列或分组列。")
        if batch_field and (batch_field not in profile or batch_field in {sample_column, label_column}):
            raise ValueError("批次字段必须是独立于样本编号和分组的有效列。")
        if group_sample_identity not in {"sample", "batch_sample"} or (group_sample_identity == "batch_sample" and not batch_field):
            raise ValueError("组内样本编号方式无效，请重新选择批次与样本。")
        profile["source_sample"] = canonical_ids(profile[sample_column])
        profile["label"] = canonical_ids(profile[label_column])
        if profile["source_sample"].eq("").any():
            raise ValueError("样本指标表存在空样本编号。")
        if batch_field:
            profile["source_batch"] = canonical_ids(profile[batch_field])
            if profile["source_batch"].eq("").any():
                raise ValueError("样本指标表存在空批次值。")
            profile["sample"] = [_batch_sample_identity(batch, sample) for batch, sample in zip(profile["source_batch"], profile["source_sample"])]
        else:
            profile["sample"] = profile["source_sample"]
        if profile["sample"].duplicated().any():
            raise ValueError("样本指标表存在重复的批次与样本编号组合。" if batch_field else "样本指标表存在重复样本编号，需先明确跨批次样本对应关系。")
        original = profile.copy()
        profile = profile[profile["label"].ne("")].copy()
        if include_labels:
            profile = profile[profile["label"].isin([str(item).strip() for item in include_labels])].copy()
        if exclude_groups:
            profile = profile[~profile["label"].isin([str(item).strip() for item in exclude_groups])].copy()
        if selected_samples_by_group:
            if any(field != label_column for field in selected_samples_by_group):
                raise ValueError("组内样本选择必须对应本次 UMAP 分组列。")
            identities = original["sample"] if group_sample_identity == "batch_sample" else original["source_sample"]
            keep = pd.Series(False, index=profile.index)
            for group, samples in selected_samples_by_group.get(label_column, {}).items():
                chosen = {str(sample).strip() for sample in samples}
                available = set(identities.loc[original["label"].eq(str(group).strip())])
                if chosen - available:
                    raise ValueError(f"所选组内样本不存在：{group}")
                keep |= profile["label"].eq(str(group).strip()) & identities.loc[profile.index].isin(chosen)
            profile = profile[keep].copy()
        if selected_samples:
            chosen = {str(sample).strip() for sample in selected_samples}
            if chosen - set(original["source_sample"]):
                raise ValueError("所选样本编号不存在于样本指标表。")
            profile = profile[profile["source_sample"].isin(chosen)].copy()
        if profile["label"].nunique() < 2:
            raise ValueError("筛选后少于两个类别，无法进行分组 UMAP。")
        columns = ["sample", "label"] + (["source_sample", "source_batch"] if batch_field else [])
        return profile, profile[columns].copy()

    def generate_report(
        self, *, profile_path: str, sample_column: str, label_column: str,
        configurations: Iterable[str], vj_usage_path: str = "", batch_field: str = "",
        profile_start: str = "", profile_end: str = "",
        include_labels: Iterable[str] = (), exclude_groups: Iterable[str] = (),
        selected_samples_by_group: dict[str, dict[str, list[str]]] | None = None,
        selected_samples: Iterable[str] = (), group_sample_identity: str = "sample",
        group_order: Iterable[str] = (), raw_p_threshold: float = 0.05,
        comparison_cohort: str = "auto", n_neighbors: int = 6,
        min_dist: float = 0.01, n_epochs: int = 50, permutations: int = 999,
        random_state: int = 42, permanova_random_state: int = 42,
        progress_callback=None, output_name: str = "unified_umap",
    ) -> UnifiedUmapReport:
        profile_file = Path(profile_path)
        if not profile_file.is_file():
            raise FileNotFoundError(f"未找到样本指标表：{profile_file}")
        if not 0 < raw_p_threshold <= 1 or n_neighbors < 2 or n_epochs < 1 or not 0 <= min_dist <= 1 or permutations < 1:
            raise ValueError("UMAP 参数超出有效范围。")
        configs = list(dict.fromkeys(str(config).strip().lower() for config in configurations))
        if not configs or any(config not in {"profile", "vj", "vj+profile"} for config in configs):
            raise ValueError("仅支持样本指标、V/J 特征或两者联合投影。")
        if comparison_cohort not in {"auto", "per_config", "shared"}:
            raise ValueError("无效的样本队列策略。")

        batch_field = str(batch_field or "").strip()
        profile, metadata = self.prepare_profile(
            profile_path=profile_path, sample_column=sample_column, label_column=label_column,
            batch_field=batch_field, include_labels=include_labels, exclude_groups=exclude_groups,
            selected_samples=selected_samples, selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
        )

        modalities: dict[str, pd.DataFrame] = {}
        if any("profile" in config for config in configs):
            columns = profile.columns.tolist()
            feature_columns = columns
            if bool(profile_start) != bool(profile_end):
                raise ValueError("样本指标特征起始列和结束列必须同时设置。")
            if profile_start:
                if profile_start not in columns or profile_end not in columns:
                    raise ValueError("样本指标特征范围列不存在。")
                start, end = columns.index(profile_start), columns.index(profile_end)
                if start > end:
                    raise ValueError("样本指标起始列不能位于结束列之后。")
                feature_columns = columns[start:end + 1]
            excluded = {sample_column, label_column, "sample", "label", "source_sample", "source_batch"}
            if batch_field:
                excluded.add(batch_field)
            feature_columns = [column for column in feature_columns if column not in excluded]
            numeric = profile[feature_columns].apply(pd.to_numeric, errors="coerce")
            numeric = numeric.loc[:, numeric.notna().any(axis=0)]
            numeric.columns = [f"PROFILE__{column}" for column in numeric.columns]
            modalities["profile"] = pd.concat([profile[["sample"]].reset_index(drop=True), numeric.reset_index(drop=True)], axis=1)
            if numeric.empty:
                raise ValueError("样本指标特征范围内没有可用数值特征。")

        if any("vj" in config.split("+") for config in configs):
            path = Path(vj_usage_path)
            if not path.exists():
                raise FileNotFoundError("V/J 投影需要已生成的 V/J 使用特征结果。")
            paths = [path] if path.is_file() else sorted([*path.rglob("*.csv"), *path.rglob("*.csv.gz")])
            merged = None
            profile_samples = set(metadata["sample"])
            for source in paths:
                header = _read_csv(source, nrows=0)
                id_col = "sample" if "sample" in header else header.columns[0]
                read_types = {id_col: "string"}
                if batch_field and batch_field in header.columns:
                    read_types[batch_field] = "string"
                data = _read_csv(source, dtype=read_types, keep_default_na=False)
                ids = canonical_ids(data[id_col])
                ids = ids.where(ids.isin(profile_samples), ids.str.replace(r"\.csv(?:\.gz)?$", "", regex=True))
                if batch_field and batch_field in data.columns:
                    batch_values = canonical_ids(data[batch_field])
                    from flask_app.services.pep_analysis_service import _batch_sample_identity
                    joined = pd.Series([_batch_sample_identity(str(batch), str(sample)) for batch, sample in zip(batch_values, ids)], index=ids.index)
                    ids = ids.where(ids.isin(profile_samples), joined)
                split = ids.str.rsplit("__", n=1)
                base = split.str[0]
                suffix = split.str[1].fillna("").str.upper()
                ids = ids.where(~((~ids.isin(profile_samples)) & base.isin(profile_samples) & suffix.isin({"IGH", "IGK", "IGL", "TRA", "TRB", "TRD", "TRG"})), base)
                excluded = {id_col, "Category", "category", label_column, batch_field}
                numeric = data.drop(columns=list(excluded), errors="ignore").apply(pd.to_numeric, errors="coerce")
                numeric = numeric.loc[:, numeric.notna().any(axis=0)]
                prefix = _safe_name(source.name.removesuffix(".csv.gz").removesuffix(".csv"))
                numeric.columns = [f"VJ__{prefix}__{column}" for column in numeric.columns]
                current = pd.concat([ids.rename("sample").reset_index(drop=True), numeric.reset_index(drop=True)], axis=1)
                if current["sample"].duplicated().any():
                    conflicts = current.drop(columns="sample").notna().groupby(current["sample"], sort=False).sum()
                    if (conflicts > 1).any().any():
                        raise ValueError(f"VJ 结果同一样本存在冲突特征：{source.name}")
                    current = current.groupby("sample", as_index=False, sort=False).first()
                merged = current if merged is None else merged.merge(current, on="sample", how="outer", validate="one_to_one")
            if merged is None or len(merged.columns) <= 1:
                raise ValueError("VJ usage 输入中没有可用数值特征。")
            modalities["vj"] = merged

        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "umap")
        png_paths: list[Path] = []
        csv_paths: list[Path] = []
        qc_rows, permanova_rows = [], []
        from flask_app.services.figure_style import apply_publication_style, save_publication_png, soften_axes
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        apply_publication_style(font_size=10)

        for config_index, config in enumerate(configs):
            parts = config.split("+")
            effective_cohort = "per_config" if len(parts) == 1 else ("shared" if comparison_cohort == "auto" else comparison_cohort)
            cohort_override_reason = (
                ("auto_single_modality_per_config" if comparison_cohort == "auto" else "single_modality_forced_per_config" if comparison_cohort == "shared" else "")
                if len(parts) == 1 else ("auto_multi_modality_shared" if comparison_cohort == "auto" else "")
            )
            frame = metadata.copy()
            for modality in parts:
                frame = frame.merge(modalities[modality], on="sample", how="inner", validate="one_to_one")
            if effective_cohort == "shared":
                shared = set(metadata["sample"])
                for modality in parts:
                    shared &= set(modalities[modality]["sample"])
                frame = frame[frame["sample"].isin(shared)]
            features = [column for column in frame if "__" in column]
            if frame.empty or not features:
                raise ValueError(f"{config} 没有匹配样本或可用特征。")
            groups = [group for group in group_order if group in set(frame["label"].astype(str))]
            groups += [group for group in dict.fromkeys(frame["label"].astype(str)) if group not in groups]
            if len(groups) < 2:
                raise ValueError(f"{config} 可用于两两比较的分组少于两个。")
            config_dir = output_base / _safe_name(config)
            config_dir.mkdir(parents=True, exist_ok=True)
            selection_frames, coordinate_frames, pair_rows = [], [], []
            comparisons_in_config = max(len(list(combinations(groups, 2))), 1)
            for left, right in combinations(groups, 2):
                if progress_callback:
                    done = config_index + len(pair_rows) / comparisons_in_config
                    progress_callback(10 + int(70 * done / len(configs)), "统一 UMAP", f"正在处理 {config}：{left} vs {right}")
                pair = frame[frame["label"].astype(str).isin([left, right])].copy()
                selected, selection = select_features_by_raw_p(pair, features, left, right, raw_p_threshold)
                selection = selection.assign(configuration=config, comparison=f"{left} vs {right}")
                selection_frames.append(selection)
                row = {"configuration": config, "comparison_scope": "pairwise", "groups": f"{left};{right}", "group1": left, "group2": right, "n_features_raw": len(features), "n_features_selected": len(selected), "n_features_retained": 0, "raw_p_threshold": raw_p_threshold, "umap_refit": True, "umap_n_neighbors": np.nan, "umap_n_epochs": n_epochs, "distance_metric": "euclidean", "feature_space": "StandardScaler-transformed selected multi-modal UMAP input", "requested_cohort": comparison_cohort, "effective_cohort": effective_cohort, "cohort_override_reason": cohort_override_reason, "cohort_modalities": ";".join(parts), "config_sample_id_hash": sample_id_hash(frame["sample"]), "comparison_sample_id_hash": sample_id_hash(pair["sample"])}
                if not selected:
                    group_counts = pair["label"].astype(str).value_counts().sort_index()
                    row.update({"n_samples": len(pair), "n_groups": len(group_counts), "group_counts": json.dumps(group_counts.to_dict(), ensure_ascii=False), "pseudo_F": np.nan, "R2": np.nan, "raw_p_value": np.nan, "permutations": permutations, "random_state": permanova_random_state, "status": "skipped", "reason": "raw-P 筛选后没有显著特征"})
                    pair_rows.append(row)
                    if progress_callback:
                        done = config_index + len(pair_rows) / comparisons_in_config
                        progress_callback(10 + int(70 * done / len(configs)), "统一 UMAP", f"已完成 {config}：{left} vs {right}")
                    continue
                try:
                    values, retained, manifest = preprocess_features(pair, selected)
                except ValueError as exc:
                    row.update({"status": "skipped", "reason": str(exc), "n_features_retained": 0})
                    pair_rows.append(row)
                    if progress_callback:
                        done = config_index + len(pair_rows) / comparisons_in_config
                        progress_callback(10 + int(70 * done / len(configs)), "统一 UMAP", f"已跳过 {config}：{left} vs {right}（{exc}）")
                    continue
                labels = pair["label"].astype(str)
                stats = calculate_permanova(values, labels, permutations, permanova_random_state)
                row.update({**stats, "n_features_retained": len(retained), "feature_space": "StandardScaler-transformed selected multi-modal UMAP input"})
                if len(pair) >= 3:
                    if progress_callback:
                        done = config_index + len(pair_rows) / comparisons_in_config
                        progress_callback(10 + int(70 * done / len(configs)), "UMAP 降维", "正在加载运行环境并拟合投影；首次启动可能稍慢。")
                    from umap.umap_ import UMAP
                    local_neighbors = min(n_neighbors, int(labels.value_counts().min()), len(pair) - 1)
                    if local_neighbors >= 2:
                        try:
                            embedding = UMAP(n_neighbors=local_neighbors, min_dist=min_dist, metric="euclidean", n_epochs=n_epochs, random_state=random_state).fit_transform(values)
                        except ValueError as exc:
                            row.update({"status": "skipped", "reason": str(exc)})
                            pair_rows.append(row)
                            if progress_callback:
                                done = config_index + len(pair_rows) / comparisons_in_config
                                progress_callback(10 + int(70 * done / len(configs)), "统一 UMAP", f"已跳过 {config}：{left} vs {right}（{exc}）")
                            continue
                        coordinate_fields = ["sample", "label"] + [column for column in ("source_batch", "source_sample") if column in pair]
                        coords = pair[coordinate_fields].copy()
                        coords["UMAP1"], coords["UMAP2"] = embedding[:, 0], embedding[:, 1]
                        coords["configuration"], coords["comparison"] = config, f"{left} vs {right}"
                        coords["umap_params"] = "|".join(retained)
                        coords["umap_n_neighbors"] = local_neighbors
                        coords["umap_min_dist"] = min_dist
                        coords["umap_n_epochs"] = n_epochs
                        coords["umap_random_state"] = random_state
                        coordinate_frames.append(coords)
                        fig, ax = plt.subplots(figsize=(6, 6))
                        palette = plt.get_cmap("tab10")
                        ellipse_bounds = [coords["UMAP1"].min(), coords["UMAP1"].max(), coords["UMAP2"].min(), coords["UMAP2"].max()]
                        for group in (left, right):
                            subset = coords[coords["label"].astype(str).eq(group)]
                            color = palette((groups.index(group)) % 10)
                            ax.scatter(subset["UMAP1"], subset["UMAP2"], label=group, color=color, s=45, alpha=0.9)
                            drawn, _reason, bounds = add_confidence_ellipse(ax, subset[["UMAP1", "UMAP2"]].to_numpy(), color, 0.95)
                            if drawn and bounds is not None:
                                ellipse_bounds[0] = min(ellipse_bounds[0], bounds[0])
                                ellipse_bounds[1] = max(ellipse_bounds[1], bounds[1])
                                ellipse_bounds[2] = min(ellipse_bounds[2], bounds[2])
                                ellipse_bounds[3] = max(ellipse_bounds[3], bounds[3])
                        ax.set(title=f"UMAP 投影：{left} vs {right}", xlabel="UMAP1", ylabel="UMAP2")
                        ax.legend(title="分组", frameon=False)
                        xlim, ylim = square_axis_limits(ellipse_bounds[:2], ellipse_bounds[2:])
                        ax.set_xlim(xlim)
                        ax.set_ylim(ylim)
                        ax.set_aspect("equal", adjustable="box")
                        soften_axes(ax, grid_axis="both")
                        if stats["status"] == "ok":
                            raw_p = float(stats["raw_p_value"])
                            annotation = "PERMANOVA：原始 p 值 " + ("***" if raw_p <= 0.001 else "**" if raw_p <= 0.01 else "*" if raw_p <= 0.05 else "")
                        else:
                            annotation = f"PERMANOVA unavailable: {stats['reason']}"
                        ax.text(0.02, 0.98, annotation, transform=ax.transAxes, va="top", ha="left", fontsize=10, fontweight="bold", bbox={"boxstyle": "round,pad=0.25", "facecolor": "white", "alpha": 0.82, "edgecolor": "0.75"})
                        fig.tight_layout()
                        image_path = config_dir / f"{_safe_name(left)}_vs_{_safe_name(right)}.png"
                        save_publication_png(fig, image_path)
                        plt.close(fig)
                        png_paths.append(image_path)
                        feature_path = config_dir / f"{_safe_name(left)}_vs_{_safe_name(right)}_features.png"
                        draw_feature_barplot(pair, selected, left, right, feature_path)
                        if feature_path.exists():
                            png_paths.append(feature_path)
                        row["umap_n_neighbors"] = local_neighbors
                        if progress_callback:
                            done = config_index + (len(pair_rows) + 0.5) / comparisons_in_config
                            progress_callback(10 + int(70 * done / len(configs)), "UMAP 降维", f"已完成 {config}：{left} vs {right}")
                pair_rows.append(row)
                if progress_callback:
                    done = config_index + len(pair_rows) / comparisons_in_config
                    progress_callback(10 + int(70 * done / len(configs)), "统一 UMAP", f"已完成 {config}：{left} vs {right}")
            coordinate_columns = ["sample", "label"] + (["source_batch", "source_sample"] if batch_field else []) + ["UMAP1", "UMAP2", "configuration", "comparison", "umap_params", "umap_n_neighbors", "umap_min_dist", "umap_n_epochs", "umap_random_state"]
            coordinate_table = pd.concat(coordinate_frames, ignore_index=True) if coordinate_frames else pd.DataFrame(columns=coordinate_columns)
            for name, table in (("pairwise_permanova.csv", pd.DataFrame(pair_rows)), ("selected_features.csv", pd.concat(selection_frames, ignore_index=True)), ("umap_coordinates.csv", coordinate_table)):
                path = config_dir / name
                table.to_csv(path, index=False, encoding="utf-8-sig")
                csv_paths.append(path)
            qc_rows.append({"configuration": config, "n_samples": len(frame), "n_features": len(features), "classes": ";".join(groups), "class_counts": json.dumps(frame["label"].value_counts().to_dict(), ensure_ascii=False), "effective_cohort": effective_cohort})
            permanova_rows.extend(pair_rows)
        qc_path = output_base / "sample_qc.csv"
        pd.DataFrame(qc_rows).to_csv(qc_path, index=False, encoding="utf-8-sig")
        csv_paths.append(qc_path)
        permanova_path = output_base / "permanova_summary.csv"
        pd.DataFrame(permanova_rows).to_csv(permanova_path, index=False, encoding="utf-8-sig")
        csv_paths.append(permanova_path)
        if progress_callback:
            progress_callback(96, "整理 UMAP 结果", "正在生成结果压缩包与统计摘要。")
        identity_path = output_base / "sample_identity.csv"
        metadata.to_csv(identity_path, index=False, encoding="utf-8-sig")
        csv_paths.append(identity_path)
        metadata_result = {"output_name": output_name, "analysis": "统一 V/J 与样本指标 UMAP", "profile_path": str(profile_file.resolve()), "vj_usage_path": str(Path(vj_usage_path).resolve()) if vj_usage_path else "", "configurations": configs, "group_column": label_column, "sample_column": sample_column, "batch_field": batch_field, "sample_identity_rule": "batch::sample" if batch_field else "sample", "group_sample_identity": group_sample_identity, "selected_samples": list(selected_samples), "selected_samples_by_group": selected_samples_by_group or {}, "selected_sample_count": len(metadata), "raw_p_threshold": raw_p_threshold, "n_neighbors": n_neighbors, "min_dist": min_dist, "n_epochs": n_epochs, "permanova_permutations": permutations, "random_state": random_state, "permanova_random_state": permanova_random_state, "png_count": len(png_paths), "warnings": []}
        metadata_path = output_base / "umap_metadata.json"
        metadata_path.write_text(json.dumps(metadata_result, ensure_ascii=False, indent=2), encoding="utf-8")
        zip_path = output_base / "unified_umap_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in [*png_paths, *csv_paths, metadata_path]:
                archive.write(path, path.relative_to(output_base).as_posix())
        return UnifiedUmapReport(job_id, output_base, png_paths, csv_paths, zip_path, metadata_result)
