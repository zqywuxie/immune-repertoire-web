import os
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
USAGE_DIR = "../Pep_260416/usage_cate"  # 仅用于遍历交叉分组结构
OUTPUT_DIR = "ML_profile_results"

SAMPLE_COL = "Sample"
LABEL_COL = "group_type"

# 特征列区间（将 DataFrame 中位于这两个列名之间的列作为特征）
PARAM_BEGIN = "TRA_percent_reads_all"
PARAM_OVER = "TRB_Largest_clone_percent"

CUSTOM_THRESHOLD = 0.003
RANDOM_STATE = 42
CV_N_SPLITS = 3
ROC_CV_N_SPLITS = 7

# 交叉分组配置
CROSS_GROUP_COLS = ["group_type", "timepoint"]

GROUP_ORDER = {
    "group_type": ["control", "experiment"],
    "timepoint": ["before", "after"],
}
APPEND_UNLISTED_GROUPS = False

plt.rcParams["font.family"] = "Arial"
plt.rcParams["font.size"] = 20


# ============================================================
# Helpers
# ============================================================
def save_text(path, text):
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


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
def read_profile(profile_path):
    df = pd.read_csv(profile_path, low_memory=False)

    if SAMPLE_COL not in df.columns:
        raise ValueError(f"Missing {SAMPLE_COL} column")
    df[SAMPLE_COL] = df[SAMPLE_COL].astype(str)

    return df


# ============================================================
# Prepare X, y — 用 PARAM_BEGIN ~ PARAM_OVER 区间定义特征列
# ============================================================
def prepare_xy_from_profile(df, label_col, param_begin, param_over):
    le = LabelEncoder()
    y = le.fit_transform(df[label_col].astype(str).values)

    # 取 DataFrame 列区间，左闭右闭
    cols = df.columns.tolist()
    if param_begin not in cols or param_over not in cols:
        raise ValueError(
            f"param_begin '{param_begin}' or param_over '{param_over}' not found in columns"
        )
    i_begin = cols.index(param_begin)
    i_over = cols.index(param_over)
    if i_begin > i_over:
        i_begin, i_over = i_over, i_begin
    feature_cols = cols[i_begin:i_over + 1]

    X_df = df[feature_cols].copy()
    X_df = X_df.apply(pd.to_numeric, errors="coerce")
    # 删除全部为 NaN 的特征列
    before = X_df.shape[1]
    X_df = X_df.dropna(axis=1, how="all")
    after = X_df.shape[1]
    if after < before:
        print(f"  dropped all-NaN feature columns: {before - after}")

    return X_df, y, le


# ============================================================
# Preprocess
# ============================================================
def preprocess_X(X_df):
    X = SimpleImputer(strategy="mean").fit_transform(X_df.values)
    X = StandardScaler().fit_transform(X)
    return X


# ============================================================
# Feature selection
# ============================================================
def select_features(X, y, X_df):
    rf = RandomForestClassifier(n_estimators=100, random_state=RANDOM_STATE)
    rf.fit(X, y)
    selector = SelectFromModel(rf, threshold=CUSTOM_THRESHOLD, prefit=True)
    X_selected = selector.transform(X)
    selected_names = X_df.columns[selector.get_support()].tolist()
    return X_selected, selected_names


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
# Run one cross-group slice
# ============================================================
def run_slice(profile_df, filter_col, filter_val, label_col, out_dir):
    # 过滤样本
    sub_df = profile_df[profile_df[filter_col].astype(str) == filter_val].copy()
    print(f"\n  Filter: {filter_col}={filter_val}, profile samples: {len(sub_df)}")

    if len(sub_df) < 3:
        print("  Skip, too few samples")
        return

    # GROUP_ORDER 过滤类别
    keep_cates = get_ordered_categories(
        sub_df[label_col],
        group_order=GROUP_ORDER.get(label_col, None),
        append_unlisted=APPEND_UNLISTED_GROUPS,
    )
    sub_df = sub_df[sub_df[label_col].astype(str).isin(keep_cates)].copy()
    print(f"  Label: {label_col}, groups: {keep_cates}")
    print(sub_df[label_col].value_counts())

    if sub_df[label_col].nunique() < 2:
        print("  Skip, less than 2 groups")
        return

    os.makedirs(out_dir, exist_ok=True)

    X_df, y, le = prepare_xy_from_profile(sub_df, label_col, PARAM_BEGIN, PARAM_OVER)
    print(f"  Raw features: {X_df.shape[1]}")
    if X_df.shape[1] == 0:
        print("  Skip, no features")
        return

    mapping = [f"Label mapping:"]
    for code, cls in enumerate(le.classes_):
        mapping.append(f"  {code}: {cls}")
    save_text(os.path.join(out_dir, "label_mapping.txt"), "\n".join(mapping))

    X = preprocess_X(X_df)
    X_sel, feat_names = select_features(X, y, X_df)
    print(f"  Selected features: {X_sel.shape[1]}")
    if X_sel.shape[1] == 0:
        print("  Skip, no selected features")
        return

    pd.DataFrame({"feature": feat_names}).to_csv(
        os.path.join(out_dir, "selected_features.csv"), index=False
    )

    grid, best_rf, cv_scores, min_count = train_rf_cv(X_sel, y)
    print(f"  Best params: {grid.best_params_}")
    print(f"  Mean CV accuracy: {np.mean(cv_scores):.4f} ± {np.std(cv_scores):.4f}")

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
                f"input: {INPUT_FILE}",
                f"filter: {filter_col}={filter_val}",
                f"label_col: {label_col}",
                f"samples: {len(sub_df)}",
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
    profile_df = read_profile(INPUT_FILE)
    print(f"Profile total samples: {len(profile_df)}")

    # 构建 filter_col → label_col 映射
    category_col_map = {}
    for col in CROSS_GROUP_COLS:
        other = [c for c in CROSS_GROUP_COLS if c != col][0]
        category_col_map[col] = other

    # 遍历 usage_cate 子目录推断交叉分组结构
    if not os.path.isdir(USAGE_DIR):
        print(f"[错误] USAGE_DIR 不存在: {USAGE_DIR}")
    else:
        for filter_val_dir in sorted(os.listdir(USAGE_DIR)):
            filter_val_path = os.path.join(USAGE_DIR, filter_val_dir)
            if not os.path.isdir(filter_val_path):
                continue

            # 从目录名解析 filter_col 和 filter_val
            if "=" not in filter_val_dir:
                continue
            filter_col, filter_val = filter_val_dir.split("=", 1)
            actual_label_col = category_col_map.get(filter_col, LABEL_COL)

            out_dir = os.path.join(OUTPUT_DIR, filter_val_dir)
            print(f"\n{'=' * 60}")
            print(f"Processing: {filter_val_dir}  (label: {actual_label_col})")

            try:
                run_slice(profile_df, filter_col, filter_val, actual_label_col, out_dir)
            except Exception as e:
                print(f"  Error: {e}")

    print("\nAll done.")
