import os
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

import pytest
from flask import Flask
from flask_app.exceptions import GroupSpecChangedError
from flask_app.models.database import Project, ProjectAsset, ProjectGroupSpec, db
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.tests.test_data_management_contracts import context

def test_revision_guard_retains_original_and_rejects_stale_edit(context):
    app, service, project = context
    client=app.test_client();url=f'/api/projects/{project.id}/group-specs'
    first=client.post(url,json={'name':'方案','spec_json':{'groups':['甲','乙'],'description':'保留'}})
    assert first.status_code==201
    scheme=first.json['group_specs'][0];old=first.json['asset'];old_bytes=Path(old['storage_path']).read_bytes()
    assert scheme['revision']==old['id']
    edit={'id':scheme['id'],'name':'重命名','spec_json':{'groups':['乙','甲']}}
    assert client.post(url,json=edit).status_code==400
    edit['expected_revision']=scheme['revision']
    result=client.post(url,json=edit)
    assert result.status_code==201
    assert result.json['group_specs'][0]['revision']==result.json['asset']['id']!=scheme['revision']
    assert result.json['group_specs'][0]['spec_json']['description']=='保留'
    current=result.json['asset']['id']
    conflict=client.post(url,json={**edit,'name':'另一人的编辑'})
    assert conflict.status_code==409 and conflict.json['error_code']=='GROUP_SPEC_CHANGED'
    assert ProjectGroupSpec.query.one().name=='重命名'
    assert ProjectAsset.query.count()==2
    assert Path(old['storage_path']).read_bytes()==old_bytes
    assert db.session.get(ProjectAsset,old['id']).metadata_json['superseded_by']==[current]
    assert client.get(url).json['group_specs'][0]['revision']==current

def test_same_definition_rename_still_changes_revision(context):
    app,_,project=context;client=app.test_client();url=f'/api/projects/{project.id}/group-specs'
    first=client.post(url,json={'name':'原名','spec_json':{'groups':['甲']}}).json
    scheme=first['group_specs'][0]
    result=client.post(url,json={'id':scheme['id'],'expected_revision':scheme['revision'],'name':'新名','spec_json':scheme['spec_json']}).json
    assert result['asset']['metadata']['content_version']==first['asset']['metadata']['content_version']
    assert result['group_specs'][0]['revision']!=scheme['revision']

def test_duplicate_create_and_deleted_edit_do_not_replace(context):
    app,service,project=context;client=app.test_client();url=f'/api/projects/{project.id}/group-specs'
    original=client.post(url,json={'name':'方案','spec_json':{'groups':['甲']}}).json['group_specs'][0]
    assert client.post(url,json={'name':'方案','spec_json':{'groups':['乙']}}).status_code==400
    assert ProjectGroupSpec.query.one().spec_json['groups']==['甲']
    assert client.delete(url+'/'+original['id']).status_code==200
    stale=client.post(url,json={'id':original['id'],'expected_revision':original['revision'],'name':'方案','spec_json':{'groups':['乙']}})
    assert stale.status_code==409 and not ProjectGroupSpec.query.count()

def test_legacy_scheme_without_asset_can_be_updated_once(context):
    app,_,project=context
    old=ProjectGroupSpec(project_id=project.id,name='旧方案',spec_json={'groups':['甲']});db.session.add(old);db.session.commit()
    url=f'/api/projects/{project.id}/group-specs';client=app.test_client()
    original=client.get(url).json['group_specs'][0]
    assert original['revision'].startswith('legacy:')
    result=client.post(url,json={'id':old.id,'expected_revision':original['revision'],'name':'旧方案','spec_json':{'groups':['乙']}})
    assert result.status_code==201 and not result.json['group_specs'][0]['revision'].startswith('legacy:')

@pytest.mark.skipif(not os.environ.get('TEST_UPLOAD_DATABASE_URI','').startswith('mysql'),reason='Requires actual MySQL locks')
def test_two_clients_publish_one_scheme_version(tmp_path):
    app=Flask(__name__);app.config.update(TESTING=True,REQUIRE_LOGIN=False,SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_DATABASE_URI=os.environ['TEST_UPLOAD_DATABASE_URI'],PROJECT_DATA_ROOT=str(tmp_path))
    db.init_app(app);service=ProjectAssetService(tmp_path/'projects')
    with app.app_context():
        db.create_all();project=Project(name='分组并发-'+uuid.uuid4().hex);db.session.add(project);db.session.commit();project_id=project.id
        old=service.save_group_spec_asset(project,name='原方案',spec_json={'groups':['甲','乙']})
        old_id=old.id;old_path=Path(old.storage_path);original_bytes=old_path.read_bytes();spec_id=old.metadata_json['spec_id']
    barrier=Barrier(2);lock=ProjectAssetService._lock_input_project
    def locked(identifier):
        barrier.wait(timeout=15);lock(identifier)
    def run(number):
        with app.app_context():
            try:
                asset=service.save_group_spec_asset(db.session.get(Project,project_id),name=f'编辑{number}',
                    spec_id=spec_id,expected_revision=old_id,require_expected_revision=True,spec_json={'groups':['乙','甲']})
                return ('saved',asset.id)
            except GroupSpecChangedError:
                return ('conflict',None)
    with patch.object(ProjectAssetService,'_lock_input_project',side_effect=locked):
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,range(2)))
    assert sorted(row[0] for row in results)==['conflict','saved']
    winner=next(row[1] for row in results if row[0]=='saved')
    with app.app_context():
        assets=ProjectAsset.query.filter_by(project_id=project_id).all()
        assert len(assets)==2 and old_path.read_bytes()==original_bytes
        assert db.session.get(ProjectAsset,old_id).metadata_json['superseded_by']==[winner]
        assert len(list(old_path.parent.glob('*.json')))==2
        assert sum(not row.metadata_json.get('superseded') for row in assets)==1
        for row in assets:db.session.delete(row)
        db.session.delete(db.session.get(ProjectGroupSpec,spec_id));db.session.delete(db.session.get(Project,project_id));db.session.commit()
