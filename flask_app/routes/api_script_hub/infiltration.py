"""Immune infiltration tasks using the existing Script Hub queue and results."""
from pathlib import Path
import uuid
from contextlib import ExitStack
from flask import Blueprint, request, jsonify, current_app, has_app_context, has_request_context, g
from flask_app.exceptions import ValidationError
from flask_app.services import infiltration_service
from flask_app.services.project_storage_paths import script_output_parent
from . import _common as shared

bp=Blueprint('script_hub_infiltration',__name__)
MODULE='immune-infiltration'
CONSISTENCY='immune-infiltration-consistency'
CONCORDANCE='immune-infiltration-concordance'
PAIRED='immune-infiltration-paired'
PATHWAY='immune-infiltration-pathway'
SAMPLE_PATHWAY='immune-infiltration-sample-pathway'


def inspector_for(module):
    return infiltration_service.inspect_consistency if module == CONSISTENCY else infiltration_service.inspect_inputs


def inspect_request(module, profile, deconvolution, data, *, scope_only=False):
    scope = {key: data.get(key) for key in ('selected_infiltration_samples', 'selected_infiltration_groups')}
    args = (profile, deconvolution, data.get('group_field') or '', data.get('cell_columns'))
    if scope_only:
        scope = {'validate_group_counts': False}
        if module not in {SAMPLE_PATHWAY, PAIRED}:
            return infiltration_service.inspect_inputs(*args, **scope)
        args = (profile, deconvolution, '' if module == PAIRED else args[2], data.get('cell_columns'))
    if module == SAMPLE_PATHWAY:
        from flask_app.routes.api_script_hub._common import _transcriptome_path_from_request
        expression = _transcriptome_path_from_request(data, 'expression_path', 'transcriptome_path')
        if not expression:
            raise ValidationError(message='请选择当前项目数据集的转录组表达矩阵。')
        from flask_app.services.infiltration_sample_pathway import inspect_sample_pathway
        return inspect_sample_pathway(
            profile, deconvolution, expression, data.get('group_field') or '',
            data.get('cell_columns'), None if scope_only else data.get('comparison'), **scope,
        )
    if module == PATHWAY:
        if not data.get('group_field'):
            return infiltration_service.inspect_inputs(*args, **scope)
        from flask_app.services.pathway_artifacts import resolve_pathway_input
        source = resolve_pathway_input(data)
        data['go_gsea_path'] = source['path']
        return infiltration_service.inspect_pathway(*args,source['path'],data.get('comparison'), **scope)
    if module == PAIRED:
        from flask_app.services.infiltration_pairing import inspect_paired
        return inspect_paired(*args,subclass_columns=data.get('subclass_columns'),sample_pairs=data.get('sample_pairs'))
    if module == CONCORDANCE:
        return infiltration_service.inspect_concordance(*args, subclass_columns=data.get('subclass_columns'), **scope)
    return inspector_for(module)(*args, **scope)


def request_inputs(data):
    if not data.get('project_id'):
        raise ValidationError(message='请先选择项目。')
    assets=shared._request_registered_assets(data, input_types={"profile", "deconvolution"})
    profile=assets.get('profile_path')
    deconvolution=assets.get('deconvolution_path')
    if not profile or not deconvolution:
        raise ValidationError(message='请选择当前项目数据集的样本指标表和免疫浸润结果。')
    return profile,deconvolution


@bp.route('/immune-infiltration/inspect',methods=['POST'])
def inspect_infiltration(module=MODULE):
    try:
        data=request.get_json(silent=True) or {}
        profile,deconvolution=request_inputs(data)
        if data.get('group_field') or data.get('score_type') is not None:
            infiltration_service.validate_score_type(data.get('score_type'))
        result=inspect_request(module,profile,deconvolution,data, scope_only=shared._as_bool(data.get('sample_scope_only'), False))
        return jsonify(success=True,**(result[0] if isinstance(result,tuple) else result))
    except ValidationError as error:
        return jsonify(success=False,message=error.message),400


def infiltration_request(data, module):
    profile,deconvolution=request_inputs(data)
    group=data.get('group_field')
    if not isinstance(group,str) or not group:
        raise ValidationError(message='请选择分组字段。')
    score_type=infiltration_service.validate_score_type(data.get('score_type'))
    checked=inspect_request(module,profile,deconvolution,data)
    if not isinstance(checked, tuple):
        raise ValidationError(message='请先明确本次比较和有效样本范围。')
    checked_summary = checked[0]
    cells=data.get('cell_columns') or checked_summary['cell_columns']
    config = {'group_field':group,'cell_columns':cells,'score_type':score_type}
    if module != PAIRED:
        config.update(selected_infiltration_samples=checked_summary.get('scope_samples', checked_summary['selected_infiltration_samples']),
            selected_infiltration_groups=checked_summary['selected_infiltration_groups'])
    if module in {CONCORDANCE,PAIRED}:
        config['subclass_columns'] = checked_summary['selected_subclasses']
    if module == PAIRED:
        config['sample_pairs'] = checked_summary['sample_pairs']
    if module == PATHWAY:
        config.update(comparison=data['comparison'],upstream_artifact_id=data['upstream_artifact_id'])
    if module == SAMPLE_PATHWAY:
        config.update(comparison=data['comparison'])
        from flask_app.routes.api_script_hub._common import _transcriptome_path_from_request
        expression_path = _transcriptome_path_from_request(data, 'expression_path', 'transcriptome_path')
        if not expression_path:
            raise ValidationError(message='请选择当前项目数据集的转录组表达矩阵。')
    else:
        expression_path = None
    context=shared._build_script_cache_context(project_id=data['project_id'],module_name=module,
        input_paths=[{'asset_type':'profile','path':profile},{'asset_type':'deconvolution','path':deconvolution},*([{'asset_type':'go_bp_gsea','path':data['go_gsea_path']}] if module == PATHWAY else []),*([{'asset_type':'transcriptome','path':expression_path}] if module == SAMPLE_PATHWAY else [])],
        config_json=config)
    if module == PATHWAY:
        context['upstream_input'] = data['upstream_input']
    return profile, deconvolution, expression_path, cells, config, context


@bp.route('/immune-infiltration/run',methods=['POST'])
def run_infiltration(module=MODULE):
    try:
        data=request.get_json(silent=True) or {}
        profile, deconvolution, expression_path, cells, config, context = infiltration_request(data, module)
        group, score_type = config['group_field'], config['score_type']
        if not shared._force_rerun_requested(data):
            reused = shared._try_reuse_script_result(context, module)
            if reused:
                return jsonify(reused)
        task_id='script_task_'+uuid.uuid4().hex[:12]
        shared._set_task_state(task_id,status='queued',progress=0,stage='等待执行',detail='免疫浸润分析已提交',meta={'module':module},history=[],**context)
        try:
            shared._script_executor.submit(_run_infiltration_task,task_id,profile_path=profile,deconvolution_path=deconvolution,
                group_field=group,cell_columns=cells,score_type=score_type,module=module,subclass_columns=config.get("subclass_columns"),sample_pairs=config.get("sample_pairs"),go_gsea_path=data.get("go_gsea_path"),comparison=data.get("comparison"),expression_path=expression_path,selected_infiltration_samples=config.get("selected_infiltration_samples"),output_name=data.get("output_name"),results_root=shared._resolve_results_root(),app_context_app=current_app._get_current_object())
        except Exception:
            shared._set_task_state(task_id,status='failed',stage='提交失败',detail='任务未能进入执行队列，请稍后重试。')
            raise
        return jsonify(success=True,task_id=task_id,status_url=f'/api/script-hub/task/{task_id}')
    except ValidationError as error:
        return jsonify(success=False,message=error.message),400


def _run_infiltration_task(task_id,*,profile_path,deconvolution_path,group_field,cell_columns,results_root,app_context_app,score_type=None,module=MODULE,subclass_columns=None,sample_pairs=None,go_gsea_path=None,comparison=None,expression_path=None,selected_infiltration_samples=None,output_name=None):
    # The local executor, unlike RQ, does not supply an application context.
    with ExitStack() as stack:
        if not has_app_context():
            stack.enter_context(app_context_app.app_context())
        if not has_request_context():
            stack.enter_context(app_context_app.test_request_context('/api/script-hub/infiltration-worker'))
            from flask_app.models.database import User, db
            from flask_login import login_user
            job = shared.get_script_hub_job_service().get_job(task_id)
            if job and job.get('user_id'):
                owner = db.session.get(User, job['user_id'])
                if owner is None or not owner.is_active:
                    shared._set_task_state(task_id,status='failed',stage='账号不可用',detail='任务所属账号已停用。')
                    return
                login_user(owner)
            g.analysis_project_id = (job or {}).get('project_id')
        try:
            if module == PATHWAY:
                from flask_app.services.analysis_artifacts import revalidate_job_upstream
                revalidate_job_upstream(shared.get_script_hub_job_service().get_job(task_id))
            parent=script_output_parent(task_id,Path(results_root)/shared._RESULT_DIR,app_context_app)
            job_id,output,metadata=infiltration_service.generate_report(profile_path,deconvolution_path,group_field,cell_columns,parent,
                lambda value,stage,detail:shared._record_stage(task_id,value,stage,detail,{'module':module}),
                lambda:shared._script_task_cancel_requested(task_id),score_type=score_type,analysis_kind="sample_pathway" if module == SAMPLE_PATHWAY else "pathway" if module == PATHWAY else "paired" if module == PAIRED else "concordance" if module == CONCORDANCE else "consistency" if module == CONSISTENCY else "composition",subclass_columns=subclass_columns,sample_pairs=sample_pairs,go_gsea_path=go_gsea_path,comparison=comparison,expression_path=expression_path,selected_infiltration_samples=selected_infiltration_samples,output_name=output_name)
            result={'module':module,'job_id':job_id,'output_base':str(output),'metadata':metadata,
                'png_urls':[f'/api/script-hub/results/{job_id}/{path.relative_to(output).as_posix()}' for path in output.rglob('*.png')],
                'csv_urls':[f'/api/script-hub/results/{job_id}/{path.relative_to(output).as_posix()}' for path in output.rglob('*.csv')]}
            metadata['show_significance_filter'] = False
            shared._normalize_script_result(result,output,metadata,title='免疫浸润分析结果',subtitle=metadata['method'],dl_extras=[('csv_urls', None, '数据与统计表')],zip_name='infiltration_results.zip')
            shared._complete_script_task(task_id,module_name=module,stage='分析完成',detail='GO-BP 样本级相关分析已完成' if module == SAMPLE_PATHWAY else '通路方向比较已完成' if module == PATHWAY else '样本配对相关性已完成' if module == PAIRED else '组间方向比较已完成' if module == CONCORDANCE else '细胞相关性分析已完成' if module == CONSISTENCY else '组成与组间比较已完成',result=result,
                history=(shared._get_task_state(task_id) or {}).get('history',[]),app_context_app=app_context_app)
        except Exception as error:
            if shared._script_task_cancel_requested(task_id):
                raise shared.ScriptTaskCancelled()
            else:
                shared.logger.exception('免疫浸润分析失败')
                shared._set_task_state(task_id,status='failed',stage='分析失败',detail=str(error))


@bp.route('/immune-infiltration-consistency/inspect', methods=['POST'])
def inspect_consistency():
    return inspect_infiltration(CONSISTENCY)


@bp.route('/immune-infiltration-consistency/run', methods=['POST'])
def run_consistency():
    return run_infiltration(CONSISTENCY)


@bp.route('/immune-infiltration-concordance/inspect', methods=['POST'])
def inspect_concordance():
    return inspect_infiltration(CONCORDANCE)


@bp.route('/immune-infiltration-concordance/run', methods=['POST'])
def run_concordance():
    return run_infiltration(CONCORDANCE)


@bp.route('/immune-infiltration-paired/inspect', methods=['POST'])
def inspect_paired():
    return inspect_infiltration(PAIRED)


@bp.route('/immune-infiltration-paired/run', methods=['POST'])
def run_paired():
    return run_infiltration(PAIRED)


@bp.route('/immune-infiltration-pathway/sources', methods=['GET'])
def pathway_sources():
    from flask_app.services.pathway_artifacts import pathway_candidates
    from flask_app.services.upstream_source_catalog import source_view_options, source_management_view
    try:
        options = source_view_options(request.args)
        candidates = pathway_candidates(request.args.get('project_id', ''), request.args.get('asset_set', ''))
        return jsonify(source_management_view(candidates, **options) if options else {'success': True, 'candidates': candidates})
    except ValidationError as error:
        return jsonify(success=False, message=error.message), 400


@bp.route('/immune-infiltration-pathway/inspect', methods=['POST'])
def inspect_pathway():
    return inspect_infiltration(PATHWAY)


@bp.route('/immune-infiltration-pathway/run', methods=['POST'])
def run_pathway():
    return run_infiltration(PATHWAY)


@bp.route('/immune-infiltration-sample-pathway/inspect', methods=['POST'])
def inspect_sample_pathway():
    return inspect_infiltration(SAMPLE_PATHWAY)


@bp.route('/immune-infiltration-sample-pathway/run', methods=['POST'])
def run_sample_pathway():
    return run_infiltration(SAMPLE_PATHWAY)
