import io
import json
import os
import uuid
from pathlib import Path
from threading import Barrier
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import pytest
from flask import Flask
from flask_login import LoginManager
from werkzeug.datastructures import FileStorage
from flask_app.exceptions import UploadImpactChangedError
from flask_app.models.database import Project, ProjectAsset, db
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.tests.test_data_management_contracts import context, upload

def item(kind='profile',name='新版.csv',dataset='甲',directory=False):
    return dict(asset_type=kind,asset_set=dataset,name=name,directory=directory)

def submit(app,project,expected=None,operation=None):
    data={'asset_type':'profile','asset_set':'甲','replace_existing':'true',
          'files':(io.BytesIO(b'sample,value\n001,2\n'),'新版.csv')}
    if expected is not None: data['expected_versions']=json.dumps(expected)
    if operation: data['operation_id']=operation
    return app.test_client().post(f'/api/projects/{project.id}/assets',data=data)

def test_lightweight_preview_and_publication_scope(context):
    app,service,project=context
    old=upload(service,project);other=upload(service,project,'乙')
    alias=ProjectAsset(project_id=project.id,asset_type='datapoint',original_name='别名.csv',storage_path='/synthetic/alias.csv',
        metadata_json={'asset_set':'甲','content_version':'alias-version','unused':'x'*100000})
    db.session.add(alias);db.session.commit()
    response=app.test_client().post(f'/api/projects/{project.id}/upload-impact',json={'items':[item()]})
    impact=response.json['impacts'][0]
    assert impact['expected_versions']==[{'id':old.id,'content_version':old.metadata_json['content_version']}]
    assert impact['pagination']['total']==1
    assert 'unused' not in response.get_data(as_text=True)
    assert set(impact['assets'][0])=={'id','original_name','uploaded_at','content_version'}
    result=submit(app,project,impact['expected_versions'])
    assert result.status_code==201
    assert old.metadata_json['superseded'] is True
    assert not other.metadata_json.get('superseded') and not alias.metadata_json.get('superseded')

def test_exact_clone_name_and_directory_addition(context):
    _,service,project=context
    for name in ['001.csv','001.CSV','002.csv']:
        service.upload_assets(project,asset_type='pep',metadata={'asset_set':'甲'},
            file_storages=[FileStorage(stream=io.BytesIO(b'sample,CDR3\n001,CASS\n'),filename=name)])
    impact=service.upload_impact(project.id,[item('pep','001.csv'),item('pep','/data/pep',directory=True)])['impacts']
    assert [row['original_name'] for row in impact[0]['assets']]==['001.csv']
    assert impact[0]['pagination']['total']==1
    assert impact[1]['assets']==impact[1]['expected_versions']==[]

def test_pages_do_not_truncate_expected_version_set(context):
    _,service,project=context
    for index in range(41):
        db.session.add(ProjectAsset(project_id=project.id,asset_type='profile',original_name=f'{index}.csv',
            storage_path=f'/synthetic/{index}.csv',metadata_json={'asset_set':'甲','content_version':f'v-{index}'}))
    db.session.commit()
    first=service.upload_impact(project.id,[item()],page=1,page_size=20)['impacts'][0]
    last=service.upload_impact(project.id,[item()],page=3,page_size=20)['impacts'][0]
    assert len(first['assets'])==20 and len(last['assets'])==1
    assert first['pagination']['total']==41 and last['pagination']['total_pages']==3
    assert first['expected_versions']==last['expected_versions'] and len(first['expected_versions'])==41

@pytest.mark.parametrize('expected',[None,[],[{'id':'bad','content_version':'bad'}]])
def test_missing_or_stale_guard_preserves_old_bytes(context,expected):
    app,service,project=context;old=upload(service,project)
    response=submit(app,project,expected)
    assert response.status_code==(400 if expected is None else 409)
    if expected is not None: assert response.json['error_code']=='UPLOAD_IMPACT_CHANGED'
    assert service.list_assets(project.id)==[old]
    assert Path(old.storage_path).read_bytes()==b'sample,value\n001,1\n'

def test_empty_snapshot_detects_new_input(context):
    app,service,project=context
    expected=service.upload_impact(project.id,[item()])['impacts'][0]['expected_versions']
    assert expected==[]
    old=upload(service,project)
    assert submit(app,project,expected).status_code==409
    assert not old.metadata_json.get('superseded')

def test_version_change_in_same_asset_rejects(context):
    app,service,project=context;old=upload(service,project)
    expected=service.upload_impact(project.id,[item()])['impacts'][0]['expected_versions']
    old.metadata_json={**old.metadata_json,'content_version':'changed'};db.session.commit()
    assert submit(app,project,expected).status_code==409
    assert not old.metadata_json.get('superseded')

@pytest.mark.parametrize('expected', ['bad', [{'id':'a','content_version':'v'},{'id':'a','content_version':'v'}], [{'id':'a'}]])
def test_invalid_snapshot_is_rejected(context,expected):
    app,_,project=context
    assert submit(app,project,expected).status_code==400
    assert ProjectAsset.query.count()==0

@pytest.mark.skipif(not os.environ.get('TEST_UPLOAD_DATABASE_URI','').startswith('mysql'),reason='Requires real MySQL row locks')
def test_simultaneous_replacements_publish_only_confirmed_version(tmp_path):
    app=Flask(__name__)
    app.config.update(TESTING=True,REQUIRE_LOGIN=False,SECRET_KEY='synthetic-impact',SQLALCHEMY_DATABASE_URI=os.environ['TEST_UPLOAD_DATABASE_URI'],
        SQLALCHEMY_TRACK_MODIFICATIONS=False,PROJECT_DATA_ROOT=str(tmp_path),FILE_BROWSER_ROOT=str(tmp_path))
    db.init_app(app);LoginManager(app).user_loader(lambda _:None)
    service=ProjectAssetService(tmp_path/'projects')
    with app.app_context(),patch('flask_app.services.input_validation_cache.schedule_uploaded_validation'):
        db.create_all();project=Project(name='版本并发合成-'+uuid.uuid4().hex);db.session.add(project);db.session.commit()
        project_id=project.id;old=upload(service,project);old_id=old.id;old_path=old.storage_path
        expected=service.upload_impact(project.id,[item()])['impacts'][0]['expected_versions']
    barrier=Barrier(2)
    def validation(_):
        barrier.wait(timeout=15)
        return {'inputs':[{'status':'checked','samples':['001']}],'errors':[]}
    def run(_):
        operation=str(uuid.uuid4())
        with app.app_context():
            try:
                assets=service.upload_assets(db.session.get(Project,project_id),asset_type='profile',replace_existing=True,
                    expected_versions=expected,require_expected_versions=True,metadata={'asset_set':'甲'},operation_id=operation,
                    file_storages=[FileStorage(stream=io.BytesIO(b'sample,value\n001,2\n'),filename='新版.csv')])
                return ('saved',assets[0].id,operation)
            except UploadImpactChangedError:
                return ('conflict',None,operation)
    with patch('flask_app.services.input_validation_cache.schedule_uploaded_validation'),patch('flask_app.services.input_validation_cache.validate_uploaded_asset',side_effect=validation):
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(run,range(2)))
    assert sorted(row[0] for row in results)==['conflict','saved']
    winner=next(row for row in results if row[0]=='saved')
    with app.app_context(),patch('flask_app.services.input_validation_cache.schedule_uploaded_validation'):
        assets=ProjectAsset.query.filter_by(project_id=project_id).all()
        assert len(assets)==2
        assert db.session.get(ProjectAsset,old_id).metadata_json['superseded_by']==[winner[1]]
        assert Path(old_path).read_bytes()==b'sample,value\n001,1\n'
        assert len(list(Path(old_path).parents[2].rglob('*.csv')))==2
        replay=service.upload_assets(db.session.get(Project,project_id),asset_type='profile',replace_existing=True,
            expected_versions=expected,require_expected_versions=True,metadata={'asset_set':'甲'},operation_id=winner[2],
            file_storages=[FileStorage(stream=io.BytesIO(b'sample,value\n001,2\n'),filename='新版.csv')])
        assert replay[0].id==winner[1]
        for asset in assets: db.session.delete(asset)
        db.session.delete(db.session.get(Project,project_id));db.session.commit();db.session.remove()
