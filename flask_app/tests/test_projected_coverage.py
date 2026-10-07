"""Coverage paging and membership retain complete scoped sources using lightweight SQL."""
import re
from sqlalchemy import event
from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import ProjectAsset, db

def source(project,number,dataset='甲',historical=False):
    asset=ProjectAsset(project_id=project.id,asset_type='datapoint',original_name=f'来源{number}.csv',storage_path=f'/synthetic/{dataset}/{number}',
        metadata_json={'group_label':dataset,'superseded':historical,'unused_manifest':'x'*10000,
            'validation':{'status':'valid','key':{'validator':6},'summary':{'inputs':[{'samples':['001',f'S{number:04d}']}]}}})
    db.session.add(asset);return asset

def capture(statements):
    def handler(_connection,_cursor,statement,_parameters,_context,_many):
        if statement.lstrip().upper().startswith('SELECT') and 'FROM project_assets' in statement:
            statements.append(statement.split('FROM')[0])
    return handler

def test_covering_page_uses_all_sources_and_projected_columns(context):
    app,_,project=context
    for number in range(61):source(project,number)
    source(project,100,'乙');source(project,200,historical=True);db.session.commit()
    statements=[];listener=capture(statements);event.listen(db.engine,'before_cursor_execute',listener)
    try:
        data=app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲&page_size=2').json
    finally:event.remove(db.engine,'before_cursor_execute',listener)
    assert data['pagination']['total']==62
    row=next(item for item in data['samples'] if item['sample_id']=='001')
    assert len(row['coverage']['profile'])==61 and len(row['asset_ids'])==61
    assert row['needs_version_selection'] is True
    assert data['input_scopes']=={'甲':{'profile':{'asset_count':61,'unresolved_count':0}}}
    assert statements and all('storage_path' not in statement for statement in statements)
    assert all(not re.search(r',\s*project_assets\.metadata_json\s+(?:AS|,)',statement) for statement in statements)
    later=app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲&page=31&page_size=2').json
    assert later['pagination']['total']==62 and len(later['samples'])==2

def test_early_search_preserves_unidentified_scope_and_version_counts(context):
    app,_,project=context
    source(project,1);source(project,2)
    db.session.add(ProjectAsset(project_id=project.id,asset_type='transcriptome',original_name='尚未识别.csv',storage_path='/synthetic/pending',
        metadata_json={'asset_set':'甲','validation':{'status':'pending','summary':{'inputs':[{'samples':[]}]}}}))
    source(project,3,'乙');db.session.commit()
    data=app.test_client().get(f'/api/projects/{project.id}/input-samples?asset_set=甲&q=s0001&state=needs_attention').json
    assert [row['sample_id'] for row in data['samples']]==['S0001']
    assert data['samples'][0]['needs_version_selection'] is True
    assert data['input_scopes']['甲']['transcriptome']['unresolved_count']==1
    assert len(data['unresolved'])==1 and set(data['input_scopes'])=={'甲'}

def test_registration_membership_reads_identifiers_only_and_does_not_match_prefix(context):
    app,_,project=context
    source(project,1);source(project,2,'乙');db.session.commit()
    statements=[];listener=capture(statements);event.listen(db.engine,'before_cursor_execute',listener)
    try:
        response=app.test_client().get(f'/api/projects/{project.id}/samples/registration?asset_set=甲&sample_id=001')
    finally:event.remove(db.engine,'before_cursor_execute',listener)
    assert response.status_code==200 and response.json['sample'] is None
    assert statements and all('original_name' not in statement and 'storage_path' not in statement for statement in statements)
    rejected=app.test_client().get(f'/api/projects/{project.id}/samples/registration?asset_set=甲&sample_id=00')
    assert rejected.status_code==400
