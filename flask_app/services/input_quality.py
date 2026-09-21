"""Read selected input content and report sample alignment without changing data."""
from collections import Counter
from pathlib import Path

from flask_app.services.path_access_service import PathAccessService

LABELS = {"pep": "克隆序列表", "profile": "样本指标表", "transcriptome": "转录组数据", "deconvolution": "免疫浸润结果"}
DECONVOLUTION_GROUP_COLUMNS = {"group", "category", "分组"}
DECONVOLUTION_QUALITY_COLUMNS = {"p-value", "p.value", "p_value", "correlation", "rmse", "absolute score (sig.score)"}
SAMPLE_COLUMNS = {"sample", "sample_id", "sample_name", "样本", "样本编号", "mixture"}
GENE_COLUMNS = {"gene", "gene_id", "gene_name", "geneid", "symbol", "ensembl", "基因", "基因编号"}


def _inspect_input_quality(pep_paths, profile_path, transcriptome_path, deconvolution_path):
    from flask_app.routes.api_script_hub._common import _robust_read_csv, _iter_candidate_pep_files, _infer_wide_chain_from_filename, _chain_from_parent_dirs, _sample_name_from_pep_file
    inputs, warnings, errors, sample_sets = [], [], [], {}
    pep_files = _iter_candidate_pep_files(pep_paths)
    if pep_paths:
        pairs = []
        for path in pep_files:
            chain = _infer_wide_chain_from_filename(path.name) or _chain_from_parent_dirs(path)
            if chain: pairs.append((_sample_name_from_pep_file(path, chain), chain))
        sample_sets["pep"] = {sample for sample, chain in pairs}
        repeated = [f"{sample} / {chain}" for (sample, chain), count in Counter(pairs).items() if count > 1]
        inputs.append({"kind": "pep", "label": LABELS['pep'], "sample_count": len(sample_sets['pep']), "sample_column": "文件名", "status": "checked" if pairs else "needs_mapping", "duplicate_samples": repeated[:50], "missing_sample_count": 0, "missing_fields": {}})
        if repeated: warnings.append(f"克隆序列表有 {len(repeated)} 组重复的样本与链组合，请确认文件是否重复上传。")
    for kind, value in (("profile", profile_path), ("transcriptome", transcriptome_path), ("deconvolution", deconvolution_path)):
        if not value: continue
        report = {"kind": kind, "label": LABELS[kind], "sample_count": 0, "sample_column": "", "status": "checked", "duplicate_samples": [], "missing_sample_count": 0, "missing_fields": {}}
        inputs.append(report)
        try:
            path = PathAccessService.validate_read_path(str(value))
            options = {"dtype": str, "keep_default_na": False}
            if path.suffix.lower() == ".tsv": options["sep"] = "\t"
            # Expression matrices carry samples in columns; only the header is needed here.
            df = _robust_read_csv(path, **options, **({"nrows": 1, "header": None} if kind == "transcriptome" else {}))
            columns = ([] if df.empty else df.iloc[0].tolist()) if kind == "transcriptome" else list(df.columns)
            report.update(columns=[str(column) for column in columns], row_count=len(df))
            if not columns or (kind != "transcriptome" and df.empty): raise ValueError("空表")
            if kind == "transcriptome":
                if str(columns[0]).strip().casefold() not in GENE_COLUMNS:
                    report['status'] = 'needs_mapping'
                    warnings.append("转录组数据的基因列尚未识别，需要确认矩阵方向及基因列后核对样本。")
                    continue
                samples = [str(column).strip() for column in columns[1:]]
                report['sample_column'] = '列名（首列为基因）'
            else:
                matches = [column for column in columns if str(column).strip().casefold() in SAMPLE_COLUMNS]
                if len(matches) != 1:
                    report['status'] = 'needs_mapping'
                    warnings.append(f"{LABELS[kind]}需要确认唯一的样本编号列。")
                    continue
                column = matches[0]
                samples = [str(value).strip() for value in df[column]]
                report['sample_column'] = str(column)
                report['missing_fields'] = {str(field): int(df[field].astype(str).str.strip().eq('').sum()) for field in columns if field != column and df[field].astype(str).str.strip().eq('').any()}
                if report['missing_fields']:
                    warnings.append(f"{LABELS[kind]}的部分字段有空值，选择分组和指标时请核对。")
            if kind in {'transcriptome', 'deconvolution'}:
                excluded_columns = []
                if kind == 'deconvolution':
                    excluded_columns = [str(field) for field in columns if str(field).strip().casefold() in DECONVOLUTION_GROUP_COLUMNS]
                    quality_columns = [str(field) for field in columns if str(field).strip().casefold() in DECONVOLUTION_QUALITY_COLUMNS]
                    cell_columns = [str(field) for field in columns if field != report['sample_column'] and str(field) not in excluded_columns + quality_columns]
                    report.update(cell_columns=cell_columns, group_columns=excluded_columns, quality_columns=quality_columns)
                    if not cell_columns:
                        report['status'] = 'invalid'
                        errors.append("免疫浸润结果未包含细胞数值列；分组和质量指标不能作为细胞结果。")
                    if excluded_columns:
                        warnings.append("免疫浸润结果的分组列按文字保留，不参与细胞数值检查：" + "、".join(excluded_columns) + "。")
                    if quality_columns:
                        warnings.append("免疫浸润结果中的质量指标单独识别，不作为细胞列：" + "、".join(quality_columns) + "。")
                numeric = inspect_numeric_content(path, report['sample_column'] if kind == 'deconvolution' else None, excluded_columns=excluded_columns)
                report['numeric_content'] = numeric
                if numeric['invalid_count'] or not numeric['row_count'] or not numeric['column_count']:
                    report['status'] = 'invalid'
                    locations = '、'.join(numeric['examples'])
                    errors.append(f"{LABELS[kind]}数值区域有 {numeric['invalid_count']} 个空值、非数值或无穷值。" +
                                  (f"位置：{locations}。" if locations else "") +
                                  ("数值区域不能为空。" if not numeric['row_count'] or not numeric['column_count'] else ""))
            missing = samples.count('')
            duplicates = sorted(sample for sample, count in Counter(samples).items() if sample and count > 1)
            report.update(sample_count=len(set(samples) - {''}), duplicate_samples=duplicates[:50], duplicate_count=len(duplicates), missing_sample_count=missing)
            sample_sets[kind] = set(samples) - {''}
            report['samples'] = sorted(sample_sets[kind])
            if missing or duplicates:
                report['status'] = 'invalid'
                errors.append(f"{LABELS[kind]}存在 {missing} 个空样本编号、{len(duplicates)} 个重复样本编号，请修正后重新检查。")
        except (OSError, ValueError, KeyError) as error:
            report['status'] = 'invalid'
            errors.append(f"{LABELS[kind]}内容无法读取，请检查文件格式。")
    reference = next((kind for kind in ('profile', 'pep', 'transcriptome', 'deconvolution') if sample_sets.get(kind)), '')
    alignments = []
    if reference:
        baseline = sample_sets[reference]
        for kind, samples in sample_sets.items():
            if kind == reference: continue
            missing, extra = sorted(baseline - samples), sorted(samples - baseline)
            alignments.append({"kind": kind, "label": LABELS[kind], "matched_count": len(samples & baseline), "missing_count": len(missing), "extra_count": len(extra), "missing_samples": missing[:50], "extra_samples": extra[:50]})
            if missing or extra: warnings.append(f"{LABELS[kind]}与{LABELS[reference]}相比，缺少 {len(missing)} 个样本、多出 {len(extra)} 个样本，请确认联合分析的样本对应关系。")
    return {"inputs": inputs, "reference_kind": reference, "reference_label": LABELS.get(reference, ''), "alignments": alignments, "warnings": warnings, "errors": errors}


def validate_analysis_inputs(input_assets):
    """Validate only original tables consumed by this analysis, never derived outputs."""
    from flask_app.exceptions import ValidationError
    aliases = {'datapoint': 'profile', 'expression': 'transcriptome', 'cibersort': 'deconvolution'}
    selected = {"pep": [], "profile": "", "transcriptome": "", "deconvolution": ""}
    for asset in input_assets or []:
        kind = aliases.get(asset.get('asset_type'), asset.get('asset_type'))
        path = asset.get('path')
        if not path or kind not in {'pep', 'profile', 'transcriptome', 'deconvolution'}:
            continue
        if kind == "pep": selected[kind].append(path)
        else: selected[kind] = path
        arguments = {'profile': '', 'transcriptome': '', 'deconvolution': ''}
        if kind != "pep": arguments[kind] = path
        quality = inspect_input_quality([path] if kind == "pep" else [], arguments['profile'], arguments['transcriptome'], arguments['deconvolution'])
        if quality['errors']:
            raise ValidationError(message='输入数据检查未通过：' + '；'.join(quality['errors']),
                                  details={'input_quality': quality})
    quality = inspect_input_quality(selected['pep'], selected['profile'], selected['transcriptome'], selected['deconvolution'])
    if any(item['matched_count'] == 0 and item['missing_count'] and item['extra_count'] for item in quality['alignments']):
        raise ValidationError(message='联合输入之间没有匹配的样本，请核对样本编号或列映射。', details={'input_quality': quality})
    return quality


def inspect_numeric_content(path, sample_column=None, excluded_columns=()):
    """Scan numeric cells without materializing a complete expression matrix."""
    import csv
    import math
    from flask_app.routes.api_script_hub._common import _CSV_ENCODINGS, _robust_read_csv

    def scan(rows):
        header = next(rows, ())
        indexes = [index for index, column in enumerate(header)
                   if (index != 0 if sample_column is None else str(column).strip() != sample_column.strip())
                   and str(column) not in excluded_columns]
        result = {'row_count': 0, 'column_count': len(indexes), 'invalid_count': 0, 'examples': []}
        for row_number, row in enumerate(rows, start=2):
            if not row: continue
            result['row_count'] += 1
            for index in indexes:
                value = row[index] if index < len(row) else None
                try:
                    valid = value is not None and str(value).strip() != '' and math.isfinite(float(value))
                except (ValueError, TypeError, OverflowError):
                    valid = False
                if not valid:
                    result['invalid_count'] += 1
                    if len(result['examples']) < 5:
                        result['examples'].append(f"第 {row_number} 行 / {header[index]}")
        return result

    suffix = path.suffix.lower()
    if suffix in {'.xlsx', '.xlsm'}:
        from openpyxl import load_workbook
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            return scan(iter(workbook.worksheets[0].values))
        finally:
            workbook.close()
    if suffix == '.xls':
        frame = _robust_read_csv(path, header=None, dtype=str, keep_default_na=False)
        return scan(iter(frame.itertuples(index=False, name=None)))
    for encoding in list(_CSV_ENCODINGS) + ['latin-1']:
        try:
            with path.open(encoding=encoding, newline='') as source:
                return scan(iter(csv.reader(source, delimiter='\t' if suffix == '.tsv' else ',', strict=True)))
        except UnicodeError:
            continue
        except csv.Error as error:
            raise ValueError('表格结构无法读取') from error
    raise ValueError('表格编码无法读取')


def inspect_pep_content(path):
    import numpy as np
    import pandas as pd
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    path = PathAccessService.validate_read_path(path)
    result = _inspect_input_quality([str(path)], "", "", "")
    report = result["inputs"][0]
    try:
        frame = _robust_read_csv(path, dtype=str, keep_default_na=False, **({"sep": "\t"} if path.suffix.lower() == ".tsv" else {}))
        required = {"CDR3(pep)", "V", "J", "copy"}
        missing = sorted(required - set(frame.columns))
        if missing:
            raise ValueError("缺少字段：" + "、".join(missing))
        if frame.empty: raise ValueError("数据表为空")
        counts = pd.to_numeric(frame["copy"], errors="coerce")
        bad = (~np.isfinite(counts) | (counts < 0)).sum()
        blanks = frame[list(required - {"copy"})].apply(lambda column: column.str.strip().eq("")).sum().sum()
        if bad or blanks: raise ValueError(f"存在 {int(bad)} 个无效拷贝数和 {int(blanks)} 个空必需字段")
        report["row_count"] = len(frame)
        report["columns"] = list(frame.columns)
    except (ValueError, OSError, KeyError) as error:
        report["status"] = "invalid"
        result["errors"].append(f"克隆序列表 {path.name}：{error}")
    return result


def inspect_input_quality(pep_paths, profile_path, transcriptome_path, deconvolution_path):
    from flask_app.services.input_validation_cache import cached_validation
    from flask_app.routes.api_script_hub._common import _iter_candidate_pep_files
    result = _inspect_input_quality(pep_paths, "", "", "")
    for path in _iter_candidate_pep_files(pep_paths):
        checked = cached_validation(path, "pep", lambda path=path: inspect_pep_content(path))
        result["errors"].extend(checked["errors"])
    if result["errors"] and result["inputs"]: result["inputs"][0]["status"] = "invalid"
    samples = {}
    for kind, value in (("profile", profile_path), ("transcriptome", transcriptome_path), ("deconvolution", deconvolution_path)):
        if not value: continue
        args = {"profile": "", "transcriptome": "", "deconvolution": ""}
        args[kind] = value
        checked = cached_validation(value, kind, lambda: _inspect_input_quality([], args["profile"], args["transcriptome"], args["deconvolution"]))
        result["inputs"].extend(checked["inputs"])
        result["errors"].extend(checked["errors"])
        result["warnings"].extend(checked["warnings"])
        if checked["inputs"]: samples[kind] = set(checked["inputs"][0].get("samples", []))
    if pep_paths:
        from flask_app.routes.api_script_hub._common import _infer_wide_chain_from_filename, _chain_from_parent_dirs, _sample_name_from_pep_file
        samples["pep"] = {_sample_name_from_pep_file(path, chain) for path in _iter_candidate_pep_files(pep_paths) if (chain := _infer_wide_chain_from_filename(path.name) or _chain_from_parent_dirs(path))}
    reference = next((kind for kind in ("profile", "pep", "transcriptome", "deconvolution") if samples.get(kind)), "")
    result.update(reference_kind=reference, reference_label=LABELS.get(reference, ""))
    for kind, values in samples.items():
        if kind == reference or not reference: continue
        baseline = samples[reference]
        missing, extra = sorted(baseline - values), sorted(values - baseline)
        result["alignments"].append(dict(kind=kind, label=LABELS[kind], matched_count=len(baseline & values), missing_count=len(missing), extra_count=len(extra), missing_samples=missing[:50], extra_samples=extra[:50]))
        if missing or extra: result["warnings"].append(f"{LABELS[kind]}与{LABELS[reference]}样本不完全对应，请确认联合分析范围。")
    return result
