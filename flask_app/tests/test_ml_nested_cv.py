import numpy as np
import pandas as pd
from sklearn.model_selection import GridSearchCV as SklearnGridSearchCV
from sklearn.model_selection import StratifiedGroupKFold as SklearnStratifiedGroupKFold
from sklearn.preprocessing import LabelEncoder
import pytest

from flask_app.services import ml_analysis_service as ml_service


def test_ml_rejects_duplicate_sample_ids_instead_of_silently_dropping_rows(tmp_path):
    profile = pd.DataFrame(
        {
            "Sample": ["sample-1", " sample-1 ", "sample-2", "sample-3"],
            "Disease": ["Control", "Case", "Control", "Case"],
            "feature": [1.0, 9.0, 2.0, 8.0],
        }
    )
    profile_path = tmp_path / "profile.csv"
    profile.to_csv(profile_path, index=False)

    with pytest.raises(ValueError, match="样本编号必须唯一.*sample-1"):
        ml_service.MLAnalysisService(output_parent=tmp_path / "results").generate_report(
            profile_path=str(profile_path),
            label_col="Disease",
            param_begin="feature",
            param_over="feature",
        )


def test_ml_rejects_reversed_profile_feature_range_like_reference_pipeline(tmp_path):
    profile = pd.DataFrame(
        {
            "Sample": ["sample-1", "sample-2", "sample-3", "sample-4"],
            "Disease": ["Control", "Control", "Case", "Case"],
            "feature_a": [1.0, 2.0, 8.0, 9.0],
            "feature_b": [2.0, 3.0, 7.0, 8.0],
        }
    )
    profile_path = tmp_path / "profile.csv"
    profile.to_csv(profile_path, index=False)

    with pytest.raises(ValueError, match="特征范围起始列必须位于结束列之前"):
        ml_service.MLAnalysisService(output_parent=tmp_path / "results").generate_report(
            profile_path=str(profile_path),
            label_col="Disease",
            param_begin="feature_b",
            param_over="feature_a",
        )


def test_ml_runs_multiple_selected_models_and_registers_comparison(monkeypatch, tmp_path):
    class SmallGridSearchCV:
        def __init__(self, estimator, param_grid, **kwargs):
            self._inner = SklearnGridSearchCV(
                estimator,
                {name: [values[0]] for name, values in param_grid.items()},
                **kwargs,
            )

        def fit(self, X, y, **fit_params):
            self._inner.fit(X, y, **fit_params)
            self.__dict__.update(self._inner.__dict__)
            return self

        def __getattr__(self, name):
            return getattr(self._inner, name)

    monkeypatch.setattr(ml_service, "GridSearchCV", SmallGridSearchCV)
    labels = np.array(["Control"] * 4 + ["CaseA"] * 4 + ["CaseB"] * 4)
    rng = np.random.default_rng(45)
    label_codes = np.repeat([0.0, 1.0, 2.0], 4)
    profile = pd.DataFrame(
        {
            "Sample": [f"sample-{index:02d}" for index in range(len(labels))],
            "Disease": labels,
            "signal": label_codes + rng.normal(0, 0.1, len(labels)),
            "noise": rng.normal(size=len(labels)),
        }
    )
    profile_path = tmp_path / "profile.csv"
    profile.to_csv(profile_path, index=False)

    report = ml_service.MLAnalysisService(output_parent=tmp_path / "results").generate_report(
        profile_path=str(profile_path),
        label_col="Disease",
        param_begin="signal",
        param_over="noise",
        model_keys=["random_forest", "gaussian_nb", "xgboost"],
        cv_splits=3,
    )

    assert report.metadata["model_keys"] == ["random_forest", "gaussian_nb", "xgboost"]
    assert [item["model_key"] for item in report.metadata["models"]] == ["random_forest", "gaussian_nb", "xgboost"]
    comparison_path = next(path for path in report.csv_paths if path.endswith("model_comparison.csv"))
    comparison = pd.read_csv(comparison_path)
    assert comparison["model_key"].tolist() == ["random_forest", "gaussian_nb", "xgboost"]
    assert comparison[["roc_auc", "average_precision"]].notna().all().all()
    stability = report.metadata["stability_selection"]
    assert stability["enabled"] is True
    assert stability["folds"] == 4
    stable_features = set(stability["selected_features"])
    assert stable_features
    stability_path = next(path for path in report.csv_paths if path.endswith("feature_stability.csv"))
    stability_table = pd.read_csv(stability_path)
    assert {"selection_frequency", "selected_for_final_model", "selection_reason"}.issubset(stability_table.columns)
    assert set(stability_table.loc[stability_table["selected_for_final_model"], "feature"]) == stable_features
    for model_key in report.metadata["model_keys"]:
        predictions_path = report.output_base / "profile_Disease" / "models" / model_key / "out_of_fold_predictions.csv"
        assert len(pd.read_csv(predictions_path)) == len(labels)
        selected_path = report.output_base / "profile_Disease" / "models" / model_key / "selected_features.csv"
        assert set(pd.read_csv(selected_path)["feature"]) == stable_features


def test_xgboost_uses_binary_and_multiclass_objectives():
    binary, _ = ml_service.MLAnalysisService._classifier_grid("xgboost", 12, 3, n_classes=2)
    multiclass, _ = ml_service.MLAnalysisService._classifier_grid("xgboost", 12, 3, n_classes=3)

    assert binary.get_params()["objective"] == "binary:logistic"
    assert multiclass.get_params()["objective"] == "multi:softprob"


def test_stable_feature_selector_respects_modalities_and_group_folds():
    rng = np.random.default_rng(92)
    labels = np.repeat([0, 1], 6)
    groups = np.repeat([f"subject-{index}" for index in range(6)], 2)
    signal = labels + rng.normal(0, 0.05, len(labels))
    X = pd.DataFrame({
        "profile__signal": signal,
        "profile__noise": rng.normal(size=len(labels)),
        "VJ__gene_a": signal + rng.normal(0, 0.05, len(labels)),
        "VJ__gene_b": rng.normal(size=len(labels)),
    })

    table, folds = ml_service.MLAnalysisService._select_stable_features(
        X,
        labels,
        mode="profile_vj",
        groups=groups,
        n_splits=5,
        frequency_threshold=0.6,
        min_features_per_modality=1,
    )

    assert folds == 3  # three independent subjects per class, each with two visits
    assert set(table["modality"]) == {"profile", "vj"}
    assert table["selection_frequency"].between(0, 1).all()
    selected_by_modality = table.loc[table["selected_for_final_model"]].groupby("modality").size()
    assert set(selected_by_modality.index) == {"profile", "vj"}
    assert selected_by_modality.ge(1).all()


def test_ml_validation_keeps_preprocessing_and_feature_selection_inside_folds(monkeypatch, tmp_path):
    fit_sizes = []
    search_scoring = []

    class SmallGridSearchCV:
        def __init__(self, estimator, param_grid, **kwargs):
            # Keep this regression test fast while exercising the real nested-CV
            # split and pipeline fitting behavior.
            self._inner = SklearnGridSearchCV(
                estimator,
                {name: [values[0]] for name, values in param_grid.items()},
                **kwargs,
            )
            search_scoring.append(kwargs.get("scoring"))

        def fit(self, X, y, **fit_params):
            fit_sizes.append(len(X))
            self._inner.fit(X, y, **fit_params)
            self.__dict__.update(self._inner.__dict__)
            return self

        def __getattr__(self, name):
            return getattr(self._inner, name)

    monkeypatch.setattr(ml_service, "GridSearchCV", SmallGridSearchCV)
    rng = np.random.default_rng(21)
    y = np.array([0, 1] * 6)
    X = pd.DataFrame(
        {
            "signal": y * 3 + rng.normal(0, 0.15, len(y)),
            "noise_a": rng.normal(size=len(y)),
            "noise_b": rng.normal(size=len(y)),
        }
    )

    _, final_model, fold_scores, predictions, probabilities = ml_service.MLAnalysisService._train_rf_cv(
        X, y, cv_splits=3, threshold=0.003
    )

    assert fit_sizes[:3] and all(size < len(y) for size in fit_sizes[:3])
    assert fit_sizes[-1] == len(y)  # only the deployable final model sees the full cohort
    assert search_scoring and set(search_scoring) == {"balanced_accuracy"}
    assert len(fold_scores) == 3
    assert all({"balanced_accuracy", "macro_f1"}.issubset(row) for row in fold_scores)
    assert predictions.shape == y.shape
    assert probabilities.shape == (len(y), 2)
    assert np.isfinite(probabilities).all()
    assert final_model.named_steps["selector"].get_support().any()

    output_dir = tmp_path / "ml-results"
    output_dir.mkdir()
    sample_ids = np.array([f"sample-{index:02d}" for index in range(len(y))])
    report_files = ml_service.MLAnalysisService(output_parent=tmp_path)._run_random_forest(
        X_df=X,
        y=y,
        le=LabelEncoder().fit(y),
        sample_ids=sample_ids,
        group_ids=sample_ids,
        out_dir=output_dir,
        custom_threshold=0.003,
        cv_splits=3,
    )
    predictions_path = output_dir / "out_of_fold_predictions.csv"
    predictions = pd.read_csv(predictions_path)
    assert str(predictions_path) in report_files["csv_paths"]
    assert len(predictions) == len(y)
    assert predictions["sample"].is_unique
    assert predictions["group"].tolist() == sample_ids.tolist()
    assert predictions[["proba_0", "proba_1"]].to_numpy().min() >= 0

    subject_labels = np.repeat(["Control", "Control", "Control", "Case", "Case", "Case"], 2)
    grouped_profile = pd.DataFrame(
        {
            "Sample": [f"visit-{index:02d}" for index in range(len(subject_labels))],
            "Subject": np.repeat([f"subject-{index}" for index in range(6)], 2),
            "Disease": subject_labels,
            "signal": (subject_labels == "Case").astype(float) + rng.normal(0, 0.1, len(subject_labels)),
            "noise": rng.normal(size=len(subject_labels)),
        }
    )
    profile_path = tmp_path / "profile.csv"
    grouped_profile.to_csv(profile_path, index=False)
    report = ml_service.MLAnalysisService(output_parent=tmp_path / "reports").generate_report(
        profile_path=str(profile_path),
        label_col="Disease",
        sample_col="Sample",
        group_col="Subject",
        param_begin="signal",
        param_over="noise",
        cv_splits=3,
    )
    assert report.metadata["cv_strategy"] == "stratified_group_k_fold"
    grouped_predictions_path = next(
        path for path in report.csv_paths if path.endswith("out_of_fold_predictions.csv")
    )
    grouped_predictions = pd.read_csv(grouped_predictions_path)
    assert grouped_predictions["sample"].is_unique
    assert grouped_predictions["group"].nunique() == 6


def test_grouped_nested_cv_keeps_subjects_out_of_both_training_and_test_folds(monkeypatch):
    group_splits = []

    class RecordingStratifiedGroupKFold(SklearnStratifiedGroupKFold):
        def split(self, X, y, groups):
            for train_idx, test_idx in super().split(X, y, groups):
                group_splits.append((set(groups[train_idx]), set(groups[test_idx])))
                yield train_idx, test_idx

    monkeypatch.setattr(ml_service, "StratifiedGroupKFold", RecordingStratifiedGroupKFold)
    rng = np.random.default_rng(31)
    groups = np.repeat([f"subject-{index}" for index in range(6)], 2)
    y = np.repeat([0, 0, 0, 1, 1, 1], 2)
    X = pd.DataFrame({"signal": y + rng.normal(0, 0.1, len(y)), "noise": rng.normal(size=len(y))})

    _, _, fold_metrics, predictions, probabilities = ml_service.MLAnalysisService._train_rf_cv(
        X, y, cv_splits=3, threshold=0.003, groups=groups
    )

    assert len(fold_metrics) == 3
    assert predictions.shape == y.shape
    assert probabilities.shape == (len(y), 2)
    assert group_splits
    assert all(not train_groups.intersection(test_groups) for train_groups, test_groups in group_splits)

    conflicting_groups = np.array(["shared"] * len(y))
    with pytest.raises(ValueError):
        ml_service.MLAnalysisService._train_rf_cv(
            X, y, cv_splits=3, threshold=0.003, groups=conflicting_groups
        )
