import copy
from flask_app.tests.test_data_management_contracts import context,upload
from flask_app.models.database import AnalysisJob,ProjectGroupSpec,ProjectDataset,User,db
from flask_app.services.analysis_artifacts import capture_input_lineage


def test_saved_upload_version_and_group_identity_survive_catalog_changes(context):
    app,service,project=context
    asset=upload(service,project)
    refs=capture_input_lineage(project.id,[{'path':asset.storage_path,'asset_type':'profile'}],'甲')
    ref=refs['source_assets'][0]
    assert ref['content_version']==asset.metadata_json['content_version'] and ref['name']=='指标.csv'
    group=ProjectGroupSpec(project_id=project.id,name='合成分组',spec_json={'asset_set':'甲','source_asset_id':asset.id,'groups':['A','B']})
    job=AnalysisJob(id='saved-input-version',job_type='script_hub',module='profile',project_id=project.id,status='completed',payload={'input_assets':refs['source_assets'],**refs})
    db.session.add_all([group,job]);db.session.commit()
    before=copy.deepcopy(job.payload);group_before=copy.deepcopy(group.to_dict())
    response=app.test_client().put(f'/api/projects/{project.id}/datasets',json={'asset_set':'甲','expected_revision':0,'display_name':'改展示名','archived':True})
    assert response.status_code==200
    asset.original_name='登记显示已改变.csv'
    asset.metadata_json={**asset.metadata_json,'content_version':'current-registration-version'}
    db.session.commit();db.session.expire_all()
    assert db.session.get(AnalysisJob,job.id).payload==before
    assert db.session.get(ProjectGroupSpec,group.id).to_dict()==group_before
    assert before['input_assets'][0]['name']=='指标.csv'
    assert before['input_assets'][0]['content_version']!='current-registration-version'


def test_dataset_metadata_requires_current_project_ownership(context):
    app,service,project=context
    upload(service,project)
    owner=User(username='dataset-owner',email='dataset-owner@synthetic.test',password_hash='synthetic-no-login')
    other=User(username='dataset-other',email='dataset-other@synthetic.test',password_hash='synthetic-no-login')
    db.session.add_all([owner,other]);db.session.flush();project.user_id=owner.id;db.session.commit()
    client=app.test_client()
    with client.session_transaction() as session:
        session['_user_id']=str(other.id);session['_fresh']=True
    url=f'/api/projects/{project.id}/datasets'
    assert client.get(url).status_code==400
    assert client.put(url,json={'asset_set':'甲','expected_revision':0,'display_name':'越权名称'}).status_code==400
    assert ProjectDataset.query.count()==0
