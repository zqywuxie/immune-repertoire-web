"""Input contracts for the sample-level GO-BP and deconvolution analysis."""
from pathlib import Path

import numpy as np
import pandas as pd

from flask_app.exceptions import ValidationError
from flask_app.services.input_quality import inspect_input_quality


def _read_expression_header(expression_path):
    from flask_app.routes.api_script_hub._common import _robust_read_csv

    path = Path(expression_path)
    options = {"dtype": str, "keep_default_na": False, "nrows": 0}
    if path.suffix.lower() == ".tsv":
        options["sep"] = "\t"
    table = _robust_read_csv(path, **options)
    normalized = [str(column).strip() for column in table.columns]
    if len(normalized) != len(set(normalized)):
        raise ValidationError(message="转录组矩阵的列名在去除首尾空格后重复，请先修正输入。")
    table.columns = normalized
    columns = [str(column).strip() for column in table.columns]
    if len(columns) < 2:
        raise ValidationError(message="转录组矩阵至少需要一列基因编号和一个样本列。")
    return columns[0], columns[1:]


def inspect_sample_pathway(
    profile_path,
    deconvolution_path,
    expression_path,
    group_field="",
    cell_columns=None,
    comparison=None,
    **scope,
):
    from flask_app.services.infiltration_service import inspect_inputs

    quality = inspect_input_quality([], profile_path, expression_path, deconvolution_path)
    if quality["errors"]:
        raise ValidationError(message="；".join(quality["errors"]))
    expression_quality = next(
        (item for item in quality["inputs"] if item["kind"] == "transcriptome"), None
    )
    if not expression_quality or expression_quality["status"] != "checked":
        raise ValidationError(message="转录组矩阵的基因列或样本编号尚未确认，请先修正输入表。")

    gene_column, expression_samples = _read_expression_header(expression_path)
    if len(expression_samples) != len(set(expression_samples)):
        raise ValidationError(message="转录组矩阵存在重复样本列名，请先修正后再运行。")
    if any(not sample for sample in expression_samples):
        raise ValidationError(message="转录组矩阵存在空样本列名，请先修正后再运行。")

    inspected = inspect_inputs(profile_path, deconvolution_path, group_field, cell_columns, **scope)
    if not group_field:
        summary = inspected
        summary.update(
            expression_gene_column=gene_column,
            expression_sample_count=len(expression_samples),
            expression_match_count=None,
            comparison_groups=[],
        )
        return summary

    summary, deconvolution, metadata = inspected
    expression_sample_set = set(expression_samples)
    matched_samples = [
        sample for sample in deconvolution["sample"].astype(str)
        if sample in expression_sample_set
    ]
    if not matched_samples:
        raise ValidationError(message="转录组与免疫浸润结果没有完全一致的样本编号。")
    groups_by_sample = metadata.set_index("sample")["group"].astype(str)
    matched_groups = groups_by_sample.reindex(matched_samples)
    matched_counts = matched_groups.value_counts(sort=False).to_dict()
    comparison_groups = [
        str(group) for group, count in matched_counts.items() if int(count) >= 2
    ]
    summary.update(
        expression_gene_column=gene_column,
        expression_sample_count=len(expression_samples),
        expression_match_count=len(matched_samples),
        profile_deconvolution_expression_match_count=len(matched_samples),
        comparison_groups=comparison_groups,
        samples_by_value={group: [sample for sample in matched_samples if groups_by_sample.get(sample) == group] for group in matched_counts},
        selected_infiltration_samples=matched_samples,
        group_counts={str(group): int(count) for group, count in matched_counts.items()},
        unused_expression_sample_count=len(set(expression_samples) - set(matched_samples)),
        unmatched_deconvolution_sample_count=len(set(deconvolution["sample"]) - expression_sample_set),
    )
    if comparison is None:
        return summary
    if (
        not isinstance(comparison, list)
        or len(comparison) != 2
        or any(not isinstance(group, str) or not group for group in comparison)
        or comparison[0] == comparison[1]
    ):
        raise ValidationError(message="请选择两个不同的比较组。")
    if any(group not in comparison_groups for group in comparison):
        raise ValidationError(message="所选比较组不在三类输入共同匹配的样本中。")

    selected_samples = [
        sample for sample in matched_samples
        if groups_by_sample.get(sample) in comparison
    ]
    selected_metadata = metadata[metadata["sample"].isin(selected_samples)].copy()
    selected_metadata["group"] = selected_metadata["group"].astype(str)
    selected_counts = selected_metadata["group"].value_counts(sort=False).to_dict()
    if len(selected_samples) < 10 or any(selected_counts.get(group, 0) < 2 for group in comparison):
        counts = "、".join(f"{group} {selected_counts.get(group, 0)} 个" for group in comparison)
        raise ValidationError(
            message=f"样本级通路相关分析至少需要 10 个共同匹配样本，且每组至少 2 个；当前为 {counts}。"
        )

    summary.update(
        comparison=comparison,
        sample_count=len(selected_samples),
        selected_infiltration_samples=selected_samples,
        group_counts={group: int(selected_counts.get(group, 0)) for group in comparison},
        excluded_group_sample_count=len(matched_samples) - len(selected_samples),
    )
    excluded = len(deconvolution) - len(selected_samples)
    summary['unused_profile_count'] += excluded
    summary['unused_deconvolution_count'] += excluded
    selected_deconvolution = deconvolution[
        deconvolution["sample"].isin(selected_samples)
    ].copy()
    selected_metadata = selected_metadata[
        selected_metadata["sample"].isin(selected_deconvolution["sample"])
    ].copy()
    return summary, selected_deconvolution, selected_metadata


def write_expression_subset(expression_path, sample_ids, output_path):
    """Write a validated, sample-filtered expression matrix for the R worker."""
    from flask_app.routes.api_script_hub._common import _robust_read_csv

    path = Path(expression_path)
    header_options = {"dtype": str, "keep_default_na": False, "nrows": 0}
    if path.suffix.lower() == ".tsv":
        header_options["sep"] = "\t"
    header = _robust_read_csv(path, **header_options)
    original_columns = list(header.columns)
    normalized = [str(column).strip() for column in original_columns]
    if len(normalized) != len(set(normalized)):
        raise ValidationError(message="转录组矩阵的列名在去除首尾空格后重复，请先修正输入。")
    if len(normalized) < 2:
        raise ValidationError(message="转录组表达矩阵为空或格式不正确。")
    gene_column = normalized[0]
    selected_original_columns = [original_columns[0]]
    for sample in sample_ids:
        if sample not in normalized:
            raise ValidationError(message="转录组矩阵在任务执行时缺少已确认的样本列，请重新核对输入。")
        selected_original_columns.append(original_columns[normalized.index(sample)])
    options = {
        "dtype": str,
        "keep_default_na": False,
        "usecols": selected_original_columns,
    }
    if path.suffix.lower() == ".tsv":
        options["sep"] = "\t"
    table = _robust_read_csv(path, **options)
    table = table[selected_original_columns]
    table.columns = [str(column).strip() for column in table.columns]
    if table.empty:
        raise ValidationError(message="转录组表达矩阵为空或格式不正确。")
    if table[gene_column].astype(str).str.strip().eq("").any():
        raise ValidationError(message="转录组矩阵存在空基因编号，请先修正输入。")

    raw = table[sample_ids].astype(str)
    numeric = raw.apply(pd.to_numeric, errors="coerce")
    missing_tokens = raw.apply(lambda column: column.str.strip().str.casefold().isin({"", "na", "nan"}))
    invalid = numeric.isna() & ~missing_tokens
    if invalid.to_numpy().any():
        raise ValidationError(message="转录组表达矩阵含有非数值表达值，请先修正输入；空值按原始流程记为 0。")
    values = numeric.fillna(0.0).to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ValidationError(message="转录组表达矩阵包含无穷值，不能进行 ssGSEA。")
    if (values < 0).any():
        raise ValidationError(message="ssGSEA 的表达矩阵不能含负值；请确认上传的是未作负值中心化的表达数据。")
    subset = pd.DataFrame({gene_column: table[gene_column].astype(str).str.strip()})
    for index, sample in enumerate(sample_ids):
        # R/data.table may rewrite purely numeric column names (e.g. 001) to V1.
        # Internal positional aliases keep headers syntactically stable; sample IDs
        # remain in the separately written deconvolution/group tables.
        subset[f"sample_{index + 1}"] = values[:, index]
    subset.to_csv(output_path, index=False)
    return int(len(subset))
