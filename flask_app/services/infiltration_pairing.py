"""Explicit, project-scoped sample pairing for cross-modality analysis."""
from pathlib import Path

import numpy as np
import pandas as pd

from flask_app.exceptions import ValidationError
from flask_app.services.input_quality import SAMPLE_COLUMNS


def inspect_paired(profile_path, deconvolution_path, group_field='', cell_columns=None,
                   subclass_columns=None, sample_pairs=None):
    from flask_app.services.infiltration_service import inspect_inputs, SUBCLASS_COLUMNS
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    summary = inspect_inputs(profile_path, deconvolution_path, '', cell_columns)
    profile = _robust_read_csv(Path(profile_path), dtype=str, keep_default_na=False)
    deconv = _robust_read_csv(Path(deconvolution_path), dtype=str, keep_default_na=False)
    sample_column = next(column for column in profile if str(column).strip().casefold() in SAMPLE_COLUMNS)
    deconv_column = summary['deconvolution_sample_column']
    profile[sample_column] = profile[sample_column].str.strip()
    deconv[deconv_column] = deconv[deconv_column].str.strip()
    metrics = [column for column in SUBCLASS_COLUMNS if column in profile and column != group_field]
    summary.update(profile_samples=profile[sample_column].tolist(), deconvolution_samples=deconv[deconv_column].tolist(), subclass_columns=metrics)
    if not metrics:
        raise ValidationError(message='样本指标表没有可用的免疫球蛋白亚类指标，请补充 IGHM、IGHD、IGHA1 等原始指标。')
    if not group_field:
        return summary
    if group_field not in summary['group_fields']:
        raise ValidationError(message='请选择样本指标表中的分组字段。')
    selected = metrics if subclass_columns is None else subclass_columns
    cells = summary['cell_columns'] if cell_columns is None else cell_columns
    if not isinstance(selected,list) or not selected or any(not isinstance(x,str) or x not in metrics for x in selected) or len(set(selected)) != len(selected):
        raise ValidationError(message='请选择有效且不重复的亚类指标。')
    if set(selected) & set(cells):
        raise ValidationError(message='细胞列与亚类指标存在重名，请在源数据中使用不同列名。')
    if not isinstance(sample_pairs,list) or not sample_pairs:
        raise ValidationError(message='请明确填写浸润样本与指标样本的一对一配对关系。')
    pairs=[]
    for pair in sample_pairs:
        if not isinstance(pair,dict) or not all(isinstance(pair.get(key),str) and pair[key].strip() for key in ['deconvolution_sample','profile_sample']):
            raise ValidationError(message='配对记录需要填写两侧完整的样本编号。')
        pairs.append({key:pair[key].strip() for key in ['deconvolution_sample','profile_sample']})
    dids=[pair['deconvolution_sample'] for pair in pairs]
    pids=[pair['profile_sample'] for pair in pairs]
    if len(set(dids)) != len(dids) or len(set(pids)) != len(pids):
        raise ValidationError(message='每个样本只能参与一次配对，请修改重复配对。')
    if set(dids)-set(summary['deconvolution_samples']) or set(pids)-set(summary['profile_samples']):
        raise ValidationError(message='配对中存在不属于当前所选文件的样本编号。')
    matched=profile.set_index(sample_column).loc[pids]
    groups=matched[group_field].str.strip()
    if groups.eq('').any():
        raise ValidationError(message='配对指标样本存在空分组，请补全分组。')
    if groups.str.contains(',',regex=False).any():
        raise ValidationError(message='分组名称不能包含逗号。')
    counts=groups.value_counts(sort=False).to_dict()
    if len(counts)<2 or any(count<3 for count in counts.values()):
        raise ValidationError(message='配对相关性至少需要两个分组，每组至少三个有效配对。')
    prepared=deconv.set_index(deconv_column).loc[dids,cells].astype(float).reset_index(drop=True)
    metrics_frame=matched[selected].apply(pd.to_numeric,errors='coerce').reset_index(drop=True)
    if not np.isfinite(metrics_frame.to_numpy(dtype=float)).all():
        raise ValidationError(message='配对亚类指标存在缺失或非法数值，不会自动填零。')
    group_series=pd.Series(groups.to_numpy())
    for frame in [prepared,metrics_frame]:
        ranks=frame.rank(method='average')
        residuals=ranks-ranks.groupby(group_series).transform('mean')
        constant=[column for column in frame if float(residuals[column].var())<1e-12]
        if constant:
            raise ValidationError(message='以下指标在配对样本组别校正后无变化，请取消选择：'+'、'.join(constant))
    prepared.insert(0,'sample',dids)
    metadata=metrics_frame.copy()
    metadata.insert(0,'group',groups.to_numpy())
    metadata.insert(0,'sample',pids)
    summary.update(sample_count=len(pairs), group_counts=counts, selected_subclasses=selected,
                   sample_pairs=pairs, unused_profile_count=len(profile)-len(pairs),
                   unused_deconvolution_count=len(deconv)-len(pairs))
    return summary,prepared,metadata


def validate_paired_assets(input_assets, config):
    """Recheck explicit pairing at admission and worker start, not ID intersection."""
    from flask_app.services.input_quality import validate_analysis_inputs
    paths={asset.get('asset_type'):asset.get('path') for asset in input_assets or []}
    if not paths.get('profile') or not paths.get('deconvolution') or not config.get('group_field'):
        raise ValidationError(message='配对分析缺少输入文件或分组配置。')
    inputs=[]
    for asset in input_assets:
        checked=validate_analysis_inputs([asset])
        inputs.extend(checked['inputs'])
    summary, _, _ = inspect_paired(paths['profile'],paths['deconvolution'],config['group_field'],
                                  config.get('cell_columns'),config.get('subclass_columns'),config.get('sample_pairs'))
    # Each submitted pair was validated above. Unselected rows are outside
    # this explicit analysis scope, not missing or extra matched identities.
    return {'inputs':inputs,'reference_kind':'profile','reference_label':'样本指标表',
            'alignments':[{'kind':'deconvolution','label':'免疫浸润结果表','matched_count':summary['sample_count'],
                           'missing_count':0,'extra_count':0,
                           'unused_profile_count':summary['unused_profile_count'],
                           'unused_deconvolution_count':summary['unused_deconvolution_count'],
                           'missing_samples':[],'extra_samples':[],'matching_method':'explicit_pairs'}],
            'warnings':[],'errors':[]}
