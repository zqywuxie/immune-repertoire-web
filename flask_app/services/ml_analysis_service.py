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
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectFromModel
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    auc,
    classification_report,
    confusion_matrix,
    roc_auc_score,
    roc_curve,
)
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_score
from sklearn.preprocessing import LabelEncoder, StandardScaler, label_binarize

from flask_app.services.figure_style import (
    MUTED_BLUE_RED_CMAP,
    MUTED_CATEGORY_COLORS,
    PALETTE,
    apply_publication_style,
    soften_axes,
)

_CSV_ENCODINGS = ["utf-8", "gbk", "gb2312", "gb18030", "latin-1"]

RANDOM_STATE = 42
DEFAULT_THRESHOLD = 0.003

apply_publication_style(font_size=10, axes_linewidth=0.9)


def _try_read_csv(filepath, **kwargs):
    suffix = str(filepath).lower()
    sep = kwargs.pop("sep", ",")
    if suffix.endswith((".tsv", ".tsv.gz")):
        sep = "\t"
    if suffix.endswith((".xlsx", ".xls", ".xlsm")):
        return pd.read_excel(filepath, sheet_name=kwargs.pop("sheet_name", 0), **kwargs)
    for enc in _CSV_ENCODINGS:
        try:
            return pd.read_csv(filepath, encoding=enc, sep=sep, compression="infer", **kwargs)
        except (UnicodeDecodeError, UnicodeError):
            continue
    return pd.read_csv(filepath, sep=sep, compression="infer", **kwargs)


def _safe_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.=-]+", "_", str(value or "ml")).strip("_")
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


class MLAnalysisService:
    """Random-forest ML workflow for Profile features or cached VJ usage."""

    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    def generate_report(
        self,
        *,
        profile_path: str,
        mode: str = "profile",
        label_col: str,
        sample_col: str = "Sample",
        param_begin: str = "",
        param_over: str = "",
        usage_path: str = "",
        filter_col: str = "",
        filter_value: str = "",
        feature_cols: Optional[List[str]] = None,
        usage_feature_cols: Optional[List[str]] = None,
        custom_threshold: float = DEFAULT_THRESHOLD,
        cv_splits: int = 3,
        roc_cv_splits: int = 7,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> MLAnalysisReport:
        profile_file = Path(profile_path)
        if not profile_file.exists():
            raise FileNotFoundError(f"Profile file not found: {profile_path}")
        mode = str(mode or "profile").strip().lower()
        if mode not in {"profile", "vj-usage"}:
            raise ValueError("mode must be profile or vj-usage")

        profile_df = _try_read_csv(profile_file, low_memory=False)
        sample_col = self._resolve_column(profile_df, sample_col, ["Sample", "sample", "SAMPLE"])
        if label_col not in profile_df.columns:
            raise ValueError(f"label_col not found: {label_col}")

        work_df = profile_df.copy()
        if filter_col and filter_col in work_df.columns and filter_value:
            work_df = work_df[work_df[filter_col].astype(str) == str(filter_value)].copy()
        work_df = work_df.dropna(subset=[sample_col, label_col]).copy()
        work_df[sample_col] = work_df[sample_col].astype(str)
        work_df[label_col] = work_df[label_col].astype(str)
        work_df = work_df.drop_duplicates(subset=[sample_col], keep="first")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "ml_analysis")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(10, "ML analysis", "Preparing feature matrix")

        if mode == "profile":
            X_df, y, le = self._prepare_profile_xy(
                work_df, sample_col, label_col, param_begin, param_over, feature_cols
            )
            merged_path = output_base / "profile_feature_matrix.csv"
            pd.concat([work_df[[sample_col, label_col]].reset_index(drop=True), X_df.reset_index(drop=True)], axis=1).to_csv(
                merged_path, index=False, encoding="utf-8-sig"
            )
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
            merged = work_df[[sample_col, label_col]].merge(feature_df, on=sample_col, how="inner")
            if merged.empty:
                raise ValueError("No samples matched between Profile and usage data")
            merged_path = output_base / "merged_feature_matrix.csv"
            merged.to_csv(merged_path, index=False, encoding="utf-8-sig")
            X_df, y, le = self._prepare_usage_xy(merged, sample_col, label_col)

        if X_df.shape[0] < 3 or len(np.unique(y)) < 2:
            raise ValueError("Need at least 3 samples and 2 label classes for ML analysis")
        if X_df.shape[1] == 0:
            raise ValueError("No numeric feature columns available")

        if progress_callback:
            progress_callback(25, "ML analysis", f"Training random forest with {X_df.shape[1]} raw features")

        out_dir = output_base / self._slice_dir_name(mode, label_col, filter_col, filter_value)
        out_dir.mkdir(parents=True, exist_ok=True)

        report_paths = self._run_random_forest(
            X_df=X_df,
            y=y,
            le=le,
            out_dir=out_dir,
            custom_threshold=custom_threshold,
            cv_splits=cv_splits,
            roc_cv_splits=roc_cv_splits,
            progress_callback=progress_callback,
        )

        metadata = {
            "job_id": job_id,
            "generated_at": datetime.now().isoformat(),
            "mode": mode,
            "profile_path": str(profile_file.resolve()),
            "usage_path": str(Path(usage_path).resolve()) if usage_path else "",
            "sample_col": sample_col,
            "label_col": label_col,
            "filter_col": filter_col,
            "filter_value": filter_value,
            "param_begin": param_begin,
            "param_over": param_over,
            "feature_cols": feature_cols or [],
            "usage_feature_cols": usage_feature_cols or [],
            "samples": int(X_df.shape[0]),
            "raw_feature_number": int(X_df.shape[1]),
            "custom_threshold": custom_threshold,
            **report_paths["summary"],
        }
        (output_base / "ml_analysis_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        csv_paths = [str(merged_path)] + report_paths["csv_paths"]
        text_paths = report_paths["text_paths"]
        png_paths = report_paths["png_paths"]
        pdf_paths = report_paths["pdf_paths"]

        zip_path = output_base / "ml_analysis_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in [output_base / "ml_analysis_metadata.json"] + [Path(p) for p in csv_paths + text_paths + png_paths + pdf_paths]:
                if path.exists():
                    zf.write(path, path.relative_to(output_base).as_posix())

        if progress_callback:
            progress_callback(100, "ML analysis", "Completed")

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
                start, end = end, start
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
            df_usage = _try_read_csv(file_path, low_memory=False)
            if df_usage.empty:
                continue
            usage_sample_col = self._resolve_usage_sample_col(df_usage)
            df_usage[usage_sample_col] = df_usage[usage_sample_col].astype(str).map(self._normalize_sample_name)
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
            df_usage = df_usage.groupby(sample_col, as_index=False).first()
            feature_df = feature_df.merge(df_usage, on=sample_col, how="left")

        if feature_df.shape[1] <= 1:
            return pd.DataFrame()
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
                df_usage = _try_read_csv(file_path, low_memory=False, nrows=200)
            except Exception:
                continue
            if df_usage.empty:
                continue
            usage_sample_col = cls._resolve_usage_sample_col(df_usage)
            if sample_values and usage_sample_col in df_usage.columns:
                normalized = df_usage[usage_sample_col].astype(str).map(cls._normalize_sample_name)
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

    def _run_random_forest(
        self,
        *,
        X_df: pd.DataFrame,
        y: np.ndarray,
        le: LabelEncoder,
        out_dir: Path,
        custom_threshold: float,
        cv_splits: int,
        roc_cv_splits: int,
        progress_callback=None,
    ) -> Dict[str, Any]:
        csv_paths: List[str] = []
        text_paths: List[str] = []
        png_paths: List[str] = []
        pdf_paths: List[str] = []

        X = SimpleImputer(strategy="mean").fit_transform(X_df.values)
        X = StandardScaler().fit_transform(X)

        rf = RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)
        rf.fit(X, y)
        selector = SelectFromModel(rf, threshold=custom_threshold, prefit=True)
        X_sel = selector.transform(X)
        feat_names = X_df.columns[selector.get_support()].tolist()
        if X_sel.shape[1] == 0:
            raise ValueError("No selected features after RandomForest threshold filtering")

        selected_path = out_dir / "selected_features.csv"
        pd.DataFrame({"feature": feat_names}).to_csv(selected_path, index=False, encoding="utf-8-sig")
        csv_paths.append(str(selected_path))

        if progress_callback:
            progress_callback(45, "ML analysis", f"Selected {X_sel.shape[1]} features")

        grid, best_rf, cv_scores, min_count = self._train_rf_cv(X_sel, y, cv_splits)
        cv_path = out_dir / "cross_validation_scores.csv"
        pd.DataFrame({"fold": np.arange(1, len(cv_scores) + 1), "accuracy": cv_scores}).to_csv(
            cv_path, index=False, encoding="utf-8-sig"
        )
        csv_paths.append(str(cv_path))
        self._plot_cv_accuracy(cv_scores, out_dir, png_paths, pdf_paths)

        self._save_classification_and_confusion(best_rf, X_sel, y, le, out_dir, csv_paths, text_paths, png_paths, pdf_paths)
        self._save_feature_importance(X_df, y, out_dir, custom_threshold, csv_paths, png_paths, pdf_paths)
        try:
            self._save_roc_curve(X_sel, y, le, grid, min_count, roc_cv_splits, out_dir, csv_paths, text_paths, png_paths, pdf_paths)
        except Exception as exc:
            skip_path = out_dir / "ROC_skipped.txt"
            skip_path.write_text(str(exc), encoding="utf-8")
            text_paths.append(str(skip_path))

        mapping_path = out_dir / "label_mapping.txt"
        mapping_path.write_text(
            "Label mapping:\n" + "\n".join(f"{code}: {cls}" for code, cls in enumerate(le.classes_)),
            encoding="utf-8",
        )
        text_paths.append(str(mapping_path))

        summary_lines = [
            f"samples: {X_df.shape[0]}",
            f"raw_feature_number: {X_df.shape[1]}",
            f"selected_feature_number: {X_sel.shape[1]}",
            f"best_params: {grid.best_params_}",
            f"best_cv_accuracy: {grid.best_score_}",
            f"mean_cv_accuracy: {np.mean(cv_scores)}",
            f"std_cv_accuracy: {np.std(cv_scores)}",
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
                "selected_feature_number": int(X_sel.shape[1]),
                "best_params": grid.best_params_,
                "best_cv_accuracy": float(grid.best_score_),
                "mean_cv_accuracy": float(np.mean(cv_scores)),
                "std_cv_accuracy": float(np.std(cv_scores)),
            },
        }

    @staticmethod
    def _train_rf_cv(X_selected: np.ndarray, y: np.ndarray, cv_splits: int):
        min_count = int(pd.Series(y).value_counts().min())
        n_splits = min(int(cv_splits or 3), min_count)
        if n_splits < 2:
            raise ValueError("min class count < 2")
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
        param_grid = {
            "n_estimators": [50, 100, 200],
            "max_depth": [None, 5, 10, 20],
            "min_samples_split": [2, 5, 10],
        }
        grid = GridSearchCV(
            RandomForestClassifier(random_state=RANDOM_STATE),
            param_grid,
            cv=cv,
            scoring="accuracy",
        )
        grid.fit(X_selected, y)
        best_rf = grid.best_estimator_
        cv_scores = cross_val_score(best_rf, X_selected, y, cv=cv, scoring="accuracy")
        return grid, best_rf, cv_scores, min_count

    @staticmethod
    def _plot_cv_accuracy(cv_scores, out_dir: Path, png_paths: List[str], pdf_paths: List[str]) -> None:
        fig, ax = plt.subplots(figsize=(6.4, 4.2))
        folds = np.arange(1, len(cv_scores) + 1)
        ax.bar(folds, cv_scores, color=PALETTE["blue"], edgecolor="white", linewidth=0.7)
        mean_score = np.mean(cv_scores)
        ax.plot(folds, [mean_score] * len(cv_scores), linestyle="--", color=PALETTE["red"],
                label=f"Mean = {mean_score:.4f}", linewidth=1.8)
        ax.set_xlabel("Fold")
        ax.set_ylabel("Accuracy")
        ax.set_title("Cross-validation Accuracy per Fold")
        ax.set_xticks(folds)
        soften_axes(ax)
        ax.legend()
        fig.tight_layout()
        pdf_path = out_dir / "cross_validation_accuracy.pdf"
        png_path = out_dir / "cross_validation_accuracy.png"
        fig.savefig(pdf_path, dpi=300, facecolor="white")
        fig.savefig(png_path, dpi=300, facecolor="white")
        plt.close(fig)
        pdf_paths.append(str(pdf_path))
        png_paths.append(str(png_path))

    @staticmethod
    def _save_classification_and_confusion(best_rf, X_selected, y, le, out_dir, csv_paths, text_paths, png_paths, pdf_paths):
        y_pred = best_rf.predict(X_selected)
        report = classification_report(y, y_pred, target_names=le.classes_, zero_division=0)
        report_path = out_dir / "classification_report.txt"
        report_path.write_text(report, encoding="utf-8")
        text_paths.append(str(report_path))

        cm = confusion_matrix(y, y_pred)
        cm_path = out_dir / "confusion_matrix.csv"
        pd.DataFrame(cm, index=le.classes_, columns=le.classes_).to_csv(cm_path, encoding="utf-8-sig")
        csv_paths.append(str(cm_path))

        fig, ax = plt.subplots(figsize=(5.6, 4.8))
        im = ax.imshow(cm, interpolation="nearest", cmap=MUTED_BLUE_RED_CMAP)
        ax.set_title("Confusion Matrix")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        tick_marks = np.arange(len(le.classes_))
        ax.set_xticks(tick_marks, le.classes_, rotation=45, ha="right")
        ax.set_yticks(tick_marks, le.classes_)
        ax.set_xlabel("Predicted Label")
        ax.set_ylabel("True Label")
        thresh = cm.max() / 2.0 if cm.size else 0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                ax.text(j, i, format(cm[i, j], "d"), horizontalalignment="center",
                        color="white" if cm[i, j] > thresh else PALETTE["neutral_dark"])
        fig.tight_layout()
        pdf_path = out_dir / "confusion_matrix.pdf"
        png_path = out_dir / "confusion_matrix.png"
        fig.savefig(pdf_path, dpi=300, facecolor="white")
        fig.savefig(png_path, dpi=300, facecolor="white")
        plt.close(fig)
        pdf_paths.append(str(pdf_path))
        png_paths.append(str(png_path))

    @staticmethod
    def _save_feature_importance(X_df, y, out_dir, custom_threshold, csv_paths, png_paths, pdf_paths):
        valid_cols = X_df.columns[X_df.notna().any()].tolist()
        if not valid_cols:
            return
        X_original = SimpleImputer(strategy="mean").fit_transform(X_df[valid_cols].values)
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
        ax.set_xlabel("Feature")
        ax.set_ylabel("Importance")
        ax.set_title(f"Top {top_n} Feature Importances")
        soften_axes(ax)
        fig.tight_layout()
        pdf_path = out_dir / "top20_feature_importances.pdf"
        png_path = out_dir / "top20_feature_importances.png"
        fig.savefig(pdf_path, dpi=300, facecolor="white")
        fig.savefig(png_path, dpi=300, facecolor="white")
        plt.close(fig)
        pdf_paths.append(str(pdf_path))
        png_paths.append(str(png_path))

    @staticmethod
    def _save_roc_curve(X_selected, y, le, grid, min_count, roc_cv_splits, out_dir, csv_paths, text_paths, png_paths, pdf_paths):
        classes = np.unique(y)
        n_classes = len(classes)
        n_splits = min(int(roc_cv_splits or 7), int(min_count))
        if n_splits < 2:
            return
        cv = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
        y_test_all, y_score_all = [], []
        for train_idx, test_idx in cv.split(X_selected, y):
            clf = RandomForestClassifier(**grid.best_params_, random_state=RANDOM_STATE)
            clf.fit(X_selected[train_idx], y[train_idx])
            proba = clf.predict_proba(X_selected[test_idx])
            proba_aligned = np.zeros((len(test_idx), n_classes))
            for i, cls in enumerate(classes):
                if cls in clf.classes_:
                    cls_col = np.where(clf.classes_ == cls)[0][0]
                    proba_aligned[:, i] = proba[:, cls_col]
            y_test_all.append(y[test_idx])
            y_score_all.append(proba_aligned)
        y_test_all = np.concatenate(y_test_all)
        y_score_all = np.vstack(y_score_all)

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
                auc_lines.append(f"{le.classes_[cls]} vs Rest AUC = {roc_auc:.6f}")
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
            auc_text += f"Macro-average AUC = {roc_auc_score(y_bin, y_score_all, average='macro', multi_class='ovr'):.6f}\n"
            auc_text += f"Micro-average AUC = {roc_auc_score(y_bin, y_score_all, average='micro', multi_class='ovr'):.6f}\n"

        csv_paths.append(str(out_dir / "ROC_curve_points.csv"))
        ax.plot([0, 1], [0, 1], linestyle="--", color=PALETTE["neutral_mid"], lw=0.9)
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_title("Cross-validated ROC Curve" if n_classes == 2 else "Cross-validated Multiclass ROC Curve")
        soften_axes(ax, grid_axis="both")
        ax.legend(loc="lower right", fontsize=9)
        fig.tight_layout()
        pdf_path = out_dir / "ROC.pdf"
        png_path = out_dir / "ROC_AUC.png"
        fig.savefig(pdf_path, dpi=300, facecolor="white")
        fig.savefig(png_path, dpi=300, facecolor="white")
        plt.close(fig)
        pdf_paths.append(str(pdf_path))
        png_paths.append(str(png_path))
        auc_path = out_dir / "ROC_AUC.txt"
        auc_path.write_text(auc_text, encoding="utf-8")
        text_paths.append(str(auc_path))

    @staticmethod
    def _allocate_job_id(name: str) -> str:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        return f"{_safe_name(name)}_{ts}"
