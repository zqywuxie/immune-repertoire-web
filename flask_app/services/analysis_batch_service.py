"""Durable batch plans executed by the existing RQ worker."""
from contextvars import ContextVar
from flask import current_app
from flask_login import login_user
from flask_app.exceptions import ValidationError
from flask_app.models.database import db, User
from flask_app.services.background_job_service import get_background_job_service, TERMINAL_STATUSES

batch_child_context = ContextVar("batch_child_context", default=None)
SUPPORTED_MODULES = {"immune-infiltration-sample-pathway", "immune-infiltration-pathway", "immune-infiltration-paired", "immune-infiltration-concordance", "immune-infiltration-consistency", "immune-infiltration", "profile", "pep-analysis", "topclone", "pgen-analysis", "db-alignment", "boxplot", "umap", "umapin", "volcano", "go-kegg-enrichment", "ml-analysis", "mait-nkt", "charts"}


def validate_batch(data, *, preserve_group_snapshots=False):
    items = data.get("items")
    if not isinstance(items, list) or not 1 <= len(items) <= 20:
        raise ValidationError(message="请选择 1 至 20 项分析。")
    plan = []
    for index, item in enumerate(items):
        if not isinstance(item, dict) or item.get("module") not in SUPPORTED_MODULES or not isinstance(item.get("payload"), dict):
            raise ValidationError(message=f"第 {index + 1} 项分析模块或参数无效。")
        if item['payload'].get('group_spec_id') and not (preserve_group_snapshots and item['payload'].get('group_spec_snapshot')):
            from flask_app.services.group_spec_service import get_group_spec_service
            item = {**item, 'payload': get_group_spec_service().apply_to_payload(item['module'], item['payload'], str(data.get('project_id') or item['payload'].get('project_id') or ''))}
        dependencies = item.get("depends_on", [])
        if not isinstance(dependencies, list) or any(type(value) is not int or value < 0 or value >= index for value in dependencies):
            raise ValidationError(message=f"第 {index + 1} 项只能依赖排在前面的分析。")
        upstream = item.get("upstream_from")
        if upstream is not None:
            from flask_app.services.analysis_artifacts import downstream_spec
            valid_index = type(upstream) is int and 0 <= upstream < index
            producer = plan[upstream] if valid_index else {}
            pep_link = producer.get('module') == 'pep-analysis' and downstream_spec(item['module'], item['payload']) is not None
            deg_link = (producer.get('module') == 'volcano' and producer.get('payload', {}).get('input_mode') == 'expression'
                        and item['module'] == 'go-kegg-enrichment')
            if not valid_index or not (pep_link or deg_link):
                raise ValidationError(message=f"第 {index + 1} 项前置结果来源与分析类型不匹配。")
            dependencies = [*dependencies, upstream]
        plan.append({"upstream_from": upstream, "module": item["module"], "payload": item["payload"], "depends_on": sorted(set(dependencies)), "status": "queued", "job_id": "", "error": ""})
    return plan


def attach_batch_child(job_id):
    context = batch_child_context.get()
    if context is None:
        return
    parent_id, index = context
    service = get_background_job_service()
    child = service.get_job(job_id)
    service.upsert_job(job_id, {"parent_job_id": parent_id, "hidden_from_default_list": True})
    parent = service.get_job(parent_id)
    items = [dict(item) for item in parent["payload"]["items"]]
    items[index] = {**items[index], "job_id": job_id, "status": child["status"]}
    service.upsert_job(parent_id, {"items": items})


def dispatch_batch_item(parent, item):
    app = current_app._get_current_object()
    payload = {**item["payload"], "project_id": parent["project_id"], "asset_set": parent["payload"].get("asset_set", "")}
    if payload.get('group_spec_snapshot'):
        # Batch payload was resolved when submitted; editing the live scheme cannot change this child.
        payload.pop('group_spec_id', None)
    module = item["module"]
    path = "/api/jobs" if module == "charts" else "/api/script-hub/jobs"
    body = {"module": "charts.combined", "project_id": parent["project_id"], "payload": payload} if module == "charts" else {**payload, "module": module}
    with app.test_request_context(path, method="POST", json=body):
        if parent.get("user_id"):
            user = db.session.get(User, parent["user_id"])
            if user is None:
                raise ValidationError(message="任务所属用户不存在。")
            login_user(user)
        bind_batch_upstream(parent, item, payload)
        resolved_body = body if module == 'charts' else {**payload, "module": module}
        with app.test_request_context(path, method="POST", json=resolved_body):
            if parent.get("user_id"):
                login_user(user)
            response = app.full_dispatch_request()
        data = response.get_json(silent=True) or {}
        if response.status_code >= 400 or not data.get("success"):
            raise ValidationError(message=data.get("message") or "子任务提交失败。")
        # Inline children commit in a nested app context. End this session
        # snapshot so MySQL REPEATABLE READ can observe the completed child.
        db.session.commit()
        child_id = str(data.get("job_id") or data.get("task_id") or "")
        if child_id:
            child = get_background_job_service().get_job(child_id)
            if child and (child.get("parent_job_id") != parent["job_id"] or not child.get("hidden_from_default_list")):
                # Reused results return before ScriptExecutor.submit, which normally binds the child.
                attach_batch_child(child_id)
        return child_id


def run_batch_plan(job_id):
    service = get_background_job_service()
    parent = service.get_job(job_id)
    count = len(parent["payload"]["items"])
    for index in range(count):
        parent = service.get_job(job_id)
        if parent.get("cancel_requested") or parent["status"] == "cancelled":
            items = [dict(item) for item in parent["payload"]["items"]]
            for item in items[index:]:
                item.update(status="cancelled", error="批次已取消，未执行此项分析。")
            service.upsert_job(job_id, {"items": items, "result": {"items": items, "total_count": count, "completed_count": sum(item["status"] == "completed" for item in items)}})
            service.cancel_job(job_id, detail="当前分析已结束，剩余项目已取消。")
            return
        item = parent["payload"]["items"][index]
        if item["status"] in TERMINAL_STATUSES:
            continue
        blocked = [dependency for dependency in item.get("depends_on", []) if parent["payload"]["items"][dependency]["status"] != "completed"]
        if blocked:
            items = [dict(entry) for entry in parent["payload"]["items"]]
            items[index].update(status="failed", blocked_by=blocked, error="前置分析未成功完成，未执行此项：" + "、".join(str(value + 1) for value in blocked))
            service.upsert_job(job_id, {"items": items})
            continue
        service.update_progress(job_id, index * 100 / count, "执行批次", f"正在执行第 {index + 1}/{count} 项分析")
        token = batch_child_context.set((job_id, index))
        child_id = ""
        try:
            child_id = dispatch_batch_item(parent, item)
            child = service.get_job(child_id) if child_id else None
            if not child or child["status"] not in TERMINAL_STATUSES:
                raise RuntimeError("子任务未返回终态，批次无法确认计算结果。")
            outcome = {"job_id": child_id, "status": child["status"], "error": child.get("error") or ""}
        except Exception as error:
            outcome = {"status": "failed", "error": str(error)}
            if child_id:
                outcome["job_id"] = child_id
        finally:
            batch_child_context.reset(token)
        parent = service.get_job(job_id)
        items = [dict(item) for item in parent["payload"]["items"]]
        items[index].update(outcome)
        service.upsert_job(job_id, {"items": items})
    parent = service.get_job(job_id)
    items = parent["payload"]["items"]
    successful = sum(item["status"] == "completed" for item in items)
    result = {"items": items, "completed_count": successful, "total_count": count, "partial_success": 0 < successful < count}
    if parent.get("cancel_requested"):
        service.upsert_job(job_id, {"result": result})
        service.cancel_job(job_id)
    elif successful == count:
        service.complete_job(job_id, result, detail=f"全部 {count} 项分析已完成。")
    else:
        service.upsert_job(job_id, {"status": "failed", "result": result, "stage": "批次已结束", "detail": f"{successful}/{count} 项成功，其他项目请查看具体原因。"})


def settle_interrupted_batch_plan(parent_id):
    """End the saved plan only after its owning worker is confirmed terminal."""
    from flask_app.models.database import AnalysisJob
    parent = db.session.get(AnalysisJob, parent_id, populate_existing=True)
    if parent is None or parent.module != "analysis-batch" or parent.status not in {"failed", "interrupted"}:
        return
    previous = (parent.payload or {}).get("items", [])
    items = [dict(item) for item in previous]
    for item in items:
        if item.get("status") in TERMINAL_STATUSES:
            continue
        child_id = item.get("job_id")
        child = db.session.get(AnalysisJob, child_id, populate_existing=True) if child_id else None
        if child is not None and child.status in TERMINAL_STATUSES:
            item.update(status=child.status, error="" if child.status == "completed" else child.error or child.detail or "此项分析未完成。")
        else:
            item.update(status="interrupted", error=(
                "批次执行已终止，此项未完成。请从组合分析任务重新运行。"
                if child_id else "批次执行已终止，此项尚未执行。请从组合分析任务重新运行。"
            ))
    completed = sum(item.get("status") == "completed" for item in items)
    result = {**(parent.result or {}), "items":items, "total_count":len(items),
              "completed_count":completed, "partial_success":0 < completed < len(items)}
    if items != previous or result != parent.result:
        get_background_job_service().upsert_job(parent_id, {"items":items, "result":result})


def execute_batch(job_id):
    from flask_app.app import app
    from flask_app.services.persistent_queue import claim
    with app.app_context():
        if claim(job_id):
            run_batch_plan(job_id)


def bind_batch_upstream(parent, item, payload):
    """Bind exclusively to the selected preceding child, never an older project result."""
    source_index = item.get('upstream_from')
    if source_index is None:
        return
    from flask_app.services.analysis_artifacts import downstream_spec, scoped_pep_candidates
    source = parent['payload']['items'][source_index]
    if source['status'] != 'completed' or not source.get('job_id'):
        raise ValidationError(message='前置分析尚未生成可用结果。')
    if item['module'] == 'go-kegg-enrichment':
        from flask_app.services.differential_artifacts import differential_candidates
        candidates = [candidate for candidate in differential_candidates(parent['project_id'], parent['payload'].get('asset_set', ''))
                      if candidate['job_id'] == source['job_id'] and candidate['status'] == 'available']
        if len(candidates) != 1:
            raise ValidationError(message='本批次前置分析没有生成可用的完整差异表达结果。')
        payload.update(input_mode='deg', upstream_artifact_id=candidates[0]['id'], source_job_id=source['job_id'])
        for field in ('expression_path', 'transcriptome_path', 'deg_directory', 'upstream_input'):
            payload.pop(field, None)
        return
    spec = downstream_spec(item['module'], payload)
    if spec is None:
        raise ValidationError(message='当前分析模式不支持所选前置结果。')
    candidates = scoped_pep_candidates(parent['project_id'], parent['payload'].get('asset_set', ''), spec[0])
    candidates = [candidate for candidate in candidates
                  if candidate['job_id'] == source['job_id'] and candidate['status'] == 'available']
    for field, collection in (('chain', 'chains'), ('group_field', 'group_fields')):
        if payload.get(field):
            candidates = [candidate for candidate in candidates
                          if not candidate.get(collection) or payload[field] in candidate[collection]]
    if item['module'] == 'volcano':
        from pathlib import Path
        # Match the reference default (1VJusage) and the requested grouping;
        # ungrouped usage and 0VJusage are different scientific inputs.
        usage_type = str(payload.get('usage_type') or '1VJusage')
        if usage_type not in {'1VJusage', '0VJusage'}:
            raise ValidationError(message='V/J 使用类型必须为 1VJusage 或 0VJusage。')
        group_field = str(payload.get('group_field') or '')
        candidates = [candidate for candidate in candidates
            if Path(candidate['path']).name == usage_type
            and 'usage_cate' in Path(candidate['path']).parts
            and (not group_field or Path(candidate['path']).parent.parent.parent.name == group_field)]
    if item['module'] == 'umapin':
        from pathlib import Path
        # PEP emits the same combined table under two names plus its parent directory.
        # Bind the canonical grouped feature table, not one of its aliases.
        candidates = [candidate for candidate in candidates if Path(candidate['path']).name == 'df_VJ_all.csv']
    if item['module'] in {'ml-analysis', 'umap'} and len(candidates) > 1:
        from pathlib import Path
        # ML reads the combined table; its directory and other filenames are aliases.
        canonical = [candidate for candidate in candidates if Path(candidate['path']).name == 'df_VJ_all.csv']
        if len(canonical) == 1:
            candidates = canonical
    if item['module'] == 'mait-nkt' and len(candidates) > 1:
        from pathlib import Path
        # Category copies contain the same counts; group labels come from Profile.
        source_job = get_background_job_service().get_job(source['job_id']) or {}
        output_base = (source_job.get('result') or {}).get('output_base')
        canonical = [candidate for candidate in candidates
                     if output_base and Path(candidate['path']).resolve() == (Path(output_base) / 'Pep_shared' / 'TRA.csv').resolve()]
        if len(canonical) == 1:
            candidates = canonical
    if len(candidates) != 1:
        raise ValidationError(message='前置分析未生成唯一匹配结果，请核对链和分组设置。')
    payload.pop(spec[1], None)
    payload.pop('upstream_input', None)
    payload['upstream_artifact_id'] = candidates[0]['id']
    payload['source_job_id'] = source['job_id']

    if item['module'] == 'umapin' and (not payload.get('param_begin') or not payload.get('param_over')):
        from flask_app.routes.api_script_hub._common import _robust_read_csv
        columns = list(_robust_read_csv(candidates[0]['path'], nrows=0).columns)
        category = str(payload.get('category_col') or 'Category')
        if category not in columns or columns.index(category) == len(columns) - 1:
            raise ValidationError(message='前置结果缺少分组列之后的特征列。')
        if not payload.get('param_begin'): payload['param_begin'] = columns[columns.index(category) + 1]
        if not payload.get('param_over'): payload['param_over'] = columns[-1]
