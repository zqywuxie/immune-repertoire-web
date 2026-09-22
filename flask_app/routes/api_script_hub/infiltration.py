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


def request_inputs(data):
    if not data.get('project_id'):
        raise ValidationError(message='请先选择项目。')
    assets=shared._request_registered_assets(data)
    profile=assets.get('profile_path')
    deconvolution=assets.get('deconvolution_path')
    if not profile or not deconvolution:
        raise ValidationError(message='请选择当前项目数据集的样本指标表和免疫浸润结果。')
    return profile,deconvolution


@bp.route('/immune-infiltration/inspect',methods=['POST'])
def inspect_infiltration():
    try:
        data=request.get_json(silent=True) or {}
        profile,deconvolution=request_inputs(data)
        if data.get('group_field') or data.get('score_type') is not None:
            infiltration_service.validate_score_type(data.get('score_type'))
        result=infiltration_service.inspect_inputs(profile,deconvolution,data.get('group_field') or '',data.get('cell_columns'))
        return jsonify(success=True,**(result[0] if isinstance(result,tuple) else result))
    except ValidationError as error:
        return jsonify(success=False,message=error.message),400


@bp.route('/immune-infiltration/run',methods=['POST'])
def run_infiltration():
    try:
        data=request.get_json(silent=True) or {}
        profile,deconvolution=request_inputs(data)
        group=data.get('group_field')
        if not isinstance(group,str) or not group:
            raise ValidationError(message='请选择分组字段。')
        score_type=infiltration_service.validate_score_type(data.get('score_type'))
        checked=infiltration_service.inspect_inputs(profile,deconvolution,group,data.get('cell_columns'))
        cells=data.get('cell_columns') or checked[0]['cell_columns']
        context=shared._build_script_cache_context(project_id=data['project_id'],module_name=MODULE,
            input_paths=[{'asset_type':'profile','path':profile},{'asset_type':'deconvolution','path':deconvolution}],
            config_json={'group_field':group,'cell_columns':cells,'score_type':score_type})
        task_id='script_task_'+uuid.uuid4().hex[:12]
        shared._set_task_state(task_id,status='queued',progress=0,stage='等待执行',detail='免疫浸润分析已提交',meta={'module':MODULE},history=[],**context)
        try:
            shared._script_executor.submit(_run_infiltration_task,task_id,profile_path=profile,deconvolution_path=deconvolution,
                group_field=group,cell_columns=cells,score_type=score_type,results_root=shared._resolve_results_root(),app_context_app=current_app._get_current_object())
        except Exception:
            shared._set_task_state(task_id,status='failed',stage='提交失败',detail='任务未能进入执行队列，请稍后重试。')
            raise
        return jsonify(success=True,task_id=task_id,status_url=f'/api/script-hub/task/{task_id}')
    except ValidationError as error:
        return jsonify(success=False,message=error.message),400


def _run_infiltration_task(task_id,*,profile_path,deconvolution_path,group_field,cell_columns,results_root,app_context_app,score_type=None):
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
            parent=script_output_parent(task_id,Path(results_root)/shared._RESULT_DIR,app_context_app)
            job_id,output,metadata=infiltration_service.generate_report(profile_path,deconvolution_path,group_field,cell_columns,parent,
                lambda value,stage,detail:shared._record_stage(task_id,value,stage,detail,{'module':MODULE}),
                lambda:shared._script_task_cancel_requested(task_id),score_type=score_type)
            result={'module':MODULE,'job_id':job_id,'output_base':str(output),'metadata':metadata,
                'png_urls':[f'/api/script-hub/results/{job_id}/{path.relative_to(output).as_posix()}' for path in output.rglob('*.png')],
                'csv_urls':[f'/api/script-hub/results/{job_id}/{path.relative_to(output).as_posix()}' for path in output.rglob('*.csv')]}
            metadata['show_significance_filter'] = False
            shared._normalize_script_result(result,output,metadata,title='免疫浸润分析结果',subtitle=metadata['method'],dl_extras=[('csv_urls', None, '数据与统计表')],zip_name='infiltration_results.zip')
            shared._complete_script_task(task_id,module_name=MODULE,stage='分析完成',detail='组成与组间比较已完成',result=result,
                history=(shared._get_task_state(task_id) or {}).get('history',[]),app_context_app=app_context_app)
        except Exception as error:
            if shared._script_task_cancel_requested(task_id):
                shared._mark_script_task_cancelled(task_id)
            else:
                shared.logger.exception('免疫浸润分析失败')
                shared._set_task_state(task_id,status='failed',stage='分析失败',detail=str(error))
