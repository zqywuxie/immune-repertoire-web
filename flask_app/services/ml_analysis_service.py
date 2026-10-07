"""
Machine-learning analysis service based on _reference/anal_pipeline/ML_260526.
"""

from __future__ import annotations

import json
import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.ensemble import ExtraTreesClassifier, GradientBoostingClassifier, RandomForestClassifier
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    average_precision_score,
    auc,
    balanced_accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedGroupKFold, StratifiedKFold
from sklearn.naive_bayes import GaussianNB
from sklearn.neighbors import KNeighborsClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import LabelEncoder, StandardScaler, label_binarize
from sklearn.svm import SVC

from flask_app.services.figure_style import (
    MUTED_BLUE_RED_CMAP,
    MUTED_CATEGORY_COLORS,
    PALETTE,
    apply_publication_style,
    save_publication_png,
    soften_axes,
)

_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

RANDOM_STATE = 42
DEFAULT_THRESHOLD = 0.003
SUPPORTED_ML_MODELS = {
    "logistic_l1": "逻辑回归（L1）",
    "random_forest": "随机森林",
    "extra_trees": "极端随机树",
    "logistic_l2": "逻辑回归（L2）",
    "gaussian_nb": "高斯朴素贝叶斯",
    "knn": "K 近邻",
    "rbf_svm": "径向基 SVM",
    "linear_svm": "线性 SVM",
    "gradient_boosting": "梯度提升树",
    "xgboost": "XGBoost",
}

apply_publication_style(font_size=10, axes_linewidth=0.9)


def _try_read_csv(filepath, **kwargs):
    suffix = str(filepath).lower()
    sep = kwargs.pop("sep", ",")
    if suffix.endswith((".tsv", ".tsv.gz")):
        sep = "\t"
    if suffix.endswith((".xlsx", ".xls", ".xlsm")):
        kwargs.pop("low_memory", None)
        return pd.read_excel(filepath, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, compression="infer", **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(filepath, sep=sep, compression="infer", **kwargs)


def _safe_name(value: str) -> str:
    safe = re.sub(
        r"[^A-Za-z0-9_.=-]+", "_", str(value if value is not None else "ml")
    ).strip("_")
    return safe or "ml"


@dataclass
class MLAnalysisReport:
    job_id: str
    output_base: Path
    png_paths: List[str]
    pdf_paths: List[str]
    csv_paths: List[str]
    text_paths: List[str]
    zip_path: str
    metadata: Dict[str, Any]


class _FoldLocalTopKSelector(BaseEstimator, TransformerMixin):
    """Rank features inside a training fold using script 09 modality Top-K."""

    def __init__(self, feature_names: Tuple[str, ...], mode: str):
        self.feature_names = feature_names
        self.mode = mode

    def _modality(self, feature: str) -> str:
        if self.mode == "vj":
            return "vj"
        if self.mode == "profile":
            return "profile"
        return "profile" if str(feature).lower().startswith("profile__") else "vj"

    def fit(self, X, y):
        values = np.asarray(X, dtype=float)
        if values.shape[1] != len(self.feature_names):
            raise ValueError("Top-K 特征名称数量与输入矩阵列数不一致")
        self.model_ = RandomForestClassifier(
            n_estimators=100,
            class_weight="balanced",
            random_state=RANDOM_STATE,
            n_jobs=1,
        ).fit(values, y)
        importances = self.model_.feature_importances_
        top_k = {"vj": 20, "profile": 10}
        modality_indices: Dict[str, List[int]] = {}
        for index, feature in enumerate(self.feature_names):
            modality = self._modality(feature)
            modality_indices.setdefault(modality, []).append(index)
        self.support_ = np.zeros(values.shape[1], dtype=bool)
        for modality, indices in modality_indices.items():
            ranked = sorted(indices, key=lambda index: (-importances[index], self.feature_names[index]))
            self.support_[ranked[: min(top_k[modality], len(ranked))]] = True
        self.importances_ = importances
        return self

    def transform(self, X):
        return np.asarray(X)[:, self.support_]

    def get_support(self):
        return self.support_


class MLAnalysisService:
    """Cross-validated classifier workflows for Profile features and cached VJ usage."""

    SUPPORTED_ML_MODELS = SUPPORTED_ML_MODELS

    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        profile_path: str,
        mode: str = "profile",
        label_col: str,
        sample_col: str = "Sample",
        group_col: str = "",
        batch_field: Optional[str] = None,
        selected_group_values: Optional[Dict[str, List[str]]] = None,
        selected_samples: Optional[List[str]] = None,
        selected_samples_by_group: Optional[Dict[str, Dict[str, List[str]]]] = None,
        group_sample_identity: str = "sample",
        param_begin: str = "",
        param_over: str = "",
        usage_path: str = "",
        filter_col: str = "",
        filter_value: str = "",
        feature_cols: Optional[List[str]] = None,
        usage_feature_cols: Optional[List[str]] = None,
        model_keys: Optional[List[str]] = None,
        custom_threshold: float = DEFAULT_THRESHOLD,
        cv_splits: int = 3,
        use_stability_selection: bool = True,
        stability_threshold: float = 0.60,
        stability_splits: int = 5,
        stability_min_features: int = 5,
        # Kept for queued-job/API compatibility; ROC now reuses nested-CV predictions.
        roc_cv_splits: int = 7,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> MLAnalysisReport:
        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise FileNotFoundError(f"Profile file not found: {profile_path}")
        mode = self._normalize_mode(mode)
        if mode not in {"profile", "vj", "profile_vj"}:
            raise ValueError("mode must be profile, vj, or profile_vj")
        model_keys = list(dict.fromkeys(str(key).strip().lower() for key in (model_keys or ["random_forest"]) if str(key).strip()))
        unsupported_models = [key for key in model_keys if key not in SUPPORTED_ML_MODELS]
        if not model_keys or unsupported_models:
            raise ValueError(
                "请选择至少一个支持的模型；不支持的模型："
                + (", ".join(unsupported_models) if unsupported_models else "无")
            )

        work_df, sample_col, sample_identity = self.prepare_profile(
            profile_path=profile_path, sample_col=sample_col, label_col=label_col,
            group_col=group_col, batch_field=batch_field, filter_col=filter_col,
            filter_value=filter_value, selected_group_values=selected_group_values,
            selected_samples=selected_samples, selected_samples_by_group=selected_samples_by_group,
            group_sample_identity=group_sample_identity,
        )
        group_col = str(group_col or "").strip()

        self.output_parent.mkdir(parents=True, exist_ok=True)
        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "ml-analysis")

        if progress_callback:
            progress_callback(10, "\u673a\u5668\u5b66\u4e60\u5206\u6790", "\u6b63\u5728\u51c6\u5907\u7279\u5f81\u77e9\u9635")

        if mode in {"profile", "profile_vj"}:
            profile_X_df, profile_y, profile_le = self._prepare_profile_xy(
                work_df, sample_col, label_col, param_begin, param_over, feature_cols
            )
            profile_X_df = profile_X_df.drop(
                columns=[col for col in (sample_col, label_col, group_col, batch_field) if col],
                errors="ignore",
            )
            profile_matrix = pd.concat(
                [work_df[[sample_col, label_col]].reset_index(drop=True), profile_X_df.reset_index(drop=True)],
                axis=1,
            )
            if group_col:
                profile_matrix[group_col] = work_df[group_col].to_numpy()
        if mode == "profile":
            X_df, y, le = profile_X_df, profile_y, profile_le
            sample_ids = work_df[sample_col].astype(str).to_numpy()
            group_ids = work_df[group_col].to_numpy() if group_col else None
            merged_path = output_base / "profile_feature_matrix.csv"
            profile_matrix.to_csv(merged_path, index=False, encoding="utf-8-sig")
        else:
            usage_root = Path(usage_path)
            if not usage_root.exists():
                raise FileNotFoundError(f"Usage path not found: {usage_path}")
            feature_df = self._build_usage_feature_matrix(
                set(work_df[sample_col]),
                usage_root,
                sample_col,
                usage_feature_cols,
            )
            if feature_df.empty:
                raise ValueError("No matched usage features found")
            base_columns = [sample_col, label_col] + ([group_col] if group_col else [])
            base_df = profile_matrix if mode == "profile_vj" else work_df[base_columns]
            if mode == "profile_vj":
                rename_map = {
                    col: f"profile__{col}"
                    for col in base_df.columns
                    if col not in {sample_col, label_col, group_col}
                }
                base_df = base_df.rename(columns=rename_map)
            merged = base_df.merge(feature_df, on=sample_col, how="inner")
            if merged.empty:
                raise ValueError("No samples matched between Profile and usage data")
            merged_path = output_base / ("profile_vj_feature_matrix.csv" if mode == "profile_vj" else "merged_feature_matrix.csv")
            merged.to_csv(merged_path, index=False, encoding="utf-8-sig")
            sample_ids = merged[sample_col].astype(str).to_numpy()
            X_df, y, le = self._prepare_usage_xy(merged, sample_col, label_col)
            if group_col:
                X_df = X_df.drop(columns=[group_col], errors="ignore")
                group_ids = merged[group_col].to_numpy()
            else:
                group_ids = None

        if X_df.shape[0] < 3 or len(np.unique(y)) < 2:
            raise ValueError("Need at least 3 samples and 2 label classes for ML analysis")
        if X_df.shape[1] == 0:
            raise ValueError("No numeric feature columns available")
        if not 0 < float(stability_threshold) <= 1:
            raise ValueError("稳定特征入选频率阈值必须在 (0, 1] 范围内")
        if int(stability_splits) < 2:
            raise ValueError("稳定性筛选折数至少为 2")
        if int(stability_min_features) < 1:
            raise ValueError("每类数据至少保留 1 个稳定特征")

        stable_features = None
        stability_table = pd.DataFrame()
        stability_folds = 0
        if use_stability_selection:
            stability_table, stability_folds = self._select_stable_features(
                X_df,
                y,
                mode=mode,
                groups=group_ids,
                n_splits=int(stability_splits),
                frequency_threshold=float(stability_threshold),
                min_features_per_modality=int(stability_min_features),
                progress_callback=progress_callback,
            )
            stable_features = stability_table.loc[
                stability_table["selected_for_final_model"], "feature"
            ].astype(str).tolist()
            if not stable_features:
                raise ValueError("稳定性筛选未保留可用于最终模型的特征")

        if progress_callback:
            progress_callback(25, "\u673a\u5668\u5b66\u4e60\u5206\u6790", f"\u6b63\u5728\u51c6\u5907 {X_df.shape[1]} \u4e2a\u539f\u59cb\u7279\u5f81" + (f"\uff0c\u7a33\u5b9a\u7279\u5f81 {len(stable_features)} \u4e2a" if stable_features is not None else ""))

        out_dir = output_base / self._slice_dir_name(mode, label_col, filter_col, filter_value)
        out_dir.mkdir(parents=True, exist_ok=True)
        report_paths = {"csv_paths": [], "text_paths": [], "png_paths": [], "pdf_paths": []}
        if not stability_table.empty:
            stability_path = out_dir / "feature_stability.csv"
            stable_path = out_dir / "stable_features.csv"
            stability_table.to_csv(stability_path, index=False, encoding="utf-8-sig")
            stability_table.loc[stability_table["selected_for_final_model"]].to_csv(
                stable_path, index=False, encoding="utf-8-sig"
            )
            report_paths["csv_paths"].extend([str(stability_path), str(stable_path)])
        model_summaries = []
        for model_index, model_key in enumerate(model_keys):
            model_callback = None
            if progress_callback:
                def model_callback(progress, stage, detail, meta=None, *, _index=model_index, _key=model_key):
                    model_fraction = min(1.0, max(0.0, (float(progress or 0) - 35.0) / 40.0))
                    overall = 20.0 + 70.0 * (_index + model_fraction) / len(model_keys)
                    progress_callback(
                        overall,
                        stage,
                        f"模型 {_index + 1}/{len(model_keys)}（{SUPPORTED_ML_MODELS[_key]}）：{detail}",
                        meta,
                    )
            model_paths = self._run_classifier(
                X_df=X_df,
                y=y,
                le=le,
                sample_ids=sample_ids,
                group_ids=group_ids,
                model_key=model_key,
                out_dir=out_dir / "models" / model_key,
                custom_threshold=custom_threshold,
                cv_splits=cv_splits,
                final_feature_cols=stable_features,
                feature_mode=mode,
                progress_callback=model_callback,
            )
            for path_kind in ("csv_paths", "text_paths", "png_paths", "pdf_paths"):
                report_paths[path_kind].extend(model_paths[path_kind])
            model_summaries.append({
                "model_key": model_key,
                "model_label": SUPPORTED_ML_MODELS[model_key],
                **model_paths["summary"],
            })

        comparison_path = out_dir / "model_comparison.csv"
        pd.DataFrame(model_summaries).to_csv(comparison_path, index=False, encoding="utf-8-sig")
        report_paths["csv_paths"].insert(0, str(comparison_path))
        report_paths["summary"] = {
            **model_summaries[0],
            "model_keys": model_keys,
            "model_results": model_summaries,
        }

        metadata = {
            "job_id": job_id,
            "output_name": output_name,
            "generated_at": datetime.now().isoformat(),
            "mode": mode,
            "data_mode": mode,
            "profile_path": str(profile_file.resolve()),
            "usage_path": str(Path(usage_path).resolve()) if usage_path else "",
            "sample_col": sample_col,
            "label_col": label_col,
            "group_col": group_col,
            "batch_field": batch_field,
            "group_sample_identity": group_sample_identity,
            "selected_group_values": selected_group_values or {},
            "selected_samples": selected_samples or [],
            "selected_samples_by_group": selected_samples_by_group or {},
            "filter_col": filter_col,
            "filter_value": filter_value,
            "param_begin": param_begin,
            "param_over": param_over,
            "feature_cols": feature_cols or [],
            "usage_feature_cols": usage_feature_cols or [],
            "model_keys": model_keys,
            "models": model_summaries,
            "stability_selection": {
                "enabled": bool(use_stability_selection),
                "folds": int(stability_folds),
                "frequency_threshold": float(stability_threshold),
                "min_features_per_modality": int(stability_min_features),
                "selected_features": stable_features or [],
            },
            "result_items": [
                {
                    "path": str(path),
                    "kind": "image" if str(path).lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".svg")) else "file",
                    "data_mode": mode,
                    "title": Path(path).name,
                }
                for path in report_paths["png_paths"] + report_paths["csv_paths"] + report_paths["text_paths"]
            ],
            "samples": int(X_df.shape[0]),
            "raw_feature_number": int(X_df.shape[1]),
            "custom_threshold": custom_threshold,
            "cv_strategy": "stratified_group_k_fold" if group_col else "stratified_k_fold",
            **report_paths["summary"],
        }
        (output_base / "ml_analysis_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        identity_path = output_base / "sample_identity.csv"
        sample_identity = sample_identity[sample_identity["sample"].isin(sample_ids)].copy()
        sample_identity.to_csv(identity_path, index=False, encoding="utf-8-sig")
        csv_paths = [str(merged_path), str(identity_path)] + report_paths["csv_paths"]
        text_paths = report_paths["text_paths"]
        png_paths = report_paths["png_paths"]
        pdf_paths = report_paths["pdf_paths"]

        zip_path = output_base / "ml_analysis_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in [output_base / "ml_analysis_metadata.json"] + [Path(p) for p in csv_paths + text_paths + png_paths]:
                if path.exists():
                    zf.write(path, path.relative_to(output_base).as_posix())

        if progress_callback:
            progress_callback(100, "\u673a\u5668\u5b66\u4e60\u5206\u6790", "\u5206\u6790\u5b8c\u6210")

        return MLAnalysisReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            pdf_paths=pdf_paths,
            csv_paths=csv_paths,
            text_paths=text_paths,
            zip_path=str(zip_path),
            metadata=metadata,
        )

    @classmethod
    def prepare_profile(
        cls, *, profile_path: str, sample_col: str, label_col: str,
        group_col: str = "", batch_field: Optional[str] = None,
        filter_col: str = "", filter_value: str = "",
        selected_group_values=None, selected_samples=None, selected_samples_by_group=None,
        group_sample_identity: str = "sample",
    ):
        """Match UI selections to text identifiers before preparing numeric features."""
        from flask_app.services.pep_analysis_service import _batch_sample_identity
        frame = _try_read_csv(profile_path, dtype=str, keep_default_na=False, low_memory=False)
        sample_col = cls._resolve_column(frame, sample_col, ["Sample", "sample", "SAMPLE"])
        group_col = str(group_col or "").strip()
        batch_field = str(batch_field or "").strip() or None
        if label_col not in frame.columns:
            raise ValueError(f"分类标签列不存在：{label_col}")
        if group_col and (group_col not in frame.columns or group_col in {sample_col, label_col}):
            raise ValueError("受试者分组列必须存在，且与样本编号列和分类标签列不同")
        if batch_field and (batch_field not in frame.columns or batch_field in {sample_col, label_col}):
            raise ValueError("批次字段必须存在，且与样本编号列和分类标签列不同")
        if group_sample_identity not in {"sample", "batch_sample"} or (group_sample_identity == "batch_sample" and not batch_field):
            raise ValueError("组内样本编号方式无效，请重新选择批次与样本")
        frame[sample_col] = frame[sample_col].str.strip()
        frame[label_col] = frame[label_col].str.strip()
        if frame[sample_col].eq("").any():
            raise ValueError("样本编号包含空值，请修正样本指标表")
        if batch_field:
            frame[batch_field] = frame[batch_field].str.strip()
            if frame[batch_field].eq("").any():
                raise ValueError("批次字段包含空值，请修正样本指标表")
        duplicate_columns = [sample_col] + ([batch_field] if batch_field else [])
        duplicate = frame.loc[frame.duplicated(duplicate_columns, keep=False), sample_col]
        if not duplicate.empty:
            examples = ", ".join(duplicate.drop_duplicates().head(5))
            raise ValueError(f"样本编号必须唯一（选择批次时按批次与编号共同识别），发现重复样本：{examples}")
        identities = (frame.apply(lambda row: _batch_sample_identity(row[batch_field], row[sample_col]), axis=1)
                      if batch_field else frame[sample_col].copy())
        selected = frame[frame[label_col].ne("")].copy()
        if filter_col and filter_value:
            if filter_col not in selected.columns:
                raise ValueError(f"筛选列不存在：{filter_col}")
            selected = selected[selected[filter_col].str.strip().eq(str(filter_value).strip())].copy()
        for field, values in (selected_group_values or {}).items():
            if field not in frame.columns:
                raise ValueError(f"所选分组字段不存在：{field}")
            allowed = {str(value).strip() for value in values}
            if allowed:
                missing = allowed - set(frame[field].str.strip())
                if missing:
                    raise ValueError(f"所选分组值不存在：{field} / {', '.join(sorted(missing)[:5])}")
                selected = selected[selected[field].str.strip().isin(allowed)].copy()
        for field, groups in (selected_samples_by_group or {}).items():
            if field not in frame.columns:
                raise ValueError(f"所选样本分组字段不存在：{field}")
            ids = identities if group_sample_identity == "batch_sample" else frame[sample_col]
            keep = pd.Series(False, index=selected.index)
            for group, samples in groups.items():
                chosen = {str(sample).strip() for sample in samples}
                available = set(ids.loc[frame[field].str.strip().eq(str(group).strip())])
                if chosen - available:
                    raise ValueError(f"所选组内样本不存在：{field} / {group}")
                keep |= selected[field].str.strip().eq(str(group).strip()) & ids.loc[selected.index].isin(chosen)
            selected = selected[keep].copy()
        if selected_samples:
            chosen = {str(sample).strip() for sample in selected_samples}
            if chosen - set(frame[sample_col]):
                raise ValueError("所选样本编号不存在于样本指标表")
            selected = selected[selected[sample_col].isin(chosen)].copy()
        if selected.empty:
            raise ValueError("筛选后没有可分析的样本，请检查标签和样本选择")
        identity = pd.DataFrame({"sample": identities.loc[selected.index],
                                 "original_sample_id": selected[sample_col], "label": selected[label_col]})
        if batch_field:
            identity["batch"] = selected[batch_field]
        if group_col:
            identity["subject"] = selected[group_col]
        selected[sample_col] = identities.loc[selected.index]
        return selected.reset_index(drop=True), sample_col, identity.reset_index(drop=True)

    @staticmethod
    def _normalize_mode(mode: str) -> str:
        value = str(mode or "profile").strip().lower().replace("-", "_").replace("+", "_")
        if value in {"vj", "vj_usage", "usage"}:
            return "vj"
        if value in {"profile_vj", "profile_usage", "profile_vj_usage"}:
            return "profile_vj"
        return "profile"

    @staticmethod
    def _resolve_column(df: pd.DataFrame, preferred: str, candidates: List[str]) -> str:
        if preferred in df.columns:
            return preferred
        lower_map = {str(c).lower(): c for c in df.columns}
        for candidate in candidates:
            if candidate.lower() in lower_map:
                return lower_map[candidate.lower()]
        raise ValueError(f"Column not found: {preferred}")

    @staticmethod
    def _prepare_profile_xy(
        df: pd.DataFrame,
        sample_col: str,
        label_col: str,
        param_begin: str,
        param_over: str,
        selected_features: Optional[List[str]] = None,
    ) -> Tuple[pd.DataFrame, np.ndarray, LabelEncoder]:
        le = LabelEncoder()
        y = le.fit_transform(df[label_col].astype(str).values)
        columns = df.columns.tolist()
        requested = [str(col) for col in (selected_features or []) if str(col) in columns]
        missing = [str(col) for col in (selected_features or []) if str(col) not in columns]
        if missing:
            raise ValueError(f"Selected Profile feature columns not found: {', '.join(missing[:10])}")
        if requested:
            feature_cols = requested
        elif param_begin and param_over:
            if param_begin not in columns or param_over not in columns:
                raise ValueError("param_begin or param_over not found in Profile columns")
            start = columns.index(param_begin)
            end = columns.index(param_over)
            if start > end:
                raise ValueError("特征范围起始列必须位于结束列之前，请检查列选择")
            feature_cols = columns[start:end + 1]
        else:
            feature_cols = [c for c in columns if c not in {sample_col, label_col}]
        X_df = df[feature_cols].apply(pd.to_numeric, errors="coerce")
        X_df = X_df.dropna(axis=1, how="all")
        return X_df, y, le

    @staticmethod
    def _prepare_usage_xy(df: pd.DataFrame, sample_col: str, label_col: str) -> Tuple[pd.DataFrame, np.ndarray, LabelEncoder]:
        le = LabelEncoder()
        y = le.fit_transform(df[label_col].astype(str).values)
        X_df = df.drop(columns=[sample_col, label_col], errors="ignore").apply(pd.to_numeric, errors="coerce")
        X_df = X_df.dropna(axis=1, how="all")
        return X_df, y, le

    def _build_usage_feature_matrix(
        self,
        profile_samples: set,
        usage_path: Path,
        sample_col: str,
        selected_features: Optional[List[str]] = None,
    ) -> pd.DataFrame:
        if usage_path.is_file():
            files = [usage_path]
        else:
            root = self._resolve_usage_dir(usage_path)
            files = sorted([p for p in root.glob("*.csv*") if p.is_file()])
        if not files:
            return pd.DataFrame()

        feature_df = pd.DataFrame({sample_col: sorted(str(s) for s in profile_samples)})
        selected_set = {str(col) for col in (selected_features or []) if str(col)}
        for file_path in files:
            df_usage = _try_read_csv(file_path, low_memory=False, dtype=str, keep_default_na=False)
            if df_usage.empty:
                continue
            usage_sample_col = self._resolve_usage_sample_col(df_usage)
            # Exact identifiers take precedence over legacy filename aliases.
            df_usage[usage_sample_col] = df_usage[usage_sample_col].astype(str).str.strip().map(
                lambda value: value if value in profile_samples else self._normalize_sample_name(value)
            )
            df_usage = df_usage[df_usage[usage_sample_col].isin(profile_samples)].copy()
            if df_usage.empty:
                continue
            df_usage = df_usage.drop(columns=["Category", "category"], errors="ignore")
            df_usage = df_usage.rename(columns={usage_sample_col: sample_col})
            feature_cols = [c for c in df_usage.columns if c != sample_col]
            prefix = self._usage_file_prefix(file_path)
            rename_map = {col: f"{prefix}__{col}" for col in feature_cols}
            if selected_set:
                rename_map = {
                    col: renamed for col, renamed in rename_map.items()
                    if renamed in selected_set or str(col) in selected_set
                }
                if not rename_map:
                    continue
                keep_cols = [sample_col] + list(rename_map.keys())
                df_usage = df_usage[keep_cols]
            df_usage = df_usage.rename(columns=rename_map)
            for col in rename_map.values():
                df_usage[col] = pd.to_numeric(df_usage[col], errors="coerce")
            feature_cols = list(rename_map.values())
            if df_usage[sample_col].duplicated().any() and feature_cols:
                nonmissing_counts = (
                    df_usage[feature_cols]
                    .notna()
                    .groupby(df_usage[sample_col], sort=False)
                    .sum()
                )
                overlapping = nonmissing_counts.columns[
                    (nonmissing_counts > 1).any(axis=0)
                ].tolist()
                if overlapping:
                    affected = nonmissing_counts.index[
                        nonmissing_counts[overlapping].gt(1).any(axis=1)
                    ].astype(str).tolist()
                    raise ValueError(
                        "VJ usage rows contain overlapping non-missing feature values "
                        f"for sample(s) {affected[:8]}; features: {overlapping[:8]}"
                    )
            df_usage = df_usage.groupby(sample_col, as_index=False).first()
            feature_df = feature_df.merge(df_usage, on=sample_col, how="left")

        if feature_df.shape[1] <= 1:
            return pd.DataFrame()
        missing = feature_df.loc[feature_df.drop(columns=sample_col).isna().all(axis=1), sample_col]
        if not missing.empty:
            raise ValueError("部分所选样本没有匹配的 V/J 特征，请重新生成或选择上游结果：" + ", ".join(missing.head(8)))
        return feature_df

    @classmethod
    def collect_usage_feature_candidates(
        cls,
        *,
        profile_samples: set,
        usage_path: str,
        sample_col: str = "Sample",
        limit: int = 20000,
    ) -> List[Dict[str, str]]:
        root_path = Path(usage_path)
        if not usage_path or not root_path.exists():
            return []
        if root_path.is_file():
            files = [root_path]
        else:
            root = cls._resolve_usage_dir(root_path)
            files = sorted([p for p in root.glob("*.csv*") if p.is_file()])
        candidates: List[Dict[str, str]] = []
        seen = set()
        sample_values = {str(s) for s in profile_samples}
        for file_path in files:
            try:
                df_usage = _try_read_csv(file_path, low_memory=False, nrows=200, dtype=str, keep_default_na=False)
            except Exception:
                continue
            if df_usage.empty:
                continue
            usage_sample_col = cls._resolve_usage_sample_col(df_usage)
            if sample_values and usage_sample_col in df_usage.columns:
                normalized = df_usage[usage_sample_col].astype(str).str.strip().map(lambda value: value if value in sample_values else cls._normalize_sample_name(value))
                if not normalized.isin(sample_values).any():
                    continue
            prefix = cls._usage_file_prefix(file_path)
            for col in df_usage.columns:
                if col == usage_sample_col or str(col).lower() == "category":
                    continue
                key = f"{prefix}__{col}"
                if key in seen:
                    continue
                seen.add(key)
                candidates.append({
                    "value": key,
                    "label": str(col),
                    "source": prefix,
                })
                if len(candidates) >= limit:
                    return candidates
        return candidates

    @staticmethod
    def _resolve_usage_dir(path: Path) -> Path:
        for candidate in (
            path / "usage" / "1VJusage",
            path / "1VJusage",
            path / "usage_cate" / "usage" / "1VJusage",
            path / "usage" / "0VJusage",
            path / "0VJusage",
        ):
            if candidate.exists() and candidate.is_dir():
                return candidate
        return path

    @staticmethod
    def _resolve_usage_sample_col(df: pd.DataFrame) -> str:
        for candidate in ("sample", "Sample", "SAMPLE"):
            if candidate in df.columns:
                return candidate
        return df.columns[0]

    @staticmethod
    def _normalize_sample_name(value: str) -> str:
        name = str(value or "")
        name = re.sub(r"\.csv(?:\.gz)?$", "", name)
        return name.rsplit("__", 1)[0]

    @staticmethod
    def _usage_file_prefix(path: Path) -> str:
        name = path.name
        for suffix in (".csv.gz", ".tsv.gz", ".csv", ".tsv"):
            if name.lower().endswith(suffix):
                return name[:-len(suffix)]
        return path.stem

    @staticmethod
    def _slice_dir_name(mode: str, label_col: str, filter_col: str, filter_value: str) -> str:
        if filter_col and filter_value:
            return _safe_name(f"{filter_col}={filter_value}")
        return _safe_name(f"{mode}_{label_col}")

    @staticmethod
    def _select_stable_features(
        X_df: pd.DataFrame,
        y: np.ndarray,
        *,
        mode: str,
        groups: Optional[np.ndarray],
        n_splits: int,
        frequency_threshold: float,
        min_features_per_modality: int,
        progress_callback=None,
    ) -> Tuple[pd.DataFrame, int]:
        """Select fold-local RF top features and retain reproducible features.

        This mirrors script 09's per-modality Top-K selection and frequency
        threshold while fitting imputation, scaling and feature ranking only
        on each training fold. The resulting full-cohort feature list is used
        only for the deployable final model, never for outer-fold predictions.
        """
        y = np.asarray(y)
        groups = np.asarray(groups) if groups is not None else None
        if groups is not None:
            group_labels = pd.DataFrame({"group": groups, "label": y}).drop_duplicates()
            if group_labels["group"].duplicated().any():
                raise ValueError("同一受试者对应多个分类标签，无法进行分层分组稳定性筛选")
            min_class_groups = int(group_labels.groupby("label")["group"].nunique().min())
            split_count = min(int(n_splits), min_class_groups)
            if split_count < 2:
                raise ValueError("每个类别至少需要 2 名独立受试者才能进行稳定性筛选")
            cv = StratifiedGroupKFold(
                n_splits=split_count, shuffle=True, random_state=RANDOM_STATE
            )
            split_iter = cv.split(X_df, y, groups)
        else:
            min_class_samples = int(pd.Series(y).value_counts().min())
            split_count = min(int(n_splits), min_class_samples)
            if split_count < 2:
                raise ValueError("每个类别至少需要 2 个样本才能进行稳定性筛选")
            cv = StratifiedKFold(
                n_splits=split_count, shuffle=True, random_state=RANDOM_STATE
            )
            split_iter = cv.split(X_df, y)

        def modality(feature: str) -> str:
            if mode == "vj":
                return "vj"
            if mode == "profile":
                return "profile"
            return "profile" if str(feature).lower().startswith("profile__") else "vj"

        top_k = {"vj": 20, "profile": 10}
        records: List[Dict[str, Any]] = []
        for fold, (train_idx, _) in enumerate(split_iter, start=1):
            train = X_df.iloc[train_idx]
            columns: List[str] = []
            arrays: List[np.ndarray] = []
            for column in X_df.columns:
                values = pd.to_numeric(train[column], errors="coerce")
                if modality(column) in {"vj", "profile"}:
                    fill_value = 0.0
                elif values.notna().any():
                    fill_value = float(values.mean())
                else:
                    continue
                array = values.fillna(fill_value).to_numpy(dtype=float)
                if np.std(array) <= np.finfo(float).eps:
                    continue
                columns.append(str(column))
                arrays.append(array)
            if not columns:
                continue
            scaled = StandardScaler().fit_transform(np.column_stack(arrays))
            selector = RandomForestClassifier(
                n_estimators=100,
                class_weight="balanced",
                random_state=RANDOM_STATE,
                n_jobs=1,
            ).fit(scaled, y[train_idx])
            importance = selector.feature_importances_
            by_modality: Dict[str, List[int]] = {}
            for index, column in enumerate(columns):
                by_modality.setdefault(modality(column), []).append(index)
            for modality_name, indices in by_modality.items():
                ranked = sorted(indices, key=lambda i: (-importance[i], columns[i]))
                for index in ranked[: min(top_k[modality_name], len(ranked))]:
                    records.append({
                        "fold": fold,
                        "feature": columns[index],
                        "modality": modality_name,
                        "selector_importance": float(importance[index]),
                    })
            if progress_callback:
                progress_callback(
                    12 + int(10 * fold / split_count),
                    "稳定特征筛选",
                    f"已完成第 {fold}/{split_count} 折训练特征筛选",
                    {"phase": "stability_selection", "fold": fold, "folds": split_count},
                )

        if not records:
            raise ValueError("稳定性筛选未在任何训练折中找到可用特征")
        table = (
            pd.DataFrame(records)
            .groupby(["feature", "modality"], as_index=False)
            .agg(
                selection_count=("feature", "size"),
                mean_selector_importance=("selector_importance", "mean"),
            )
        )
        table["selection_frequency"] = table["selection_count"] / split_count
        minimum_count = max(1, int(np.ceil(split_count * frequency_threshold)))
        table["minimum_selection_count"] = minimum_count
        table["selected_for_final_model"] = table["selection_count"] >= minimum_count
        table["selection_reason"] = np.where(
            table["selected_for_final_model"], "frequency_threshold", "not_selected"
        )
        table["minimum_features_target"] = 0
        for modality_name in sorted(table["modality"].unique()):
            mask = table["modality"] == modality_name
            target = min(
                min_features_per_modality,
                top_k[modality_name],
                int(mask.sum()),
            )
            table.loc[mask, "minimum_features_target"] = target
            deficit = max(0, target - int(table.loc[mask, "selected_for_final_model"].sum()))
            if deficit:
                fill_indices = (
                    table.loc[mask & ~table["selected_for_final_model"]]
                    .sort_values(
                        ["selection_count", "mean_selector_importance", "feature"],
                        ascending=[False, False, True],
                    )
                    .head(deficit)
                    .index
                )
                table.loc[fill_indices, "selected_for_final_model"] = True
                table.loc[fill_indices, "selection_reason"] = "frequency_rank_fill"
        table = table.sort_values(
            ["modality", "selection_frequency", "mean_selector_importance", "feature"],
            ascending=[True, False, False, True],
        ).reset_index(drop=True)
        return table, split_count

    def _run_classifier(
        self,
        *,
        X_df: pd.DataFrame,
        y: np.ndarray,
        le: LabelEncoder,
        sample_ids: np.ndarray,
        group_ids: Optional[np.ndarray],
        model_key: str,
        out_dir: Path,
        custom_threshold: float,
        cv_splits: int,
        final_feature_cols: Optional[List[str]] = None,
        feature_mode: str = "profile",
        progress_callback=None,
    ) -> Dict[str, Any]:
        out_dir.mkdir(parents=True, exist_ok=True)
        csv_paths: List[str] = []
        text_paths: List[str] = []
        png_paths: List[str] = []
        pdf_paths: List[str] = []
        X_df = X_df.loc[:, X_df.notna().any(axis=0)]
        if X_df.shape[1] == 0:
            raise ValueError("所有输入特征均为空，无法进行机器学习分析")

        grid, best_model, cv_fold_metrics, oof_prediction, oof_probability = self._train_classifier_cv(
            X_df, y, cv_splits, custom_threshold, model_key=model_key,
            groups=group_ids, final_feature_cols=final_feature_cols,
            feature_mode=feature_mode,
            progress_callback=progress_callback
        )
        cv_scores = np.asarray([record["accuracy"] for record in cv_fold_metrics])
        cv_strategy = "stratified_group_k_fold" if group_ids is not None else "stratified_k_fold"
        if final_feature_cols is not None:
            feat_names = [name for name in final_feature_cols if name in X_df.columns]
        else:
            selector = best_model.named_steps["selector"]
            feat_names = X_df.columns[selector.get_support()].tolist()
        if not feat_names:
            raise ValueError(f"{SUPPORTED_ML_MODELS[model_key]}特征筛选未保留任何特征")
        selected_path = out_dir / "selected_features.csv"
        pd.DataFrame({"feature": feat_names}).to_csv(selected_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(selected_path))

        cv_path = out_dir / "cross_validation_scores.csv"
        pd.DataFrame(cv_fold_metrics).to_csv(cv_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(cv_path))
        self._plot_cv_accuracy(cv_scores, out_dir, png_paths, pdf_paths)

        self._save_classification_and_confusion(oof_prediction, y, le, out_dir, csv_paths, text_paths, png_paths, pdf_paths)
        prediction_path = out_dir / "out_of_fold_predictions.csv"
        prediction_frame = pd.DataFrame({
            "sample": sample_ids,
            "observed": le.inverse_transform(y),
            "predicted": le.inverse_transform(oof_prediction),
        })
        if group_ids is not None:
            prediction_frame.insert(1, "group", group_ids)
        for class_code, class_name in enumerate(le.classes_):
            prediction_frame[f"proba_{_safe_name(class_name)}"] = oof_probability[:, class_code]
        prediction_frame.to_csv(prediction_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(prediction_path))
        if len(np.unique(y)) == 2:
            oof_roc_auc = float(roc_auc_score(y, oof_probability[:, 1]))
            oof_average_precision = float(average_precision_score(y, oof_probability[:, 1]))
        else:
            binary_y = label_binarize(y, classes=np.arange(len(le.classes_)))
            oof_roc_auc = float(roc_auc_score(y, oof_probability, multi_class="ovr", average="macro"))
            oof_average_precision = float(average_precision_score(binary_y, oof_probability, average="macro"))
        self._save_feature_importance(X_df, y, out_dir, custom_threshold, csv_paths, png_paths, pdf_paths)
        try:
            self._save_roc_curve(y, oof_probability, le, out_dir, csv_paths, text_paths, png_paths, pdf_paths)
        except Exception as exc:
            skip_path = out_dir / "ROC_skipped.txt"
            skip_path.write_text(str(exc), encoding="utf-8")
            text_paths.append(str(skip_path))

        mapping_path = out_dir / "label_mapping.txt"
        mapping_path.write_text(
            "分类标签编码：\n" + "\n".join(f"{code}: {cls}" for code, cls in enumerate(le.classes_)),
            encoding="utf-8",
        )
        text_paths.append(str(mapping_path))

        summary_lines = [
            f"分类模型: {SUPPORTED_ML_MODELS[model_key]}",
            f"\u6837\u672c\u6570: {X_df.shape[0]}",
            f"\u539f\u59cb\u7279\u5f81\u6570: {X_df.shape[1]}",
            f"\u7b5b\u9009\u540e\u7279\u5f81\u6570: {len(feat_names)}",
            f"\u5168\u6837\u672c\u6a21\u578b\u53c2\u6570: {grid.best_params_}",
            f"\u5d4c\u5957\u4ea4\u53c9\u9a8c\u8bc1\u5e73\u5747\u51c6\u786e\u7387: {np.mean(cv_scores)}",
            f"\u4ea4\u53c9\u9a8c\u8bc1\u51c6\u786e\u7387\u6807\u51c6\u5dee: {np.std(cv_scores)}",
            f"\u5d4c\u5957 CV \u5e73\u5747\u5e73\u8861\u51c6\u786e\u7387: {np.mean([row['balanced_accuracy'] for row in cv_fold_metrics])}",
            f"\u5d4c\u5957 CV \u5e73\u5747 Macro-F1: {np.mean([row['macro_f1'] for row in cv_fold_metrics])}",
            "\u8bc4\u4f30\u65b9\u6cd5: \u5206\u5c42\u5d4c\u5957\u4ea4\u53c9\u9a8c\u8bc1\uff1b\u7f3a\u5931\u503c\u586b\u8865\u3001\u6807\u51c6\u5316\u3001\u7279\u5f81\u7b5b\u9009\u548c\u53c2\u6570\u8c03\u4f18\u5747\u4ec5\u5728\u8bad\u7ec3\u6298\u5185\u62df\u5408\u3002",
            "\u9a8c\u8bc1\u6307\u6807\u57fa\u4e8e\u6bcf\u4e2a\u6837\u672c\u7684\u5916\u5c42\u7559\u51fa\u9884\u6d4b\uff1b\u5bfc\u51fa\u7684\u7279\u5f81\u5217\u8868\u6765\u81ea\u5168\u6837\u672c\u62df\u5408\u7684\u6700\u7ec8\u6a21\u578b\u3002",
        ]
        summary_path = out_dir / "summary.txt"
        summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
        text_paths.append(str(summary_path))

        return {
            "csv_paths": csv_paths,
            "text_paths": text_paths,
            "png_paths": png_paths,
            "pdf_paths": pdf_paths,
            "summary": {
                "selected_feature_number": int(len(feat_names)),
                "best_params": grid.best_params_,
                "final_model_params": grid.best_params_,
                "nested_cv_mean_accuracy": float(np.mean(cv_scores)),
                "nested_cv_outer_folds": int(len(cv_fold_metrics)),
                "mean_cv_accuracy": float(np.mean(cv_scores)),
                "std_cv_accuracy": float(np.std(cv_scores)),
                "nested_cv_mean_balanced_accuracy": float(np.mean([row["balanced_accuracy"] for row in cv_fold_metrics])),
                "nested_cv_mean_macro_f1": float(np.mean([row["macro_f1"] for row in cv_fold_metrics])),
                "roc_auc": oof_roc_auc,
                "average_precision": oof_average_precision,
                "evaluation_method": f"nested_{cv_strategy}",
            },
        }

    def _run_random_forest(self, **kwargs) -> Dict[str, Any]:
        """Keep the original service entry point for queued-job compatibility."""
        return self._run_classifier(model_key="random_forest", **kwargs)

    @staticmethod
    def _classifier_grid(model_key: str, train_size: int, inner_splits: int, n_classes: int = 2):
        if model_key == "random_forest":
            estimator = RandomForestClassifier(class_weight="balanced", random_state=RANDOM_STATE)
            grid = {
                "classifier__n_estimators": [50, 100, 200],
                "classifier__max_depth": [None, 5, 10, 20],
                "classifier__min_samples_split": [2, 5, 10],
            }
        elif model_key == "extra_trees":
            estimator = ExtraTreesClassifier(class_weight="balanced", random_state=RANDOM_STATE)
            grid = {
                "classifier__n_estimators": [100, 200],
                "classifier__max_depth": [None, 6],
                "classifier__min_samples_leaf": [1, 2],
            }
        elif model_key in {"logistic_l1", "logistic_l2"}:
            penalty = "l1" if model_key == "logistic_l1" else "l2"
            solver = "saga" if penalty == "l1" else "lbfgs"
            estimator = LogisticRegression(
                penalty=penalty, solver=solver, class_weight="balanced",
                max_iter=5000, random_state=RANDOM_STATE,
            )
            grid = {"classifier__C": [0.1, 1.0, 10.0]}
        elif model_key == "gaussian_nb":
            estimator = GaussianNB()
            grid = {"classifier__var_smoothing": [1e-11, 1e-9, 1e-7]}
        elif model_key == "knn":
            estimator = KNeighborsClassifier()
            smallest_training_fold = max(1, train_size - int(np.ceil(train_size / inner_splits)))
            neighbours = [k for k in (3, 5, 7) if k <= smallest_training_fold] or [1]
            grid = {
                "classifier__n_neighbors": neighbours,
                "classifier__weights": ["uniform", "distance"],
            }
        elif model_key in {"rbf_svm", "linear_svm"}:
            kernel = "rbf" if model_key == "rbf_svm" else "linear"
            estimator = SVC(
                kernel=kernel, probability=True, class_weight="balanced",
                random_state=RANDOM_STATE,
            )
            grid = {"classifier__C": [0.1, 1.0, 10.0]}
            if kernel == "rbf":
                grid["classifier__gamma"] = ["scale", 0.01, 0.1]
        elif model_key == "gradient_boosting":
            estimator = GradientBoostingClassifier(random_state=RANDOM_STATE)
            grid = {
                "classifier__n_estimators": [100, 200],
                "classifier__learning_rate": [0.03, 0.1],
                "classifier__max_depth": [2, 3],
            }
        elif model_key == "xgboost":
            from xgboost import XGBClassifier

            objective = "binary:logistic" if n_classes == 2 else "multi:softprob"
            estimator = XGBClassifier(
                objective=objective,
                eval_metric="logloss" if n_classes == 2 else "mlogloss",
                random_state=RANDOM_STATE,
                n_jobs=1,
            )
            grid = {
                "classifier__n_estimators": [100, 300],
                "classifier__max_depth": [2, 4],
                "classifier__learning_rate": [0.03, 0.1],
            }
        else:
            raise ValueError(f"不支持的机器学习模型：{model_key}")
        return estimator, grid

    @staticmethod
    def _train_classifier_cv(
        X_df: pd.DataFrame,
        y: np.ndarray,
        cv_splits: int,
        threshold: float,
        *,
        model_key: str = "random_forest",
        groups: Optional[np.ndarray] = None,
        final_feature_cols: Optional[List[str]] = None,
        feature_mode: str = "profile",
        progress_callback=None,
    ):
        min_count = int(pd.Series(y).value_counts().min())
        y = np.asarray(y)
        groups = np.asarray(groups) if groups is not None else None
        if groups is not None:
            if len(groups) != len(y):
                raise ValueError("受试者分组数量必须与样本数量一致")
            if pd.isna(groups).any() or any(not str(group).strip() for group in groups):
                raise ValueError("受试者分组列存在空值，请补全后再运行分组交叉验证")
            groups = np.asarray([str(group).strip() for group in groups])
            group_labels = pd.DataFrame({"group": groups, "label": y}).drop_duplicates()
            if group_labels["group"].duplicated().any():
                raise ValueError("同一受试者对应多个分类标签，无法进行分层分组交叉验证")
            min_count = int(group_labels.groupby("label")["group"].nunique().min())
        n_outer = min(int(cv_splits or 3), min_count)
        if n_outer < 2:
            raise ValueError("每个类别至少需要 2 个独立受试者/样本才能进行分层交叉验证")
        X = X_df.to_numpy(dtype=float)
        if groups is not None:
            outer_cv = StratifiedGroupKFold(
                n_splits=n_outer, shuffle=True, random_state=RANDOM_STATE
            )
        else:
            outer_cv = StratifiedKFold(n_splits=n_outer, shuffle=True, random_state=RANDOM_STATE)
        oof_prediction = np.empty_like(y)
        oof_probability = np.zeros((len(y), len(np.unique(y))), dtype=float)
        cv_scores = []
        cv_fold_metrics = []
        split_iter = outer_cv.split(X, y, groups) if groups is not None else outer_cv.split(X, y)
        for fold, (train_idx, test_idx) in enumerate(split_iter, start=1):
            if groups is None:
                inner_min = int(pd.Series(y[train_idx]).value_counts().min())
            else:
                inner_pairs = pd.DataFrame({"group": groups[train_idx], "label": y[train_idx]}).drop_duplicates()
                inner_min = int(inner_pairs.groupby("label")["group"].nunique().min())
            n_inner = min(n_outer, inner_min)
            if n_inner < 2:
                raise ValueError("外层训练折中的类别样本不足，无法进行内层参数调优")
            if groups is not None:
                inner_cv = StratifiedGroupKFold(
                    n_splits=n_inner, shuffle=True, random_state=RANDOM_STATE
                )
            else:
                inner_cv = StratifiedKFold(n_splits=n_inner, shuffle=True, random_state=RANDOM_STATE)
            classifier, param_grid = MLAnalysisService._classifier_grid(
                model_key, len(train_idx), n_inner, n_classes=len(np.unique(y))
            )
            fold_selector = (
                _FoldLocalTopKSelector(tuple(X_df.columns), feature_mode)
                if final_feature_cols is not None
                else SelectFromModel(
                    RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE),
                    threshold=threshold,
                )
            )
            fold_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=0.0, keep_empty_features=True)),
                ("scaler", StandardScaler()),
                ("selector", fold_selector),
                ("classifier", classifier),
            ])
            grid = GridSearchCV(
                fold_pipeline, param_grid, cv=inner_cv, scoring="balanced_accuracy", n_jobs=1, refit=True
            )
            fit_params = {"groups": groups[train_idx]} if groups is not None else {}
            grid.fit(X[train_idx], y[train_idx], **fit_params)
            oof_prediction[test_idx] = grid.predict(X[test_idx])
            probabilities = grid.predict_proba(X[test_idx])
            for local_idx, class_code in enumerate(grid.classes_):
                oof_probability[test_idx, int(class_code)] = probabilities[:, local_idx]
            cv_scores.append(float(accuracy_score(y[test_idx], oof_prediction[test_idx])))
            fold_record = {
                "fold": fold,
                "n_train": len(train_idx),
                "n_test": len(test_idx),
                "inner_best_score": float(grid.best_score_),
                "inner_best_params": json.dumps(grid.best_params_, sort_keys=True),
                "accuracy": cv_scores[-1],
                "balanced_accuracy": float(balanced_accuracy_score(y[test_idx], oof_prediction[test_idx])),
                "macro_f1": float(f1_score(y[test_idx], oof_prediction[test_idx], average="macro", zero_division=0)),
            }
            if len(np.unique(y)) == 2 and len(np.unique(y[test_idx])) == 2:
                fold_record["roc_auc"] = float(roc_auc_score(y[test_idx], oof_probability[test_idx, 1]))
                fold_record["pr_auc"] = float(average_precision_score(y[test_idx], oof_probability[test_idx, 1]))
            cv_fold_metrics.append(fold_record)
            if progress_callback:
                strategy_label = "受试者分组" if groups is not None else "样本分层"
                progress_callback(35 + int(40 * fold / n_outer), "机器学习分析", f"已完成第 {fold}/{n_outer} 折{strategy_label}嵌套交叉验证")

        if groups is not None:
            final_inner = StratifiedGroupKFold(
                n_splits=n_outer, shuffle=True, random_state=RANDOM_STATE
            )
        else:
            final_inner = StratifiedKFold(n_splits=n_outer, shuffle=True, random_state=RANDOM_STATE)
        final_classifier, final_param_grid = MLAnalysisService._classifier_grid(
            model_key, len(y), n_outer, n_classes=len(np.unique(y))
        )
        if final_feature_cols is not None:
            missing_final = [column for column in final_feature_cols if column not in X_df.columns]
            if missing_final:
                raise ValueError(f"稳定特征不在训练矩阵中：{', '.join(missing_final[:5])}")
            final_X = X_df.loc[:, final_feature_cols].to_numpy(dtype=float)
            final_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=0.0, keep_empty_features=True)),
                ("scaler", StandardScaler()),
                ("classifier", final_classifier),
            ])
        else:
            final_X = X
            final_pipeline = Pipeline([
                ("imputer", SimpleImputer(strategy="constant", fill_value=0.0, keep_empty_features=True)),
                ("scaler", StandardScaler()),
                ("selector", SelectFromModel(
                    RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE),
                    threshold=threshold,
                )),
                ("classifier", final_classifier),
            ])
        final_grid = GridSearchCV(
            final_pipeline, final_param_grid, cv=final_inner,
            scoring="balanced_accuracy", n_jobs=1, refit=True
        )
        final_fit_params = {"groups": groups} if groups is not None else {}
        final_grid.fit(final_X, y, **final_fit_params)
        return final_grid, final_grid.best_estimator_, cv_fold_metrics, oof_prediction, oof_probability

    @staticmethod
    def _train_rf_cv(
        X_df: pd.DataFrame,
        y: np.ndarray,
        cv_splits: int,
        threshold: float,
        groups: Optional[np.ndarray] = None,
        progress_callback=None,
    ):
        """Compatibility wrapper for existing tests and internal callers."""
        return MLAnalysisService._train_classifier_cv(
            X_df, y, cv_splits, threshold, model_key="random_forest",
            groups=groups, progress_callback=progress_callback,
        )

    @staticmethod
    def _plot_cv_accuracy(cv_scores, out_dir: Path, png_paths: List[str], pdf_paths: List[str]) -> None:
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        folds = np.arange(1, len(cv_scores) + 1)
        ax.bar(folds, cv_scores, color=PALETTE["blue"], edgecolor="white", linewidth=0.7)
        mean_score = np.mean(cv_scores)
        ax.plot(folds, [mean_score] * len(cv_scores), linestyle="--", color=PALETTE["red"],
                label=f"平均值 = {mean_score:.4f}", linewidth=1.8)
        ax.set_xlabel("\u4ea4\u53c9\u9a8c\u8bc1\u6298")
        ax.set_ylabel("\u51c6\u786e\u7387")
        ax.set_title("\u5d4c\u5957\u4ea4\u53c9\u9a8c\u8bc1\u5404\u6298\u51c6\u786e\u7387")
        ax.set_xticks(folds)
        soften_axes(ax)
        ax.legend()
        fig.tight_layout()
        png_path = out_dir / "cross_validation_accuracy.png"
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))

    @staticmethod
    def _save_classification_and_confusion(y_pred, y, le, out_dir, csv_paths, text_paths, png_paths, pdf_paths):
        report = classification_report(
            y, y_pred, target_names=[str(label) for label in le.classes_], zero_division=0
        )
        report_path = out_dir / "classification_report.txt"
        report_path.write_text(report, encoding="utf-8")
        text_paths.append(str(report_path))

        cm = confusion_matrix(y, y_pred)
        cm_path = out_dir / "confusion_matrix.csv"
        pd.DataFrame(cm, index=le.classes_, columns=le.classes_).to_csv(cm_path, encoding="utf-8-sig")
        csv_paths.append(str(cm_path))

        fig, ax = plt.subplots(figsize=(5.6, 4.8))
        im = ax.imshow(cm, interpolation="nearest", cmap=MUTED_BLUE_RED_CMAP)
        ax.set_title("\u6df7\u6dc6\u77e9\u9635")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        tick_marks = np.arange(len(le.classes_))
        ax.set_xticks(tick_marks, le.classes_, rotation=45, ha="right")
        ax.set_yticks(tick_marks, le.classes_)
        ax.set_xlabel("\u9884\u6d4b\u7c7b\u522b")
        ax.set_ylabel("\u5b9e\u9645\u7c7b\u522b")
        thresh = cm.max() / 2.0 if cm.size else 0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(j, i, format(cm[i, j], "d"), horizontalalignment="center",
                        color="white" if cm[i, j] > thresh else PALETTE["neutral_dark"])
        fig.tight_layout()
        png_path = out_dir / "confusion_matrix.png"
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))

    @staticmethod
    def _save_feature_importance(X_df, y, out_dir, custom_threshold, csv_paths, png_paths, pdf_paths):
        valid_cols = X_df.columns[X_df.notna().any()].tolist()
        if not valid_cols:
            return
        X_original = SimpleImputer(strategy="constant", fill_value=0.0).fit_transform(X_df[valid_cols].to_numpy(dtype=float))
        X_original = StandardScaler().fit_transform(X_original)
        rf = RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)
        rf.fit(X_original, y)
        selector = SelectFromModel(rf, threshold=custom_threshold, prefit=True)
        mask = selector.get_support()
        importances = rf.feature_importances_
        selected_importances = importances[mask]
        selected_names = np.array(valid_cols)[mask]
        if len(selected_importances) == 0:
            return
        imp_path = out_dir / "feature_importance.csv"
        pd.DataFrame({"feature": selected_names, "importance": selected_importances}).sort_values(
            "importance", ascending=False
        ).to_csv(imp_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(imp_path))

        top_n = min(20, len(selected_importances))
        idx = np.argsort(selected_importances)[::-1][:top_n]
        fig, ax = plt.subplots(figsize=(7.2, 4.8))
        ax.bar(range(top_n), selected_importances[idx], align="center", color=PALETTE["blue"], edgecolor="white", linewidth=0.6)
        ax.set_xticks(range(top_n), selected_names[idx], rotation=45, ha="right")
        ax.set_xlabel("\u7279\u5f81")
        ax.set_ylabel("\u91cd\u8981\u6027")
        ax.set_title(f"\u524d {top_n} \u4e2a\u7279\u5f81\u91cd\u8981\u6027")
        soften_axes(ax)
        fig.tight_layout()
        png_path = out_dir / "top20_feature_importances.png"
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))

    @staticmethod
    def _save_roc_curve(y, y_score_all, le, out_dir, csv_paths, text_paths, png_paths, pdf_paths):
        classes = np.unique(y)
        n_classes = len(classes)
        y_test_all = y
        if len(y_score_all) != len(y):
            raise ValueError("ROC 预测分数与样本数不一致")

        fig, ax = plt.subplots(figsize=(5.8, 5.0))
        if n_classes == 2:
            pos_label = classes[1]
            pos_col = np.where(classes == pos_label)[0][0]
            pos_name = le.classes_[pos_label]
            fpr, tpr, _ = roc_curve(y_test_all, y_score_all[:, pos_col], pos_label=pos_label)
            roc_auc = auc(fpr, tpr)
            pd.DataFrame({"fpr": fpr, "tpr": tpr, "class": pos_name, "auc": roc_auc}).to_csv(
                out_dir / "ROC_curve_points.csv", index=False, encoding="utf-8-sig"
            )
            ax.plot(fpr, tpr, lw=1.8, color=PALETTE["blue"], label=f"{pos_name} AUC = {roc_auc:.4f}")
            auc_text = f"{pos_name} AUC = {roc_auc:.6f}\n"
        else:
            y_bin = label_binarize(y_test_all, classes=classes)
            roc_records, auc_lines = [], []
            for i, cls in enumerate(classes):
                fpr, tpr, _ = roc_curve(y_bin[:, i], y_score_all[:, i])
                roc_auc = auc(fpr, tpr)
                auc_lines.append(f"{le.classes_[cls]} 相对于其他类别 AUC = {roc_auc:.6f}")
                roc_records.append(pd.DataFrame({"class": le.classes_[cls], "fpr": fpr, "tpr": tpr, "auc": roc_auc}))
                ax.plot(
                    fpr,
                    tpr,
                    lw=1.8,
                    color=MUTED_CATEGORY_COLORS[i % len(MUTED_CATEGORY_COLORS)],
                    label=f"{le.classes_[cls]} AUC = {roc_auc:.4f}",
                )
            pd.concat(roc_records, axis=0).to_csv(out_dir / "ROC_curve_points.csv", index=False, encoding="utf-8-sig")
            auc_text = "\n".join(auc_lines) + "\n"
            auc_text += f"宏平均 AUC = {roc_auc_score(y_bin, y_score_all, average='macro', multi_class='ovr'):.6f}\n"
            auc_text += f"微平均 AUC = {roc_auc_score(y_bin, y_score_all, average='micro', multi_class='ovr'):.6f}\n"

        csv_paths.append(str(out_dir / "ROC_curve_points.csv"))
        ax.plot([0, 1], [0, 1], linestyle="--", color=PALETTE["neutral_mid"], lw=0.9)
        ax.set_xlabel("\u5047\u9633\u6027\u7387")
        ax.set_ylabel("\u771f\u9633\u6027\u7387")
        ax.set_title("\u5d4c\u5957\u4ea4\u53c9\u9a8c\u8bc1 ROC \u66f2\u7ebf" if n_classes == 2 else "\u5d4c\u5957\u4ea4\u53c9\u9a8c\u8bc1\u591a\u5206\u7c7b ROC \u66f2\u7ebf")
        soften_axes(ax, grid_axis="both")
        ax.legend(loc="lower right", fontsize=9)
        fig.tight_layout()
        png_path = out_dir / "ROC_AUC.png"
        save_publication_png(fig, png_path)
        plt.close(fig)
        png_paths.append(str(png_path))
        auc_path = out_dir / "ROC_AUC.txt"
        auc_path.write_text(auc_text, encoding="utf-8")
        text_paths.append(str(auc_path))

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{_safe_name(name)}_{ts}"
