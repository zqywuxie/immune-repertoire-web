import os
import re
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt

from matplotlib.colors import LinearSegmentedColormap

from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_score
from sklearn.preprocessing import StandardScaler, LabelEncoder, label_binarize
from sklearn.impute import SimpleImputer
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_selection import SelectFromModel
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    roc_curve,
    auc,
    roc_auc_score,
)

# ========== 配置 ==========
INPUT_FILE = "/data/scAnalyis/260416/Data/Datapoint/profile.csv"
USAGE_DIR = "../Pep_260416/usage_cate"
OUTPUT_DIR = "ML_VJ_results"

LABEL_COL = "group_type"
SAMPLE_COL = "Sample"

USAGE_SAMPLE_COL = "sample"
USAGE_LABEL_COL = "Category"

ADD_CHAIN_PREFIX = True
USE_USAGE_FILES_KEYWORDS = None
USE_PROFILE_FEATURES = False
CUSTOM_THRESHOLD = 0.003
RANDOM_STATE = 42
CV_N_SPLITS = 3
ROC_CV_N_SPLITS = 7

# 交叉分组配置
CROSS_GROUP_COLS = ["group_type", "timepoint"]
TIME_LABEL_COL = "timepoint"

# 每组参与分析的类别（空列表 = 使用全部）
GROUP_ORDER = {
    "group_type": ["control", "experiment"],
    "timepoint": ["before", "after"],
}
APPEND_UNLISTED_GROUPS = False

plt.rcParams["font.family"] = "Arial"
plt.rcParams["font.size"] = 20


# ============================================================
# Helper: get usage files from a usage_cate subdirectory
# ============================================================
def collect_usage_files(usage_dir):
    usage_files = []
    for dirname, _, filenames in os.walk(usage_dir):
        for filename in filenames:
            if filename.endswith(".csv") or filename.endswith(".csv.gz"):
                file_path = os.path.join(dirname, filename)
                if USE_USAGE_FILES_KEYWORDS is not None:
                    if not any(k in filename for k in USE_USAGE_FILES_KEYWORDS):
                        continue
                usage_files.append(file_path)
    return sorted(usage_files)


# ============================================================
# Helper: datapoint files
# ============================================================
def get_datapoint_files(input_path):
    if os.path.isfile(input_path):
        if input_path.endswith(".csv"):
            return [input_path]
        raise ValueError(f"INPUT_FILE 是文件，但不是 csv: {input_path}")
    if os.path.isdir(input_path):
        files = sorted(
            os.path.join(input_path, f)
            for f in os.listdir(input_path)
            if f.endswith(".csv")
        )
        if not files:
            raise FileNotFoundError(f"目录下没有 csv 文件: {input_path}")
        return files
    raise FileNotFoundError(f"INPUT_FILE 不存在: {input_path}")


# ============================================================
# Helper: save text
# ============================================================
def save_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ============================================================
# Helper: get ordered categories
# ============================================================
def get_ordered_categories(categories, group_order=None, append_unlisted=True):
    original_cates = categories.dropna().astype(str).unique().tolist()
    if group_order is None or len(group_order) == 0:
        return original_cates
    group_order = [str(x) for x in group_order]
    ordered = [g for g in group_order if g in original_cates]
    if append_unlisted:
        rest = [g for g in original_cates if g not in ordered]
        ordered = ordered + rest
    return ordered


# ============================================================
# Read profile
# ============================================================
def read_profile(profile_path, label_col):
    profile_df = pd.read_csv(profile_path, low_memory=False)
    required = [SAMPLE_COL, label_col]
    missing = [c for c in required if c not in profile_df.columns]
    if missing:
        raise ValueError(f"缺少必要字段: {missing}; file = {profile_path}")

    profile_df = profile_df.dropna(subset=[SAMPLE_COL, label_col])
    profile_df[SAMPLE_COL] = profile_df[SAMPLE_COL].astype(str)
    profile_df[label_col] = profile_df[label_col].astype(str)
    profile_df = profile_df.drop_duplicates(subset=[SAMPLE_COL], keep="first")

    if USE_PROFILE_FEATURES:
        return profile_df.copy()
    return profile_df[[SAMPLE_COL, label_col]].copy()


# ============================================================
# Build feature matrix from usage files
# ============================================================
def get_usage_file_prefix(file_path):
    filename = os.path.basename(file_path)
    if filename.endswith(".csv.gz"):
        return filename[:-7]
    elif filename.endswith(".csv"):
        return filename[:-4]
    return filename


def build_feature_matrix_from_usage(profile_samples, usage_files):
    feature_df = pd.DataFrame({SAMPLE_COL: sorted(profile_samples)})

    for file_path in usage_files:
        prefix = get_usage_file_prefix(file_path)
        print(f"  Processing: {prefix}")

        df_usage = pd.read_csv(file_path, compression="infer", low_memory=False)

        if USAGE_SAMPLE_COL not in df_usage.columns:
            print(f"    Skip, missing sample column")
            continue

        df_usage[USAGE_SAMPLE_COL] = (
            df_usage[USAGE_SAMPLE_COL]
            .astype(str)
            .str.replace(r"\.csv\.gz$", "", regex=True)
            .str.replace(r"\.csv$", "", regex=True)
            .str.rsplit("__", n=1)
            .str[0]
        )

        before_n = df_usage.shape[0]
        df_usage = df_usage[df_usage[USAGE_SAMPLE_COL].isin(profile_samples)].copy()
        print(f"    matched samples: {df_usage.shape[0]}/{before_n}")

        if df_usage.empty:
            continue

        df_usage = df_usage.drop(columns=[USAGE_LABEL_COL], errors="ignore")
        df_usage = df_usage.rename(columns={USAGE_SAMPLE_COL: SAMPLE_COL})

        feature_cols = [c for c in df_usage.columns if c != SAMPLE_COL]
        for col in feature_cols:
            df_usage[col] = pd.to_numeric(df_usage[col], errors="coerce")

        if ADD_CHAIN_PREFIX:
            df_usage = df_usage.rename(
                columns={col: f"{prefix}__{col}" for col in feature_cols}
            )

        df_usage = df_usage.groupby(SAMPLE_COL, as_index=False).first()
        feature_df = feature_df.merge(df_usage, on=SAMPLE_COL, how="left")

    if feature_df.shape[1] <= 1:
        return pd.DataFrame()
    return feature_df


# ============================================================
# Prepare X, y
# ============================================================
def prepare_xy(df, label_col):
    le = LabelEncoder()
    y = le.fit_transform(df[label_col].astype(str).values)
    X_df = df.drop(columns=[SAMPLE_COL, label_col], errors="ignore")
    X_df = X_df.apply(pd.to_numeric, errors="coerce")
    return X_df, y, le


# ============================================================
# Preprocess
# ============================================================
def preprocess_X(X_df):
    return X_df.fillna(0).to_numpy(dtype=float)


# ============================================================
# Feature selection
# ============================================================
def select_features(X, y, X_df):
    rf = RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)
    rf.fit(X, y)
    selector = SelectFromModel(rf, threshold=CUSTOM_THRESHOLD, prefit=True)
    X_selected = selector.transform(X)
    selected_feature_names = X_df.columns[selector.get_support()].tolist()
    return X_selected, selected_feature_names, selector, rf


# ============================================================
# Train RF with CV
# ============================================================
def train_rf_cv(X_selected, y):
    class_counts = pd.Series(y).value_counts()
    min_count = class_counts.min()
    n_splits = min(CV_N_SPLITS, min_count)
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


# ============================================================
# Plot CV accuracy
# ============================================================
def plot_cv_accuracy(cv_scores, out_dir):
    plt.figure(figsize=(8, 5))
    folds = np.arange(1, len(cv_scores) + 1)
    plt.bar(folds, cv_scores, color="#3976B0", edgecolor="black")
    mean_score = np.mean(cv_scores)
    plt.plot(
        folds,
        [mean_score] * len(cv_scores),
        linestyle="--",
        color="#CA8E8C",
        label=f"Mean = {mean_score:.4f}",
        linewidth=4,
    )
    plt.xlabel("Fold")
    plt.ylabel("Accuracy")
    plt.title("Cross-validation Accuracy per Fold")
    plt.xticks(folds)
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "cross_validation_accuracy.pdf"), dpi=300)
    plt.close()


# ============================================================
# Classification report & confusion matrix
# ============================================================
def save_classification_and_confusion(best_rf, X_selected, y, le, out_dir):
    y_pred = best_rf.predict(X_selected)
    report = classification_report(y, y_pred, target_names=le.classes_)
    print(report)
    save_text(os.path.join(out_dir, "classification_report.txt"), report)

    cm = confusion_matrix(y, y_pred)
    pd.DataFrame(cm, index=le.classes_, columns=le.classes_).to_csv(
        os.path.join(out_dir, "confusion_matrix.csv")
    )

    custom_cmap = LinearSegmentedColormap.from_list("custom", ["#3976B0", "#CA8E8C"])
    plt.figure(figsize=(6, 5))
    plt.imshow(cm, interpolation="nearest", cmap=custom_cmap)
    plt.title("Confusion Matrix")
    plt.colorbar()
    tick_marks = np.arange(len(le.classes_))
    plt.xticks(tick_marks, le.classes_, rotation=45, ha="right")
    plt.yticks(tick_marks, le.classes_)
    plt.xlabel("Predicted Label")
    plt.ylabel("True Label")
    thresh = cm.max() / 2.0
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(
                j,
                i,
                format(cm[i, j], "d"),
                horizontalalignment="center",
                color="white" if cm[i, j] > thresh else "black",
            )
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "confusion_matrix.pdf"), dpi=300)
    plt.close()


# ============================================================
# Feature importance
# ============================================================
def save_feature_importance(X_df, y, out_dir):
    # Drop all-NaN columns before imputation to avoid dimension mismatch
    valid_mask = X_df.notna().any()
    valid_cols = X_df.columns[valid_mask].tolist()
    X_clean = X_df[valid_cols]

    if X_clean.shape[1] == 0:
        return

    X_original = SimpleImputer(strategy="mean").fit_transform(X_clean.values)
    X_original = StandardScaler().fit_transform(X_original)

    rf = RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)
    rf.fit(X_original, y)

    selector = SelectFromModel(rf, threshold=CUSTOM_THRESHOLD, prefit=True)
    mask = selector.get_support()

    importances = rf.feature_importances_
    selected_importances = importances[mask]
    selected_names = np.array(valid_cols)[mask]

    if len(selected_importances) == 0:
        return

    pd.DataFrame(
        {"feature": selected_names, "importance": selected_importances}
    ).sort_values("importance", ascending=False).to_csv(
        os.path.join(out_dir, "feature_importance.csv"), index=False
    )

    top_n = min(20, len(selected_importances))
    idx = np.argsort(selected_importances)[::-1][:top_n]

    plt.figure(figsize=(9, 6))
    plt.bar(range(top_n), selected_importances[idx], align="center", color="#3976B0")
    plt.xticks(range(top_n), selected_names[idx], rotation=45, ha="right")
    plt.xlabel("Feature")
    plt.ylabel("Importance")
    plt.title(f"Top {top_n} Feature Importances")
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "top20_feature_importances.pdf"), dpi=300)
    plt.close()


# ============================================================
# ROC curve
# ============================================================
def save_roc_curve(X_selected, y, le, grid, min_count, out_dir):
    classes = np.unique(y)
    n_classes = len(classes)
    n_splits = min(ROC_CV_N_SPLITS, min_count)
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

    plt.figure(figsize=(6.5, 5.5))

    if n_classes == 2:
        pos_label = classes[1]
        pos_col = np.where(classes == pos_label)[0][0]
        pos_name = le.classes_[pos_label]
        fpr, tpr, _ = roc_curve(
            y_test_all, y_score_all[:, pos_col], pos_label=pos_label
        )
        roc_auc = auc(fpr, tpr)
        pd.DataFrame(
            {"fpr": fpr, "tpr": tpr, "class": pos_name, "auc": roc_auc}
        ).to_csv(os.path.join(out_dir, "ROC_curve_points.csv"), index=False)
        plt.plot(
            fpr, tpr, lw=2, color="#3976B0", label=f"{pos_name} AUC = {roc_auc:.4f}"
        )
        auc_text = f"{pos_name} AUC = {roc_auc:.6f}\n"
    else:
        y_bin = label_binarize(y_test_all, classes=classes)
        roc_records, auc_lines = [], []
        for i, cls in enumerate(classes):
            fpr, tpr, _ = roc_curve(y_bin[:, i], y_score_all[:, i])
            roc_auc = auc(fpr, tpr)
            auc_lines.append(f"{le.classes_[cls]} vs Rest AUC = {roc_auc:.6f}")
            roc_records.append(
                pd.DataFrame(
                    {"class": le.classes_[cls], "fpr": fpr, "tpr": tpr, "auc": roc_auc}
                )
            )
            plt.plot(fpr, tpr, lw=2, label=f"{le.classes_[cls]} AUC = {roc_auc:.4f}")
        pd.concat(roc_records, axis=0).to_csv(
            os.path.join(out_dir, "ROC_curve_points.csv"), index=False
        )
        auc_text = "\n".join(auc_lines) + "\n"
        auc_text += f"Macro-average AUC = {roc_auc_score(y_bin, y_score_all, average='macro', multi_class='ovr'):.6f}\n"
        auc_text += f"Micro-average AUC = {roc_auc_score(y_bin, y_score_all, average='micro', multi_class='ovr'):.6f}\n"

    plt.plot([0, 1], [0, 1], "k--", lw=1)
    plt.xlabel("False Positive Rate")
    plt.ylabel("True Positive Rate")
    plt.title(
        "Cross-validated ROC Curve"
        if n_classes == 2
        else "Cross-validated Multiclass ROC Curve"
    )
    plt.legend(loc="lower right", fontsize=16, frameon=True)
    plt.grid(alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(out_dir, "ROC.pdf"), dpi=300)
    plt.savefig(os.path.join(out_dir, "ROC_AUC.png"), dpi=300)
    plt.close()
    save_text(os.path.join(out_dir, "ROC_AUC.txt"), auc_text)


# ============================================================
# Run one datapoint with a specific label column
# ============================================================
def run_one_datapoint(
    profile_path, usage_files, label_col, subdir="", group_order=None
):
    datapoint_name = os.path.basename(profile_path).rsplit(".", 1)[0]
    out_dir = (
        os.path.join(OUTPUT_DIR, subdir, datapoint_name)
        if subdir
        else os.path.join(OUTPUT_DIR, datapoint_name)
    )
    os.makedirs(out_dir, exist_ok=True)

    profile_df = read_profile(profile_path, label_col)
    profile_df[label_col] = profile_df[label_col].astype(str)

    # 按 GROUP_ORDER 过滤类别
    keep_cates = get_ordered_categories(
        profile_df[label_col],
        group_order=group_order,
        append_unlisted=APPEND_UNLISTED_GROUPS,
    )
    profile_df = profile_df[profile_df[label_col].isin(keep_cates)]

    print(
        f"\nProfile samples: {len(profile_df)}, label: {label_col}, groups: {keep_cates}"
    )
    print(profile_df[label_col].value_counts())

    if profile_df[label_col].nunique() < 2:
        print(f"Skip, less than 2 groups in {label_col}")
        return

    profile_samples = set(profile_df[SAMPLE_COL].astype(str).tolist())
    feature_df = build_feature_matrix_from_usage(profile_samples, usage_files)
    if feature_df.empty:
        print("Skip, no matched usage features")
        return

    print(f"Feature matrix: {feature_df.shape}")
    df = profile_df.merge(feature_df, on=SAMPLE_COL, how="inner")
    print(f"Merged: {df.shape}")

    if df.shape[0] < 3 or df[label_col].nunique() < 2:
        print("Skip, insufficient samples or groups after merge")
        return

    df.to_csv(os.path.join(out_dir, "merged_feature_matrix.csv"), index=False)

    X_df, y, le = prepare_xy(df, label_col)
    print(f"Raw features: {X_df.shape[1]}")

    mapping = [f"Label mapping:"]
    for code, cls in enumerate(le.classes_):
        mapping.append(f"{code}: {cls}")
    save_text(os.path.join(out_dir, "label_mapping.txt"), "\n".join(mapping))

    X = preprocess_X(X_df)
    X_sel, feat_names, selector, rf = select_features(X, y, X_df)
    print(f"Selected features: {X_sel.shape[1]}")
    if X_sel.shape[1] == 0:
        print("Skip, no selected features")
        return

    pd.DataFrame({"feature": feat_names}).to_csv(
        os.path.join(out_dir, "selected_features.csv"), index=False
    )

    grid, best_rf, cv_scores, min_count = train_rf_cv(X_sel, y)
    print(f"Best params: {grid.best_params_}")
    print(f"Mean CV accuracy: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}")

    pd.DataFrame(
        {"fold": np.arange(1, len(cv_scores) + 1), "accuracy": cv_scores}
    ).to_csv(os.path.join(out_dir, "cross_validation_scores.csv"), index=False)

    plot_cv_accuracy(cv_scores, out_dir)
    save_classification_and_confusion(best_rf, X_sel, y, le, out_dir)

    try:
        save_feature_importance(X_df, y, out_dir)
    except Exception as e:
        print(f"  [跳过] feature importance: {e}")

    try:
        save_roc_curve(X_sel, y, le, grid, min_count, out_dir)
    except Exception as e:
        print(f"  [跳过] ROC curve: {e}")

    save_text(
        os.path.join(out_dir, "summary.txt"),
        "\n".join(
            [
                f"datapoint: {datapoint_name}",
                f"profile_path: {profile_path}",
                f"usage_dir: {USAGE_DIR}",
                f"label_col: {label_col}",
                f"subdir: {subdir}",
                f"profile_samples: {len(profile_df)}",
                f"merged_samples: {df.shape[0]}",
                f"raw_feature_number: {X_df.shape[1]}",
                f"selected_feature_number: {X_sel.shape[1]}",
                f"best_params: {grid.best_params_}",
                f"best_cv_accuracy: {grid.best_score_}",
                f"mean_cv_accuracy: {np.mean(cv_scores)}",
                f"std_cv_accuracy: {np.std(cv_scores)}",
            ]
        ),
    )


# ============================================================
# Main
# ============================================================
if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    datapoint_files = get_datapoint_files(INPUT_FILE)
    print(f"Datapoint files: {len(datapoint_files)}")

    # 构建 filter_col → actual_label_col 映射
    category_col_map = {}
    for col in CROSS_GROUP_COLS:
        other = [c for c in CROSS_GROUP_COLS if c != col][0]
        category_col_map[col] = other

    # 遍历 usage_cate 子目录
    if not os.path.isdir(USAGE_DIR):
        print(f"[错误] USAGE_DIR 不存在: {USAGE_DIR}")
    else:
        for filter_val_dir in sorted(os.listdir(USAGE_DIR)):
            filter_val_path = os.path.join(USAGE_DIR, filter_val_dir)
            if not os.path.isdir(filter_val_path):
                continue

            usage_parent = os.path.join(filter_val_path, "usage")
            usage_1vj = os.path.join(usage_parent, "1VJusage")
            if not os.path.isdir(usage_1vj):
                continue

            # 推断 label column
            filter_col = filter_val_dir.split("=")[0]
            actual_label_col = category_col_map.get(filter_col, LABEL_COL)

            usage_files = collect_usage_files(usage_1vj)
            print(f"\n{'=' * 80}")
            print(f"Processing: {filter_val_dir}  (label: {actual_label_col})")
            print(f"Usage files: {len(usage_files)}")

            if not usage_files:
                continue

            group_order = GROUP_ORDER.get(actual_label_col, None)

            for profile_path in datapoint_files:
                try:
                    run_one_datapoint(
                        profile_path,
                        usage_files,
                        actual_label_col,
                        subdir=filter_val_dir,
                        group_order=group_order,
                    )
                except Exception as e:
                    print(f"Error: {e}")

    print("\nAll done.")
