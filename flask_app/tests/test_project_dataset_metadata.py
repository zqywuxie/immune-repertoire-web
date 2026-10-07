import copy
import pytest
from flask_app.tests.test_data_management_contracts import context, upload
from flask_app.models.database import AnalysisJob, ProjectAsset, ProjectDataset, SampleRecord, db


def test_display_rename_archive_restore_preserves_scope_and_history(context):
    app, service, project = context
    asset = upload(service,project,dataset='甲')
    sample = SampleRecord(project_id=project.id,sample_id='001',sample_name='001',extra_metadata={'asset_set':'甲'})
    job = AnalysisJob(id='saved-result',job_type='script_hub',module='profile',project_id=project.id,status='completed',
        payload={'asset_set':'甲','input_assets':[{'asset_id':asset.id,'content_version':asset.metadata_json['content_version']}]},
        result={'metadata':{'sample_count':1},'snapshot_scope':'甲'})
    db.session.add_all([sample,job]);db.session.commit()
    before=(copy.deepcopy(asset.to_dict()),copy.deepcopy(sample.to_dict()),copy.deepcopy(job.to_dict()))
    raw=__import__('pathlib').Path(asset.storage_path).read_bytes()
    client=app.test_client()
    assert client.get(f'/api/projects/{project.id}/datasets').json['datasets'][0]['name']=='甲'
    response=client.put(f'/api/projects/{project.id}/datasets',json={'asset_set':'甲','expected_revision':0,
        'display_name':'病例队列','description':'采集说明','source':'合作医院','batch':'批次01','archived':True})
    assert response.status_code==200,response.json
    saved=response.json['dataset'];assert saved['name']=='甲' and saved['display_name']=='病例队列'
    assert saved['revision']==1 and saved['archived'] is True
    summary=client.get(f'/api/projects/{project.id}/datasets').json['datasets'][0]
    assert summary['id']==saved['id'] and summary['input_count']==1 and summary['archived'] is True
    db.session.expire_all()
    assert db.session.get(ProjectAsset,asset.id).to_dict()==before[0]
    assert db.session.get(SampleRecord,sample.id).to_dict()==before[1]
    assert db.session.get(AnalysisJob,job.id).to_dict()==before[2]
    assert __import__('pathlib').Path(asset.storage_path).read_bytes()==raw
    restore=client.put(f'/api/projects/{project.id}/datasets',json={'asset_set':'甲','expected_revision':1,'archived':False})
    assert restore.status_code==200 and restore.json['dataset']['id']==saved['id']
    assert restore.json['dataset']['source']=='合作医院' and restore.json['dataset']['revision']==2


def test_dataset_description_conflict_is_atomic_and_project_scoped(context):
    app,service,project=context
    upload(service,project,dataset='甲');upload(service,project,dataset='乙')
    client=app.test_client();url=f'/api/projects/{project.id}/datasets'
    first=client.put(url,json={'asset_set':'甲','expected_revision':0,'display_name':'先保存'})
    assert first.status_code==200
    conflict=client.put(url,json={'asset_set':'甲','expected_revision':0,'display_name':'后保存','source':'不应部分写入'})
    assert conflict.status_code==409 and conflict.json['error_code']=='DATASET_RECORD_CHANGED'
    assert conflict.json['details']['dataset']['display_name']=='先保存'
    row=ProjectDataset.query.filter_by(project_id=project.id,scope='甲').one()
    assert row.source=='' and row.display_name=='先保存'
    separate=client.put(url,json={'asset_set':'乙','expected_revision':0,'display_name':'先保存'})
    assert separate.status_code==200 and separate.json['dataset']['id']!=first.json['dataset']['id']


@pytest.mark.parametrize('fields',[{'display_name':''},{'archived':'true'},{'expected_revision':True},
    {'description':'字'*4001},{'scope':'改关联'},{'asset_set':'不存在'}])
def test_invalid_dataset_fields_do_not_mutate_metadata(context,fields):
    app,service,project=context;upload(service,project,dataset='甲')
    response=app.test_client().put(f'/api/projects/{project.id}/datasets',json={'asset_set':'甲','expected_revision':0,**fields})
    assert response.status_code==400,response.json
    assert ProjectDataset.query.count()==0
