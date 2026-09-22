"""Project-scoped adapter for the original infiltration A/B R analyses."""
import json
from pathlib import Path
import subprocess
import uuid

from flask_app.exceptions import ValidationError
from flask_app.services.input_quality import inspect_input_quality, SAMPLE_COLUMNS

SCORE_TYPES = {'relative': '相对比例', 'absolute': '绝对分数', 'other': '其他原始估计分数'}


def validate_score_type(value):
    if not isinstance(value, str) or value not in SCORE_TYPES:
        raise ValidationError(message='请根据输入文件的生成方式，选择相对比例、绝对分数或其他原始估计分数。')
    return value


SCRIPTS = Path(__file__).resolve().parents[2] / 'scripts' / 'infiltration' / '07.immuneInfiltration'


def inspect_inputs(profile_path, deconvolution_path, group_field='', cell_columns=None):
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
    result = {'group_fields':fields, 'cell_columns':cells, 'sample_count':report['sample_count']}
    if not group_field:
        return result
    if group_field not in fields:
        raise ValidationError(message='请选择样本指标表中的分组字段。')
    table = _robust_read_csv(Path(deconvolution_path), dtype=str, keep_default_na=False)
    ids = table[report['sample_column']].str.strip()
    profile[sample_column] = profile[sample_column].str.strip()
    groups = profile.set_index(sample_column)[group_field].str.strip()
    missing = ids[~ids.isin(groups.index)].tolist()
    if missing:
        raise ValidationError(message='浸润样本在样本指标表中缺少分组：'+'、'.join(missing[:10]))
    assigned = ids.map(groups)
    if assigned.eq('').any():
        raise ValidationError(message='匹配样本的分组为空，请先补充分组。')
    if assigned.str.contains(',',regex=False).any():
        raise ValidationError(message='分组名称不能包含逗号。')
    counts = assigned.value_counts(sort=False).to_dict()
    if len(counts)<2 or any(count<2 for count in counts.values()):
        raise ValidationError(message='组间比较至少需要两个分组，且每组至少两个匹配样本。')
    result.update(group_counts=counts, unused_profile_count=len(set(groups.index)-set(ids)))
    # Internal columns avoid collisions with cell feature names and keep IDs textual.
    prepared = table[selected].apply(lambda column: column.astype(float))
    prepared.insert(0,'sample',ids.to_numpy())
    metadata = profile.loc[profile[sample_column].isin(ids),[sample_column,group_field]].copy()
    metadata.columns=['sample','group']
    return result, prepared, metadata


def generate_report(profile_path, deconvolution_path, group_field, cell_columns, output_parent, progress, cancelled, score_type=None):
    if score_type is not None:
        validate_score_type(score_type)
    summary, prepared, metadata = inspect_inputs(profile_path,deconvolution_path,group_field,cell_columns)
    summary.update(score_type=score_type or 'unspecified', score_type_label=SCORE_TYPES.get(score_type, '历史任务未标注'))
    job_id='infiltration_'+uuid.uuid4().hex[:12]
    output=Path(output_parent)/job_id
    output.mkdir(parents=True)
    prepared.to_csv(output/'input.csv',index=False)
    metadata.to_csv(output/'groups.csv',index=False)
    config={'paths':{'datapoint_input':str(output/'groups.csv'),'deconvolution':str(output/'input.csv'),'output_root':str(output)},
        'datapoint':{'sample_column':'sample','group_column':'group','group_order':list(summary['group_counts'])},
        'immune_infiltration':{'sample_column':'sample','group_column':'category','cell_columns':cell_columns}}
    config_path=output/'config.json'
    config_path.write_text(json.dumps(config,ensure_ascii=False),encoding='utf-8')
    for index,(script,label) in enumerate([('02.plot_deconv_composition.R','计算细胞组成'),('03.plot_deconv_group_comparison.R','计算组间差异')]):
        progress(15+index*40,label,'使用原始分析脚本')
        command=['Rscript',str(SCRIPTS/script),'--config='+str(config_path),'--dpi=150','--split-cell=none']
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
    summary.update(method='输入类型：'+summary['score_type_label']+'；组成图：全局最小值平移后按行归一化；组间比较：原始数值、双侧 Wilcoxon 检验及全体比较 BH 校正。', group_field=group_field)
    (output/'analysis_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    return job_id,output,summary
