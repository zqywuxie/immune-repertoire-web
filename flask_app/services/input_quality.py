"""Read selected input content and report sample alignment without changing data."""
from collections import Counter
from pathlib import Path

from flask_app.services.path_access_service import PathAccessService

LABELS = {"pep": "克隆序列表", "profile": "样本指标表", "transcriptome": "转录组数据", "deconvolution": "免疫浸润结果"}
DECONVOLUTION_GROUP_COLUMNS = {"group", "category", "分组"}
DECONVOLUTION_QUALITY_COLUMNS = {"p-value", "p.value", "p_value", "correlation", "rmse", "absolute score (sig.score)"}
SAMPLE_COLUMNS = {"sample", "sample_id", "sample_name", "样本", "样本编号", "mixture"}
GENE_COLUMNS = {"gene", "gene_id", "gene_name", "gene_symbol", "geneid", "symbol", "ensembl", "基因", "基因编号"}


def _inspect_input_quality(pep_paths, profile_path, transcriptome_path, deconvolution_path, profile_batch_field=None, profile_sample_column=None, pep_field_mapping=None):
    from flask_app.routes.api_script_hub._common import _robust_read_csv, _iter_candidate_pep_files, _infer_wide_chain_from_filename, _chain_from_parent_dirs, _sample_name_from_pep_file
    inputs, warnings, errors, sample_sets = [], [], [], {}
    pep_files = _iter_candidate_pep_files(pep_paths, pep_field_mapping)
    if pep_paths:
        pairs = []
        for path in pep_files:
            chain = _infer_wide_chain_from_filename(path.name) or _chain_from_parent_dirs(path)
            if chain: pairs.append((_sample_name_from_pep_file(path, chain), chain))
        sample_sets["pep"] = {sample for sample, chain in pairs}
        repeated = [f"{sample} / {chain}" for (sample, chain), count in Counter(pairs).items() if count > 1]
        inputs.append({"kind": "pep", "label": LABELS['pep'], "sample_count": len(sample_sets['pep']), "samples": sorted(sample_sets["pep"]), "sample_column": "文件名", "status": "checked" if pairs else "needs_mapping", "duplicate_samples": repeated[:50], "missing_sample_count": 0, "missing_fields": {}})
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
                if kind == 'profile' and profile_sample_column:
                    if profile_sample_column not in columns:
                        report['status'] = 'invalid'
                        errors.append(f"样本指标表不存在所选样本编号列“{profile_sample_column}”。")
                        continue
                    matches = [profile_sample_column]
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
            if kind == 'profile' and profile_batch_field:
                batch_field = str(profile_batch_field).strip()
                if batch_field not in columns or batch_field == report['sample_column']:
                    raise ValueError(f"无效的批次字段：{batch_field}")
                batches = [str(value).strip() for value in df[batch_field]]
                missing_batches = sum(not batch for batch in batches)
                identities = [(sample, batch) for sample, batch in zip(samples, batches) if sample and batch]
                duplicate_identities = [identity for identity, count in Counter(identities).items() if count > 1]
                duplicates = sorted(f"{batch} / {sample}" for sample, batch in duplicate_identities)
                report.update(
                    batch_field=batch_field,
                    batch_count=len(set(batches) - {''}),
                    sample_count=len(set(identities)),
                    duplicate_samples=duplicates[:50],
                    duplicate_count=len(duplicates),
                    missing_sample_count=missing,
                    missing_batch_count=missing_batches,
                )
                if missing_batches:
                    report['status'] = 'invalid'
                    errors.append(f"{LABELS[kind]}存在 {missing_batches} 个空批次值，请修正后重新检查。")
            else:
                report.update(sample_count=len(set(samples) - {''}), duplicate_samples=duplicates[:50], duplicate_count=len(duplicates), missing_sample_count=missing)
            sample_sets[kind] = set(samples) - {''}
            report['samples'] = sorted(sample_sets[kind])
            if kind == 'profile' and duplicates and not profile_batch_field and not missing:
                report['status'] = 'needs_mapping'
                warnings.append("样本指标表存在重复样本编号；如果来自不同批次，请在分析配置中指定批次字段，同一批次内的重复编号仍需修正。")
            if missing or (duplicates and not (kind == 'profile' and not profile_batch_field)):
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


def validate_analysis_inputs(input_assets, config_json=None, module_name=None):
    """Validate only original tables consumed by this analysis, never derived outputs."""
    from flask_app.exceptions import ValidationError
    aliases = {'datapoint': 'profile', 'expression': 'transcriptome', 'cibersort': 'deconvolution'}
    selected = {"pep": [], "profile": "", "transcriptome": "", "deconvolution": ""}
    profile_batch_field = str((config_json or {}).get('batch_field') or '').strip() or None
    profile_sample_column = str((config_json or {}).get('sample_col') or '').strip() or None
    mapping = (config_json or {}).get('field_mapping')
    pep_field_mapping = mapping if isinstance(mapping, dict) and {'cdr3_column', 'copy_column'}.issubset(mapping) else None
    if module_name == 'topclone' and (config_json or {}).get('mode', 'trace') == 'trace':
        # Proportion analysis consumes only these two columns; V/J are not used.
        pep_field_mapping = {'cdr3_column': 'CDR3(pep)', 'copy_column': 'copy'}
    for asset in input_assets or []:
        kind = aliases.get(asset.get('asset_type'), asset.get('asset_type'))
        path = asset.get('path')
        if not path or kind not in {'pep', 'profile', 'transcriptome', 'deconvolution'}:
            continue
        if kind == "pep": selected[kind].append(path)
        else: selected[kind] = path
        arguments = {'profile': '', 'transcriptome': '', 'deconvolution': ''}
        if kind != "pep": arguments[kind] = path
        quality = inspect_input_quality(
            [path] if kind == "pep" else [], arguments['profile'], arguments['transcriptome'], arguments['deconvolution'],
            profile_batch_field if kind == 'profile' else None,
            profile_sample_column if kind == 'profile' else None,
            pep_field_mapping if kind == 'pep' else None,
        )
        if kind == 'pep' and quality.get('inputs') and quality['inputs'][0].get('status') == 'needs_mapping':
            raise ValidationError(message='未识别到可用于本分析的克隆文件，请检查链型、文件名及所需字段。', details={'input_quality': quality, 'asset_type': 'pep'})
        if kind == 'profile' and not profile_batch_field and quality.get('inputs'):
            if quality['inputs'][0].get('duplicate_count'):
                raise ValidationError(
                    message='输入数据检查未通过：样本指标表存在重复样本编号。若样本来自不同批次，请指定批次字段；同批次内重复编号需先修正。',
                    details={'input_quality': quality, 'field': 'batch_field'},
                )
        if quality['errors']:
            raise ValidationError(message='输入数据检查未通过：' + '；'.join(quality['errors']),
                                  details={'input_quality': quality})
        if kind in {"profile", "transcriptome", "deconvolution"} and quality["inputs"]:
            report = quality["inputs"][0]
            if report.get("status") == "needs_mapping":
                raise ValidationError(message="无法确认关键编号列或矩阵方向，请先在工作表与编号列设置中完成映射整理，再重新检查并提交。", details={"input_quality": quality, "field": "input_mapping", "asset_type": kind})
    quality = inspect_input_quality(
        selected['pep'], selected['profile'], selected['transcriptome'], selected['deconvolution'], profile_batch_field, profile_sample_column, pep_field_mapping,
    )
    if any(item['matched_count'] == 0 and item['missing_count'] and item['extra_count'] for item in quality['alignments']):
        raise ValidationError(message='联合输入之间没有匹配的样本，请核对样本编号或列映射。', details={'input_quality': quality})
    return quality


def require_alignment_review(quality, reviewed=False):
    """Require explicit acknowledgement whenever selected inputs do not align."""
    from flask_app.exceptions import ValidationError
    mismatches = [item for item in (quality or {}).get('alignments', []) if item.get('missing_count') or item.get('extra_count')]
    if mismatches and reviewed is not True:
        labels = '、'.join(item.get('label') or item.get('kind') or '输入数据' for item in mismatches)
        raise ValidationError(message=f'{labels}与其他输入的样本编号不完全一致，请返回输入检查页核对差异后再提交。', details={'field': 'sample_alignment_reviewed', 'alignments': mismatches})
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
        import xlrd

        workbook = xlrd.open_workbook(path, on_demand=True)
        try:
            if not workbook.nsheets:
                return scan(iter(()))
            sheet = workbook.sheet_by_index(0)

            def rows():
                for row_index in range(sheet.nrows):
                    values = sheet.row_values(row_index)
                    # Match pandas' previous treatment of Excel date cells: dates
                    # are not accepted as numeric measurements.
                    for column_index, value in enumerate(values):
                        if sheet.cell_type(row_index, column_index) == xlrd.XL_CELL_DATE:
                            values[column_index] = xlrd.xldate_as_datetime(value, workbook.datemode)
                    yield values

            return scan(rows())
        finally:
            workbook.release_resources()
    for encoding in list(_CSV_ENCODINGS) + ['latin-1']:
        try:
            with path.open(encoding=encoding, newline='') as source:
                return scan(iter(csv.reader(source, delimiter='\t' if suffix == '.tsv' else ',', strict=True)))
        except UnicodeError:
            continue
        except csv.Error as error:
            raise ValueError('表格结构无法读取') from error
    raise ValueError('表格编码无法读取')


def inspect_pep_content(path, field_mapping=None):
    import csv
    import gzip
    import math
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    path = PathAccessService.validate_read_path(path)
    result = _inspect_input_quality([str(path)], "", "", "", pep_field_mapping=field_mapping)
    report = result["inputs"][0]
    try:
        from flask_app.routes.api_script_hub._common import _CSV_ENCODINGS

        lowered_name = path.name.lower()
        compressed = lowered_name.endswith((".csv.gz", ".tsv.gz"))
        delimiter = "\t" if lowered_name.endswith((".tsv", ".tsv.gz")) else ","
        opener = gzip.open if compressed else open
        encodings = list(dict.fromkeys(["utf-8-sig", *_CSV_ENCODINGS, "latin-1"]))
        last_decode_error = None
        for encoding in encodings:
            try:
                with opener(path, "rt", encoding=encoding, newline="") as source:
                    rows = csv.reader(source, delimiter=delimiter, strict=True)
                    columns = next(rows, [])
                    if field_mapping is not None:
                        from flask_app.routes.api_script_hub._common import _find_matching_column, _COLUMN_HINTS
                        cdr3_column = str(field_mapping.get("cdr3_column") or _find_matching_column(columns, _COLUMN_HINTS["cdr3_column"]))
                        copy_column = str(field_mapping.get("copy_column") or _find_matching_column(columns, _COLUMN_HINTS["copy_column"]))
                        required = (cdr3_column, copy_column)
                        sequence_fields = (cdr3_column,)
                    else:
                        required = ("CDR3(pep)", "V", "J", "copy")
                        sequence_fields = ("CDR3(pep)", "V", "J")
                        copy_column = "copy"
                    missing = sorted(set(required) - set(columns))
                    if missing:
                        raise ValueError("缺少字段：" + "、".join(missing))
                    positions = {field: columns.index(field) for field in required}
                    row_count = bad_counts = blank_fields = 0
                    for row_number, row in enumerate(rows, start=2):
                        if len(row) != len(columns):
                            raise ValueError(f"第 {row_number} 行字段数与表头不一致")
                        row_count += 1
                        for field in sequence_fields:
                            if not row[positions[field]].strip():
                                blank_fields += 1
                        try:
                            copy_count = float(row[positions[copy_column]].strip())
                            if not math.isfinite(copy_count) or copy_count < 0:
                                bad_counts += 1
                        except (ValueError, TypeError, OverflowError):
                            bad_counts += 1
                break
            except csv.Error as error:
                raise ValueError(f"表格结构无法读取：{error}") from error
            except UnicodeError as error:
                last_decode_error = error
        else:
            raise ValueError("表格编码无法读取") from last_decode_error

        if not row_count:
            raise ValueError("数据表为空")
        if bad_counts or blank_fields:
            raise ValueError(f"存在 {bad_counts} 个无效拷贝数和 {blank_fields} 个空必需字段")
        report["row_count"] = row_count
        report["columns"] = columns
    except (ValueError, OSError, KeyError) as error:
        report["status"] = "invalid"
        result["errors"].append(f"克隆序列表 {path.name}：{error}")
    return result


def inspect_input_quality(pep_paths, profile_path, transcriptome_path, deconvolution_path, profile_batch_field=None, profile_sample_column=None, pep_field_mapping=None):
    from flask_app.services.input_validation_cache import cached_validation
    from flask_app.routes.api_script_hub._common import _iter_candidate_pep_files
    result = _inspect_input_quality(pep_paths, "", "", "", pep_field_mapping=pep_field_mapping)
    pep_pending = False
    for path in _iter_candidate_pep_files(pep_paths, pep_field_mapping):
        checked = cached_validation(path, "pep", lambda path=path: inspect_pep_content(path, pep_field_mapping),
                                    options={"field_mapping": pep_field_mapping} if pep_field_mapping is not None else None)
        result["errors"].extend(checked["errors"])
        pep_pending = pep_pending or any(item.get("status") == "pending" for item in checked["inputs"])
    if result["inputs"]:
        if pep_pending: result["inputs"][0]["status"] = "pending"
        elif result["errors"]: result["inputs"][0]["status"] = "invalid"
    samples = {}
    for kind, value in (("profile", profile_path), ("transcriptome", transcriptome_path), ("deconvolution", deconvolution_path)):
        if not value: continue
        args = {"profile": "", "transcriptome": "", "deconvolution": ""}
        args[kind] = value
        checked = cached_validation(value, kind, lambda: _inspect_input_quality(
            [], args["profile"], args["transcriptome"], args["deconvolution"],
            profile_batch_field if kind == 'profile' else None,
            profile_sample_column if kind == 'profile' else None,
        ), options=({**({"batch_field": profile_batch_field} if profile_batch_field else {}),
                     **({"sample_col": profile_sample_column} if profile_sample_column else {})} or None) if kind == 'profile' else None)
        result["inputs"].extend(checked["inputs"])
        result["errors"].extend(checked["errors"])
        result["warnings"].extend(checked["warnings"])
        if checked["inputs"] and checked["inputs"][0].get("status") != "pending": samples[kind] = set(checked["inputs"][0].get("samples", []))
    if pep_paths and not pep_pending:
        from flask_app.routes.api_script_hub._common import _infer_wide_chain_from_filename, _chain_from_parent_dirs, _sample_name_from_pep_file
        samples["pep"] = {_sample_name_from_pep_file(path, chain) for path in _iter_candidate_pep_files(pep_paths, pep_field_mapping) if (chain := _infer_wide_chain_from_filename(path.name) or _chain_from_parent_dirs(path))}
    reference = next((kind for kind in ("profile", "pep", "transcriptome", "deconvolution") if samples.get(kind)), "")
    result.update(reference_kind=reference, reference_label=LABELS.get(reference, ""))
    for kind, values in samples.items():
        if kind == reference or not reference: continue
        baseline = samples[reference]
        missing, extra = sorted(baseline - values), sorted(values - baseline)
        result["alignments"].append(dict(kind=kind, label=LABELS[kind], matched_count=len(baseline & values), missing_count=len(missing), extra_count=len(extra), missing_samples=missing[:50], extra_samples=extra[:50]))
        if missing or extra: result["warnings"].append(f"{LABELS[kind]}与{LABELS[reference]}样本不完全对应，请确认联合分析范围。")
    result["errors"] = list(dict.fromkeys(result["errors"]))
    result["warnings"] = list(dict.fromkeys(result["warnings"]))
    return result


def inspect_selected_input_quality(pep_paths, profile_path, transcriptome_path, deconvolution_path,
                                   *, alignment_groups=None, profile_batch_field=None):
    """Combine content checks without aligning unrelated independent analyses."""
    if alignment_groups is None:
        return inspect_input_quality(pep_paths, profile_path, transcriptome_path, deconvolution_path,
                                     profile_batch_field=profile_batch_field)
    values = {"pep": pep_paths, "profile": profile_path, "transcriptome": transcriptome_path,
              "deconvolution": deconvolution_path}
    def inspect(kinds):
        return inspect_input_quality(values["pep"] if "pep" in kinds else [],
            values["profile"] if "profile" in kinds else "", values["transcriptome"] if "transcriptome" in kinds else "",
            values["deconvolution"] if "deconvolution" in kinds else "", profile_batch_field=profile_batch_field)
    result = {"inputs": [], "errors": [], "warnings": [], "alignments": [], "reference_kind": "", "reference_label": ""}
    for kind, value in values.items():
        if not value:
            continue
        checked = inspect({kind})
        for key in ("inputs", "errors", "warnings"):
            result[key].extend(checked[key])
    seen = set()
    for group in alignment_groups:
        checked = inspect(set(group))
        for alignment in checked["alignments"]:
            key = (checked["reference_kind"], alignment["kind"])
            if key in seen:
                continue
            seen.add(key)
            result["alignments"].append(alignment)
        if checked["alignments"]:
            result["reference_kind"] = checked["reference_kind"]
            result["reference_label"] = checked["reference_label"]
        result["warnings"].extend(checked["warnings"])
    for key in ("errors", "warnings"):
        result[key] = list(dict.fromkeys(result[key]))
    return result
