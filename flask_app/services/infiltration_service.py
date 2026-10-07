"""Project-scoped adapter for the original infiltration A/B R analyses."""
import json
from pathlib import Path
import subprocess
import tempfile

from flask_app.exceptions import ValidationError
from flask_app.services.input_quality import inspect_input_quality, SAMPLE_COLUMNS

SCORE_TYPES = {'relative': '相对比例', 'absolute': '绝对分数', 'other': '其他原始估计分数'}


def validate_score_type(value):
    if not isinstance(value, str) or value not in SCORE_TYPES:
        raise ValidationError(message='请根据输入文件的生成方式，选择相对比例、绝对分数或其他原始估计分数。')
    return value


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts' / 'infiltration' / '07.immuneInfiltration'


def inspect_inputs(profile_path, deconvolution_path, group_field='', cell_columns=None, *, selected_infiltration_samples=None, selected_infiltration_groups=None, validate_group_counts=True):
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    quality = inspect_input_quality([], profile_path, '', deconvolution_path)
    if quality['errors']:
        raise ValidationError(message='；'.join(quality['errors']))
    report = next(item for item in quality['inputs'] if item['kind']=='deconvolution')
    if report['status'] != 'checked':
        raise ValidationError(message='请先确认免疫浸润结果的样本编号列。')
    profile = _robust_read_csv(Path(profile_path), dtype=str, keep_default_na=False)
    sample_columns = [column for column in profile if str(column).strip().casefold() in SAMPLE_COLUMNS]
    if len(sample_columns) != 1:
        raise ValidationError(message='请先确认样本指标表的唯一编号列。')
    sample_column = sample_columns[0]
    fields = [str(column) for column in profile if column != sample_column]
    cells = report.get('cell_columns', [])
    selected = cells if cell_columns is None else cell_columns
    if not isinstance(selected,list) or not selected or any(not isinstance(x,str) or x not in cells or ',' in x for x in selected) or len(set(selected)) != len(selected):
        raise ValidationError(message='请选择有效且不重复的细胞列，列名不能包含逗号。')
    result = {'group_fields':fields, 'cell_columns':cells, 'sample_count':report['sample_count'], 'deconvolution_sample_column':report['sample_column']}
    if not group_field:
        return result
    if group_field not in fields:
        raise ValidationError(message='请选择样本指标表中的分组字段。')
    table = _robust_read_csv(Path(deconvolution_path), dtype=str, keep_default_na=False)
    ids = table[report['sample_column']].str.strip()
    profile[sample_column] = profile[sample_column].str.strip()
    groups = profile.set_index(sample_column)[group_field].str.strip()
    available_ids = ids.tolist()
    for label, choices, available in (("浸润样本", selected_infiltration_samples, available_ids),
                                       ("浸润分组", selected_infiltration_groups, ids.map(groups).dropna().unique().tolist())):
        if choices is not None:
            if not isinstance(choices, list) or not choices or any(not isinstance(item, str) or item not in available for item in choices):
                raise ValidationError(message=f"请选择当前输入中有效且非空的{label}范围。")
    keep = ids.isin(selected_infiltration_samples) if selected_infiltration_samples is not None else ids.notna()
    if selected_infiltration_groups is not None:
        keep &= ids.map(groups).isin(selected_infiltration_groups)
    if not validate_group_counts:
        keep &= ids.isin(groups.index)
    table = table.loc[keep].copy()
    ids = ids.loc[keep]
    if ids.empty:
        raise ValidationError(message='所选浸润样本与分组没有交集。')
    missing = ids[~ids.isin(groups.index)].tolist()
    if missing:
        raise ValidationError(message='浸润样本在样本指标表中缺少分组：'+'、'.join(missing[:10]))
    assigned = ids.map(groups)
    if assigned.eq('').any():
        raise ValidationError(message='匹配样本的分组为空，请先补充分组。')
    if assigned.str.contains(',',regex=False).any():
        raise ValidationError(message='分组名称不能包含逗号。')
    counts = assigned.value_counts(sort=False).to_dict()
    if validate_group_counts and (len(counts)<2 or any(count<2 for count in counts.values())):
        raise ValidationError(message='组间比较至少需要两个分组，且每组至少两个匹配样本。')
    result.update(group_counts=counts, sample_count=len(ids), selected_infiltration_samples=ids.tolist(), scope_samples=ids.tolist(),
        samples_by_value={group: ids[assigned.eq(group)].tolist() for group in counts},
        selected_infiltration_groups=list(counts),
        unused_deconvolution_count=len(available_ids)-len(ids), unused_profile_count=len(set(groups.index)-set(ids)))
    # Internal columns avoid collisions with cell feature names and keep IDs textual.
    prepared = table[selected].apply(lambda column: column.astype(float))
    prepared.insert(0,'sample',ids.to_numpy())
    metadata = profile.loc[profile[sample_column].isin(ids),[sample_column,group_field]].copy()
    metadata.columns=['sample','group']
    return result, prepared, metadata


def inspect_consistency(profile_path, deconvolution_path, group_field='', cell_columns=None, **scope):
    result = inspect_inputs(profile_path, deconvolution_path, group_field, cell_columns, **scope)
    if not group_field:
        return result
    summary, prepared, metadata = result
    cells = list(prepared.columns[1:])
    if len(cells) < 2:
        raise ValidationError(message='细胞相关性至少需要选择两个细胞类型。')
    if any(count < 3 for count in summary['group_counts'].values()):
        raise ValidationError(message='细胞相关性每组至少需要三个匹配样本。')
    groups = prepared['sample'].map(metadata.set_index('sample')['group']).str.strip()
    ranks = prepared[cells].rank(method='average')
    residuals = ranks - ranks.groupby(groups).transform('mean')
    constant = [cell for cell in cells if float(residuals[cell].var()) < 1e-12]
    if constant:
        raise ValidationError(message='以下细胞在组别校正后无变化，无法计算相关性，请取消选择：'+'、'.join(constant))
    return result


SUBCLASS_COLUMNS = ['IGHM', 'IGHD', 'IGHA1', 'IGHA2', 'IGHG3', 'IGHG4', 'IGHGP', 'IGHE']


def inspect_concordance(profile_path, deconvolution_path, group_field='', cell_columns=None, subclass_columns=None, **scope):
    import numpy as np
    import pandas as pd
    from flask_app.routes.api_script_hub._common import _robust_read_csv
    result = inspect_inputs(profile_path, deconvolution_path, group_field, cell_columns, **scope)
    profile = _robust_read_csv(Path(profile_path), dtype=str, keep_default_na=False)
    available = [column for column in SUBCLASS_COLUMNS if column in profile and column != group_field]
    summary = result[0] if isinstance(result, tuple) else result
    summary['subclass_columns'] = available
    if not available:
        raise ValidationError(message='样本指标表中没有可用的免疫球蛋白亚类指标，需要 IGHM、IGHD、IGHA1、IGHA2、IGHG3、IGHG4、IGHGP 或 IGHE 列。')
    if not group_field:
        return summary
    selected = available if subclass_columns is None else subclass_columns
    if not isinstance(selected, list) or not selected or any(not isinstance(x,str) or x not in available for x in selected) or len(set(selected)) != len(selected):
        raise ValidationError(message='请选择有效且不重复的亚类指标。')
    summary, prepared, metadata = result
    sample_column = next(column for column in profile if str(column).strip().casefold() in SAMPLE_COLUMNS)
    profile[sample_column] = profile[sample_column].str.strip()
    indexed = profile.set_index(sample_column)
    for column in selected:
        numeric = pd.to_numeric(metadata['sample'].map(indexed[column]), errors='coerce')
        if not np.isfinite(numeric.to_numpy(dtype=float)).all():
            raise ValidationError(message=f'亚类指标 {column} 的参与样本存在缺失或非数值，请修正后再运行；不会自动填零。')
        metadata[column] = numeric.to_numpy()
    summary['selected_subclasses'] = selected
    return summary, prepared, metadata



def inspect_pathway(profile_path, deconvolution_path, group_field, cell_columns, go_gsea_path, comparison, **scope):
    from flask_app.services.pathway_artifacts import validate_go_bp_table
    if not isinstance(comparison, list) or len(comparison) != 2 or any(
        not isinstance(group, str) or not group or ':' in group for group in comparison
    ) or comparison[0] == comparison[1]:
        raise ValidationError(message='请选择两个不同组别的明确比较方向，组名不能包含冒号。')
    summary, prepared, metadata = inspect_inputs(profile_path, deconvolution_path, group_field, cell_columns, **scope)
    if any(group not in summary['group_counts'] for group in comparison):
        raise ValidationError(message='通路来源的比较组别与当前浸润样本分组不一致。')
    validate_go_bp_table(go_gsea_path)
    metadata = metadata[metadata['group'].isin(comparison)].copy()
    prepared = prepared[prepared['sample'].isin(metadata['sample'])].copy()
    summary.update(comparison=comparison, sample_count=len(prepared),
        excluded_group_sample_count=sum(count for group,count in summary['group_counts'].items() if group not in comparison),
        group_counts={group:summary['group_counts'][group] for group in comparison})
    excluded = len(summary['scope_samples']) - len(prepared)
    summary['unused_profile_count'] += excluded
    summary['unused_deconvolution_count'] += excluded
    summary['selected_infiltration_samples'] = prepared['sample'].tolist()
    return summary, prepared, metadata


def generate_report(profile_path, deconvolution_path, group_field, cell_columns, output_parent, progress, cancelled, score_type=None, analysis_kind="composition", subclass_columns=None, sample_pairs=None, go_gsea_path=None, comparison=None, expression_path=None, selected_infiltration_samples=None, selected_infiltration_groups=None, output_name=None):
    if analysis_kind not in {"composition", "consistency", "concordance", "paired", "pathway", "sample_pathway"}:
        raise ValidationError(message="不支持的浸润分析类型。")
    if score_type is not None:
        validate_score_type(score_type)
    scope = dict(selected_infiltration_samples=selected_infiltration_samples, selected_infiltration_groups=selected_infiltration_groups)
    inspector = inspect_consistency if analysis_kind == "consistency" else inspect_inputs
    if analysis_kind == "pathway":
        summary, prepared, metadata = inspect_pathway(profile_path,deconvolution_path,group_field,cell_columns,go_gsea_path,comparison, **scope)
    elif analysis_kind == "sample_pathway":
        from flask_app.services.infiltration_sample_pathway import inspect_sample_pathway
        summary, prepared, metadata = inspect_sample_pathway(
            profile_path, deconvolution_path, expression_path, group_field,
            cell_columns, comparison, **scope,
        )
    elif analysis_kind == "paired":
        from flask_app.services.infiltration_pairing import inspect_paired
        summary, prepared, metadata = inspect_paired(profile_path,deconvolution_path,group_field,cell_columns,subclass_columns,sample_pairs)
    elif analysis_kind == "concordance":
        summary, prepared, metadata = inspect_concordance(profile_path,deconvolution_path,group_field,cell_columns,subclass_columns, **scope)
    else:
        summary, prepared, metadata = inspector(profile_path,deconvolution_path,group_field,cell_columns, **scope)
    summary.update(output_name=output_name or '免疫浸润分析', score_type=score_type or 'unspecified', score_type_label=SCORE_TYPES.get(score_type, '历史任务未标注'))
    from flask_app.services.project_storage_paths import allocate_result_dir
    modules = {'composition': 'immune-infiltration', 'consistency': 'immune-infiltration-consistency', 'concordance': 'immune-infiltration-concordance', 'paired': 'immune-infiltration-paired', 'pathway': 'immune-infiltration-pathway', 'sample_pathway': 'immune-infiltration-sample-pathway'}
    job_id, output = allocate_result_dir(Path(output_parent), modules[analysis_kind])
    prepared.to_csv(output/'input.csv',index=False)
    metadata.to_csv(output/'groups.csv',index=False)
    if analysis_kind == 'paired':
        import pandas as pd
        metadata.to_csv(output/'subclass.csv',index=False)
        pd.DataFrame({'sample':prepared['sample'],'group':metadata['group']}).to_csv(output/'groups.csv',index=False)
        pd.DataFrame({'cibersort_id':prepared['sample'],'profile_sample':metadata['sample'],'group':metadata['group'],'mapping_status':'paired'}).to_csv(output/'sample_manifest.csv',index=False)
    config={'paths':{'datapoint_input':str(output/'groups.csv'),'deconvolution':str(output/'input.csv'),'output_root':str(output)},
        'datapoint':{'sample_column':'sample','group_column':'group','group_order':list(summary['group_counts'])},
        'immune_infiltration':{'sample_column':'sample','group_column':'category','cell_columns':cell_columns}}
    if analysis_kind == 'pathway':
        import shutil
        shutil.copyfile(go_gsea_path,output/'GO_BP_full.csv')
        config['immune_infiltration']['comparisons']=[comparison]
    if analysis_kind == 'sample_pathway':
        config['paths']['transcriptome_expression'] = '临时生成的样本筛选表达矩阵'
        config['immune_infiltration']['comparisons'] = [comparison]
        config['immune_infiltration']['sample_pathway_method'] = 'GOALL ssGSEA; group-residual partial Spearman; within-group permutation'
    config_path=output/'config.json'
    config_path.write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
    expression_subset_path = None
    if analysis_kind == 'sample_pathway':
        from flask_app.services.infiltration_sample_pathway import write_expression_subset
        with tempfile.NamedTemporaryFile(prefix=f'{job_id}_', suffix='.csv', dir=output.parent, delete=False) as temporary:
            expression_subset_path = Path(temporary.name)
        try:
            write_expression_subset(expression_path, prepared['sample'].tolist(), expression_subset_path)
        except Exception:
            expression_subset_path.unlink(missing_ok=True)
            raise
    stages = [('04.plot_cell_consistency.R','计算组别校正细胞相关性')] if analysis_kind == 'consistency' else [('02.plot_deconv_composition.R','计算细胞组成'),('03.plot_deconv_group_comparison.R','计算组间差异')]
    if analysis_kind == "concordance":
        stages = [("05.plot_directional_concordance.R", "计算亚类与细胞的组间变化方向")]
    if analysis_kind == "paired":
        stages = [("06.plot_paired_concordance.R", "计算明确配对的跨数据相关性")]
    if analysis_kind == "pathway":
        stages = [("07.plot_pathway_direction.R", "计算 GO-BP 通路与细胞的方向一致性")]
    if analysis_kind == "sample_pathway":
        stages = [("08.plot_go_sample_concordance.R", "计算 GO-BP 样本通路分数与浸润相关性")]
    try:
        for index,(script,label) in enumerate(stages):
            progress(15+index*40,label,'使用原始分析脚本')
            command=['Rscript',str(SCRIPTS/script),'--config='+str(config_path),'--dpi=150','--split-cell=none']
            if analysis_kind == 'pathway':
                command.extend(['--go-gsea='+str(output/'GO_BP_full.csv'),'--output='+str(output/'pathway_direction'),'--comparison='+':'.join(comparison)])
            if analysis_kind == 'sample_pathway':
                command.extend([
                    '--input='+str(output/'input.csv'),
                    '--groups='+str(output/'groups.csv'),
                    '--expression='+str(expression_subset_path),
                    '--output='+str(output),
                    '--cell-cols='+','.join(cell_columns),
                    '--comparison-json='+json.dumps(comparison,ensure_ascii=False,separators=(',',':')),
                ])
            if analysis_kind == 'paired':
                command.extend(['--subclass='+str(output/'subclass.csv'),'--sample-manifest='+str(output/'sample_manifest.csv')])
            if analysis_kind == 'consistency':
                command.append('--score-type='+str(score_type or 'other'))
                if score_type == 'absolute':
                    command.append('--absolute='+str(output/'input.csv'))
            with (output/f'stage_{index+1}.log').open('w',encoding='utf-8') as log:
                process=subprocess.Popen(command,stdout=log,stderr=subprocess.STDOUT)
                try:
                    for _ in range(1800):
                        if cancelled():
                            raise RuntimeError('分析已取消')
                        try:
                            code=process.wait(timeout=1)
                            break
                        except subprocess.TimeoutExpired:
                            continue
                    else:
                        raise RuntimeError('分析超过运行时限')
                    if code:
                        log.flush()
                        detail = (output/f'stage_{index+1}.log').read_text(encoding='utf-8',errors='replace')[-1200:].strip()
                        raise RuntimeError(f'{label}失败（退出码 {code}）：{detail}')
                finally:
                    if process.poll() is None:
                        process.terminate()
                        try: process.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            process.kill();process.wait()
    finally:
        if expression_subset_path is not None:
            expression_subset_path.unlink(missing_ok=True)
    summary.update(method='输入类型：'+summary['score_type_label']+'；组成图：全局最小值平移后按行归一化；组间比较：原始数值、双侧 Wilcoxon 检验及全体比较 BH 校正。', group_field=group_field)
    if analysis_kind == 'consistency':
        summary.update(method='输入类型：'+summary['score_type_label']+'；按细胞秩转换并去除组别效应，计算残差相关；p 值沿用原脚本的残差 Pearson 检验，细胞对统一 BH 校正。相关性不表示因果关系。', analysis_kind=analysis_kind)
    if analysis_kind == 'concordance':
        summary.update(method='输入类型：'+summary['score_type_label']+'；在本次匹配样本中比较亚类指标与细胞分数的组间中位数差，沿用原脚本单侧 Wilcoxon 组合的方向联合 p 值与每个比较内 BH 校正；这是组间方向比较，不是样本配对相关性。',analysis_kind=analysis_kind)
    if analysis_kind == 'paired':
        summary.update(method='输入类型：'+summary['score_type_label']+'；仅使用明确的一对一配对，按各指标秩转换并去除指标表分组效应后计算残差相关；p 值沿用原脚本的残差 Pearson 检验，亚类与细胞组合统一 BH 校正。配对清单随结果保存。',analysis_kind=analysis_kind)
    if analysis_kind == 'pathway':
        summary.update(method='GO-BP 的 NES 方向与浸润细胞组间中位数差比较；原脚本单侧 Wilcoxon 与 GSEA 方向 p 值组成联合检验，全部通路与细胞组合统一 BH 校正。零效应标为无方向差异。该分析用于内部生物学一致性判断。',analysis_kind=analysis_kind)
    if analysis_kind == 'sample_pathway':
        summary.update(method='10 项固定 GO-BP 使用 org.Hs.eg.db 的 GOALL 注释构建基因集，在 log2(表达量+1) 上计算 GSVA ssGSEA。样本分数与浸润分数分别秩转换并去除组别效应；按组内置换浸润残差估计 p 值，通路与细胞组合统一 BH 校正。该分析属于探索性内部生物学一致性分析。',analysis_kind=analysis_kind)
    summary['analysis_notes'] = [f"本次分析 {summary['sample_count']} 个实际匹配样本；分组来源：{group_field}。", *[f'{group}：{count} 个样本。' for group, count in summary['group_counts'].items()], summary['method']]
    (output/'analysis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return job_id,output,summary
