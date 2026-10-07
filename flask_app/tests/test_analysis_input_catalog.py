"""Input catalog identity and resolved schema against synthetic real CSV assets."""
from pathlib import Path
import pytest
from flask_app.models.database import File, Project, ProjectAsset, db
from flask_app.tests.test_data_management_contracts import context

@pytest.fixture
def catalog(context):
    app, service, project = context
    from flask_app.routes.api.files import bp
    from flask_app.routes.api_analysis import analysis_bp
    app.register_blueprint(bp, url_prefix="/api")
    app.register_blueprint(analysis_bp)
    return app.test_client(), project

def input_asset(project,tmp_path,*,identifier='current',dataset='甲',historical=False,kind='profile'):
    path=tmp_path/f'{identifier}.csv'
    path.write_text('sample,group,metric\n001,A,1\n002,B,2\n',encoding='utf-8')
    item=ProjectAsset(id=identifier,project_id=project.id,asset_type=kind,original_name='同名.csv',storage_path=str(path),size=path.stat().st_size,
        metadata_json={'asset_set':dataset,'superseded':historical,'validation':{'status':'valid','summary':{'inputs':[{'kind':'profile','columns':['cached_old_header'],'sample_count':2}]}}})
    db.session.add(item);db.session.flush();return item

def legacy_file(project,identifier='legacy',path='/unused.csv'):
    item=File(id=identifier,name='legacy.csv',original_name='legacy.csv',size=4,mime_type='text/csv',columns=['stale'],row_count=9,storage_path=path,project=project.id)
    db.session.add(item);db.session.flush();return item

def test_catalog_limits_dataset_excludes_cached_history_and_returns_asset_identity(catalog,tmp_path):
    client,p=catalog
    current=input_asset(p,tmp_path)
    old=input_asset(p,tmp_path,identifier='old',historical=True)
    input_asset(p,tmp_path,identifier='other-set',dataset='乙')
    legacy_file(p,old.id,old.storage_path);legacy_file(p,current.id,current.storage_path);legacy_file(p)
    db.session.commit()
    response=client.get('/api/files',query_string={'project':p.id,'asset_set':'甲'})
    assert response.status_code==200,response.json
    assert [row['id'] for row in response.json['files']]==[current.id]
    assert response.json['files'][0]['asset_id']==current.id
    assert response.json['files'][0]['asset_set']=='甲'
    history=client.get('/api/files',query_string={'project':p.id,'asset_set':'甲','include_superseded':'true'})
    assert {row['id'] for row in history.json['files']}=={old.id,current.id}
    wide=client.get('/api/files',query_string={'project':p.id})
    assert {row['id'] for row in wide.json['files']}=={'current','other-set','legacy'}
    assert client.get('/api/files',query_string={'asset_set':'甲'}).status_code==400

def test_readonly_descriptor_reads_selected_history_not_cached_header(catalog,tmp_path):
    client,p=catalog
    old=input_asset(p,tmp_path,identifier='old',historical=True);input_asset(p,tmp_path);db.session.commit()
    result=client.get(f'/api/analysis/input-files/{old.id}',query_string={'project_id':p.id,'asset_set':'甲'})
    assert result.status_code==200,result.json
    assert result.json['id']==old.id
    assert result.json['columns']==['sample','group','metric']
    assert result.json['row_count']==2
    assert 'path' not in result.json
    assert File.query.count()==0
    assert db.session.get(ProjectAsset,old.id).metadata_json['superseded'] is True

def test_descriptor_and_execution_adapter_use_prepared_columns_and_path(catalog,tmp_path):
    client,p=catalog
    source=input_asset(p,tmp_path,identifier='old',historical=True)
    prepared_path=tmp_path/'prepared.csv';prepared_path.write_text('sample,mapped_metric\n001,10\n002,20\n',encoding='utf-8')
    prepared=ProjectAsset(id='prepared',project_id=p.id,asset_type='prepared_input',original_name='prepared.csv',storage_path=str(prepared_path),size=prepared_path.stat().st_size,metadata_json={})
    db.session.add(prepared);db.session.flush()
    raw_stat=Path(source.storage_path).stat();mapped_stat=prepared_path.stat()
    source.metadata_json={**source.metadata_json,'input_preparation':{'prepared_asset_id':prepared.id,'source_size':raw_stat.st_size,'source_mtime_ns':raw_stat.st_mtime_ns,'prepared_size':mapped_stat.st_size,'prepared_mtime_ns':mapped_stat.st_mtime_ns}}
    stale=legacy_file(p,source.id);db.session.commit()
    descriptor=client.get(f'/api/analysis/input-files/{source.id}',query_string={'project_id':p.id,'asset_set':'甲'})
    assert descriptor.status_code==200,descriptor.json
    assert descriptor.json['columns']==['sample','mapped_metric']
    assert db.session.get(File,source.id).columns==['stale']
    from flask_app.routes.api_analysis import _get_owned_file
    with client.application.test_request_context('/api/analysis/execute-unified',json={'project_id':p.id,'asset_set':'甲'}):
        resolved=_get_owned_file(source.id)
    assert resolved.storage_path==str(prepared_path)
    assert resolved.columns==descriptor.json['columns']
    assert resolved.row_count==2

@pytest.mark.parametrize('scope',[{'asset_set':'乙'},{'project_id':'other-project'}])
def test_descriptor_rejects_wrong_scope(catalog,tmp_path,scope):
    client,p=catalog
    source=input_asset(p,tmp_path);db.session.commit()
    result=client.get(f'/api/analysis/input-files/{source.id}',query_string=scope)
    assert result.status_code==400,result.json
    assert File.query.count()==0

def test_descriptor_rejects_nonprofile_and_missing_bytes(catalog,tmp_path):
    client,p=catalog
    expression=input_asset(p,tmp_path,identifier='expression',kind='transcriptome')
    missing=input_asset(p,tmp_path,identifier='missing');db.session.commit()
    assert client.get(f'/api/analysis/input-files/{expression.id}').status_code==400
    Path(missing.storage_path).unlink()
    response=client.get(f'/api/analysis/input-files/{missing.id}')
    assert response.status_code==404,response.json
    assert File.query.count()==0

def test_adapter_creates_profile_file_without_legacy_mime(catalog,tmp_path):
    client,p=catalog
    source=input_asset(p,tmp_path);db.session.commit()
    from flask_app.routes.api_analysis import _get_owned_file
    with client.application.test_request_context('/api/analysis/execute-unified',json={'project_id':p.id,'asset_set':'甲'}):
        resolved=_get_owned_file(source.id)
    assert resolved.mime_type=='text/csv'
    assert resolved.storage_path==source.storage_path
    assert resolved.columns==['sample','group','metric']
