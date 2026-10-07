import json, os, uuid
from pathlib import Path
from unittest.mock import patch
import pytest
from flask import Flask
from flask_login import LoginManager
from flask_app.exceptions import AppException
from flask_app.models.database import db, Project, ProjectAsset, ProjectGroupSpec
from flask_app.routes import api_projects
from flask_app.services.group_spec_service import get_group_spec_service
from flask_app.services.project_asset_service import ProjectAssetService
from flask_app.services.project_service import ProjectService
from flask_app.tests.test_data_management_contracts import context

def scheme(project, name, dataset='', groups=None, **fields):
    item=ProjectGroupSpec(project_id=project.id,name=name,spec_json={
        'groups':groups or ['甲','乙'],**({'asset_set':dataset} if dataset else {}),**fields})
    db.session.add(item);db.session.flush();return item

def test_catalog_filters_before_pagination_and_keeps_project_wide(context):
    app,_,project=context
    for number in range(23):scheme(project,f'甲方案{number:02}','甲')
    scheme(project,'乙方案','乙');common=scheme(project,'通用方案')
    literal=scheme(project,'甲%_方案','甲');db.session.commit()
    url=f'/api/projects/{project.id}/group-specs'
    with patch.object(get_group_spec_service(),'list_specs',side_effect=AssertionError('must not read entire collection')):
        first=app.test_client().get(url,query_string={'view':'summary','asset_set':'甲','page':1,'page_size':20})
        second=app.test_client().get(url,query_string={'view':'summary','asset_set':'甲','page':2,'page_size':20})
        search=app.test_client().get(url,query_string={'view':'summary','asset_set':'甲','q':'%_'})
    assert first.status_code==second.status_code==search.status_code==200
    assert first.json['pagination']=={'page':1,'page_size':20,'total':25,'total_pages':2}
    assert len(first.json['items'])==20 and len(second.json['items'])==5
    items=first.json['items']+second.json['items']
    assert len({item['id'] for item in items})==25 and not any(item['name']=='乙方案' for item in items)
    assert next(item for item in items if item['id']==common.id)['project_wide'] is True
    assert [item['id'] for item in search.json['items']]==[literal.id]
    assert all('spec_json' not in item for item in items)

def test_preview_is_bounded_but_detail_preserves_full_objects(context):
    app,_,project=context
    groups=[{'name':f'组{i:04}','color':'#123456','note':'保留属性'} for i in range(1500)]
    item=scheme(project,'完整定义','甲',groups=groups,description='x'*100000);db.session.commit()
    client=app.test_client();url=f'/api/projects/{project.id}/group-specs'
    catalog=client.get(url,query_string={'view':'summary'}).json
    entry=catalog['items'][0]
    assert entry['group_count']==1500 and entry['group_preview']==[value['name'] for value in groups[:6]]
    assert len(json.dumps(catalog))<3000 and 'description' not in entry
    detail=client.get(url+'/'+item.id)
    assert detail.status_code==200 and detail.json['group_spec']['spec_json']['groups']==groups
    assert detail.json['group_spec']['spec_json']['description']=='x'*100000
    assert detail.json['group_spec']['revision']==entry['revision']
    assert len(client.get(url).json['group_specs'][0]['spec_json']['groups'])==1500

def test_summary_can_omit_definitions_and_post_can_return_only_saved_detail(context):
    app,_,project=context;client=app.test_client()
    with patch.object(get_group_spec_service(),'describe_specs',side_effect=AssertionError('summary must not read schemes')):
        response=client.get(f'/api/projects/{project.id}?summary_only=true&include_group_specs=false')
    assert response.status_code==200 and 'group_specs' not in response.json
    with patch.object(get_group_spec_service(),'list_specs',side_effect=AssertionError('save must not read other schemes')):
        saved=client.post(f'/api/projects/{project.id}/group-specs?view=detail',json={'name':'新方案','spec_json':{'groups':['乙','甲']}})
    assert saved.status_code==201 and set(saved.json)=={'group_spec'}
    assert saved.json['group_spec']['spec_json']['groups']==['乙','甲']
    assert saved.json['group_spec']['revision'] and ProjectAsset.query.count()==1
    assert 'group_specs' in client.get(f'/api/projects/{project.id}?summary_only=true').json

def test_missing_source_storage_is_an_item_reason_not_whole_list_failure(context):
    app,_,project=context
    source=ProjectAsset(project_id=project.id,asset_type='profile',original_name='缺失.csv',
        storage_path='/synthetic/unavailable-group-source.csv',metadata_json={'asset_set':'甲','validation':{'status':'valid'}})
    db.session.add(source);db.session.flush()
    item=scheme(project,'失效来源',source_asset_id=source.id,source_content_version='old')
    db.session.commit();client=app.test_client();url=f'/api/projects/{project.id}/group-specs'
    for response in [client.get(url),client.get(url,query_string={'view':'summary','asset_set':'甲'}),client.get(url+'/'+item.id)]:
        assert response.status_code==200
    full=client.get(url).json['group_specs'][0]
    assert not full['source']['available'] and '无法读取' in full['source']['reason']
    assert client.get(url,query_string={'view':'summary','asset_set':'乙'}).json['pagination']['total']==0

def test_source_projection_preserves_uri_fallback_and_prepared_matching(context,tmp_path):
    app,_,project=context
    file=tmp_path/'source.csv';file.write_text('sample,group\n001,A\n')
    prepared=tmp_path/'prepared.csv';prepared.write_text('sample,group\n001,A\n')
    source=ProjectAsset(project_id=project.id,asset_type='profile',original_name='历史来源.csv',
        storage_path=str(tmp_path/'missing.csv'),metadata_json={'dataset':' 甲 ','storage_uri':str(file),
        'validation':{'summary':{'huge':'x'*500000}}})
    db.session.add(source);db.session.flush()
    derived=ProjectAsset(project_id=project.id,asset_type='prepared_input',original_name='整理.csv',
        storage_path=str(tmp_path/'missing-prepared.csv'),metadata_json={'source_asset_id':source.id,'file_path':str(prepared)})
    db.session.add(derived);item=scheme(project,'绑定旧来源',source_asset_id=source.id);db.session.commit()
    service=get_group_spec_service()
    assert service.describe_specs(project.id)[0]['source']['available']
    match=service.describe_specs(project.id,profile_path=str(prepared),asset_set='甲')[0]
    assert match['source']['available'] and match['source']['asset_set']=='甲'
    assert not service.describe_specs(project.id,profile_path=str(tmp_path/'other.csv'))[0]['source']['available']
    identities=service.source_identities(ProjectAsset.query.filter_by(id=source.id))
    assert 'validation' not in identities[0].metadata_json
    assert len(json.dumps(identities[0].metadata_json))<1000

def test_exact_detail_refuses_other_project_and_invalid_view(context):
    app,_,project=context
    other=Project(name='其他项目');db.session.add(other);db.session.flush()
    item=scheme(other,'另一项目方案');db.session.commit()
    client=app.test_client();url=f'/api/projects/{project.id}/group-specs'
    assert client.get(url+'/'+item.id).status_code==400
    assert client.get(url,query_string={'view':'unknown'}).status_code==400
    assert client.get(url,query_string={'view':'summary','page':99}).json['items']==[]

@pytest.mark.skipif(not os.environ.get('TEST_UPLOAD_DATABASE_URI','').startswith('mysql'),reason='Requires actual MySQL JSON projection')
def test_mysql_catalog_json_count_and_object_preview(tmp_path,monkeypatch):
    app=Flask(__name__);app.config.update(TESTING=True,REQUIRE_LOGIN=False,SECRET_KEY='synthetic',
        SQLALCHEMY_TRACK_MODIFICATIONS=False,SQLALCHEMY_DATABASE_URI=os.environ['TEST_UPLOAD_DATABASE_URI'],
        PROJECT_DATA_ROOT=str(tmp_path),FILE_BROWSER_ROOT=str(tmp_path))
    db.init_app(app);login=LoginManager(app);login.user_loader(lambda value:None)
    monkeypatch.setattr(api_projects,'_project_service',lambda:ProjectService(tmp_path))
    app.register_blueprint(api_projects.project_api_bp)
    app.register_error_handler(AppException,lambda error:(error.to_dict(),error.http_status))
    with app.app_context():
        db.create_all();project=Project(name='目录投影-'+uuid.uuid4().hex);db.session.add(project);db.session.flush()
        try:
            groups=[{'name':f'组{i:04}','color':'red'} for i in range(1500)]
            target=scheme(project,'甲%_方案','甲',groups=groups,description='x'*100000)
            scheme(project,'乙方案','乙');scheme(project,'通用方案');db.session.commit()
            response=app.test_client().get(f'/api/projects/{project.id}/group-specs',query_string={'view':'summary','asset_set':'甲','q':'%_'})
            assert response.status_code==200
            assert response.json['pagination']['total']==1
            item=response.json['items'][0]
            assert item['id']==target.id and item['group_count']==1500
            assert item['group_preview']==[group['name'] for group in groups[:6]]
            assert len(json.dumps(response.json))<3000
        finally:
            db.session.rollback();db.session.delete(db.session.get(Project,project.id));db.session.commit()
