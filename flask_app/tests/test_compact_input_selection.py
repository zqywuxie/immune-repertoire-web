"""Complete default input selection without project-wide heavy metadata retrieval."""
import json
from unittest.mock import patch
from sqlalchemy import event
from flask_app.models.database import Project, ProjectAsset, db
from flask_app.tests.test_data_management_contracts import context

def asset(project, identifier, kind='pep', dataset='甲', history=False):
    return ProjectAsset(id=identifier, project_id=project.id, asset_type=kind,
        original_name=f'{identifier}.csv', storage_path=f'/synthetic/{identifier}.csv', size=7,
        metadata_json={'data_set':dataset,'superseded':history,'content_version':f'version-{identifier}',
                       'validation':{'status':'valid','summary':{'inputs':[{'samples':['001']*300,'columns':['very-long-cached-column']*300}]}},
                       'upload_operation':{'manifest':{'files':['unneeded-file']*300}}})

def test_compact_selection_keeps_all_clones_and_omits_heavy_reports(context):
    app, service, project=context
    other=Project(name='其他项目');db.session.add(other);db.session.flush()
    db.session.add_all([asset(project,f'clone-{n:03d}') for n in range(251)]+[
        asset(project,'profile','datapoint'),asset(project,'immune','cibersort'),asset(project,'rna','transcriptome'),
        asset(project,'old',history=True),asset(project,'other-set',dataset='乙'),asset(other,'foreign')])
    db.session.commit()
    statements=[]
    def record(_conn,_cursor,statement,_params,_ctx,_executemany):statements.append(statement)
    event.listen(db.engine,'before_cursor_execute',record)
    try:result=service.input_selection(project.id,'甲')
    finally:event.remove(db.engine,'before_cursor_execute',record)
    assert result['totals']=={'pep':251,'profile':1,'transcriptome':1,'deconvolution':1}
    assert len(result['assets'])==254 and len({row['id'] for row in result['assets']})==254
    assert {'old','other-set','foreign'}.isdisjoint({row['id'] for row in result['assets']})
    assert all(row['metadata']['asset_set']=='甲' for row in result['assets'])
    assert all(row['metadata']['validation']=={'status':'valid'} for row in result['assets'])
    assert 'samples' not in json.dumps(result) and 'upload_operation' not in json.dumps(result)
    assert len(json.dumps(result).encode()) < 150000
    assert len([statement for statement in statements if "FROM project_assets" in statement])==5
    assert not any('project_assets.metadata_json AS project_assets_metadata_json' in statement for statement in statements)

def test_scalar_candidates_are_bounded_and_remaining_versions_use_existing_paged_browser(context):
    app,service,project=context
    db.session.add_all([asset(project,f'profile-{n:03d}','profile') for n in range(55)])
    db.session.commit()
    result=app.test_client().get(f'/api/projects/{project.id}/input-selection',query_string={'asset_set':'甲'})
    assert result.status_code==200,result.json
    assert len(result.json['assets'])==50 and result.json['totals']['profile']==55
    assert result.json['truncated_kinds']==['profile']
    page=app.test_client().get(f'/api/projects/{project.id}/assets',query_string={'asset_set':'甲','asset_type':'profile','inputs_only':'true','page':2,'page_size':50})
    assert page.status_code==200 and len(page.json['assets'])==5
    assert {row['id'] for row in result.json['assets']}.isdisjoint({row['id'] for row in page.json['assets']})

def test_scope_required_empty_dataset_does_not_fall_back_to_all_inputs(context):
    app,service,project=context
    db.session.add(asset(project,'a'));db.session.commit();client=app.test_client()
    assert client.get(f'/api/projects/{project.id}/input-selection').status_code==400
    missing=client.get(f'/api/projects/{project.id}/input-selection',query_string={'asset_set':'缺失'})
    assert missing.status_code==200 and missing.json['assets']==[] and sum(missing.json['totals'].values())==0

def test_selection_refresh_preserves_validation_job_synchronization(context):
    app,service,project=context
    with patch('flask_app.services.input_validation_cache.synchronize_validation_jobs') as sync:
        result=app.test_client().get(f'/api/projects/{project.id}/input-selection',query_string={'asset_set':'甲'})
    assert result.status_code==200
    sync.assert_called_once_with(project.id)

def test_selection_checks_project_ownership(context):
    app,service,project=context
    app.config['REQUIRE_LOGIN']=True
    result=app.test_client().get(f'/api/projects/{project.id}/input-selection',query_string={'asset_set':'甲'})
    assert result.status_code == 400
    assert "assets" not in result.json
