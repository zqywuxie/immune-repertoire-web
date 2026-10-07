from datetime import datetime, timedelta
from unittest.mock import patch

from flask_app.models.database import db, ProjectAsset
from flask_app.services.project_result_catalog import _mongo_result_to_asset
from flask_app.services.mongo_service import get_project_results as actual_get_project_results
from flask_app.tests.test_data_management_contracts import context

def test_catalog_reads_only_page_models_and_keeps_full_saved_payload(context):
    app,_,project=context;pid=project.id;now=datetime(2026,10,1)
    for i in range(12):
        db.session.add(ProjectAsset(id=f'sql-{i:02d}',project_id=pid,asset_type='processed_result',
            original_name=f'结果{i}',storage_path=f'/result/{i}',uploaded_at=now+timedelta(seconds=i),
            metadata_json={'job_id':f'job-{i}','analysis_type':'profile','report':'x'*10000}))
    db.session.commit()
    docs=[{'_id':f'mongo-{i:02d}','project_id':pid,'job_id':f'job-{i}','analysis_type':'profile',
           'output_base':f'/result/{i}','created_at':now+timedelta(seconds=i),
           'input_assets':[{'asset_id':'old-input'}], 'config_json':{'group_spec_snapshot':{'groups':['B','A']}}} for i in range(6,18)]
    calls=[]
    def read(project_id, analysis_type=None, *, projection=None, identifiers=None):
        assert project_id==pid;calls.append((projection,identifiers))
        selected=[doc for doc in docs if identifiers is None or doc['_id'] in identifiers]
        return [{key:value for key,value in doc.items() if key=='_id' or key in projection} for doc in selected] if projection else selected
    original=ProjectAsset.to_dict;serialized=[]
    def serialize(asset): serialized.append(asset.id);return original(asset)
    with patch('flask_app.services.mongo_service.get_project_results',side_effect=read),patch.object(ProjectAsset,'to_dict',serialize):
        first=app.test_client().get(f'/api/projects/{pid}/results?page=1&page_size=4').json
        second=app.test_client().get(f'/api/projects/{pid}/results?page=2&page_size=4').json
        beyond=app.test_client().get(f'/api/projects/{pid}/results?page=8&page_size=4').json
    assert first['pagination']['total']==second['pagination']['total']==18
    assert [item['id'] for item in first['results']]==['mongo-17','mongo-16','mongo-15','mongo-14']
    assert [item['id'] for item in second['results']]==['mongo-13','mongo-12','sql-11','sql-10']
    assert serialized==['sql-10','sql-11'] or serialized==['sql-11','sql-10']
    assert first['results'][0]['metadata']['input_assets']==[{'asset_id':'old-input'}]
    assert first['results'][0]['metadata']['config_json']['group_spec_snapshot']['groups']==['B','A']
    assert second['results'][2]['metadata']['report']=='x'*10000
    assert not beyond['results']
    assert len(calls)==5 and calls[-1][1] is None
    assert all('metadata_json' not in projection and 'input_assets' not in projection for projection,ids in calls if projection)
    assert [len(ids) for projection,ids in calls if ids is not None]==[4,2]

def test_duplicate_canonical_choice_is_stable_and_preserves_sql_precedence(context):
    app,_,project=context;now=datetime(2026,10,1)
    for name in ['sql-a','sql-b']:
        db.session.add(ProjectAsset(id=name,project_id=project.id,asset_type='processed_result',original_name=name,
            storage_path='/same',uploaded_at=now,metadata_json={'job_id':'job'}))
    db.session.commit()
    docs=[{'_id':name,'project_id':project.id,'job_id':job,'output_base':path,'created_at':now} for name,job,path in
          [('mongo-z','job','/same'),('mongo-a','other','/other'),('mongo-b','other','/other')]]
    with patch('flask_app.services.mongo_service.get_project_results',return_value=docs):
        result=app.test_client().get(f'/api/projects/{project.id}/results').json
        assets=app.test_client().get(f'/api/projects/{project.id}/assets?asset_type=processed_result').json
    assert result['pagination']['total']==assets['pagination']['total']==2
    assert {item['id'] for item in result['results']}=={'sql-b','mongo-b'}
    assert result['results']==assets['assets']

def test_mongo_failure_does_not_report_partial_or_empty_success(context):
    app,_,project=context
    with patch('flask_app.services.mongo_service.get_project_results',side_effect=RuntimeError('synthetic unavailable')):
        response=app.test_client().get(f'/api/projects/{project.id}/results')
    assert response.status_code==500 and '暂时无法完整读取' in response.json['message']
    assert 'results' not in response.json

def test_mongo_hydration_limits_ids_inside_project_and_type(monkeypatch):
    from flask_app.services import mongo_service
    seen={}
    class Cursor:
        def sort(self,*args):return self
        def __iter__(self):return iter([])
    class Collection:
        def find(self,query,projection):seen.update(query=query,projection=projection);return Cursor()
    monkeypatch.setattr(mongo_service,'results_col',lambda:Collection())
    monkeypatch.setattr(mongo_service,'ensure_result_indexes',lambda:None)
    assert actual_get_project_results('owned','profile',identifiers=['one','two'])==[]
    assert seen['query']['project_id']=='owned' and seen['query']['_id']=={'$in':['one','two']}
    assert seen['query']['$or'][1]['metadata_json.analysis_type']=='profile'

def test_legacy_mongo_saved_input_fallback_preserves_explicit_empty():
    doc={'_id':'old','metadata_json':{'input_assets':[{'asset_id':'version-one'}], 'config_json':{'group_spec_snapshot':{'groups':['B','A']}}}}
    payload=_mongo_result_to_asset(doc)['metadata']
    assert payload['input_assets'][0]['asset_id']=='version-one'
    assert payload['config_json']['group_spec_snapshot']['groups']==['B','A']
    assert _mongo_result_to_asset({**doc,'input_assets':[]})['metadata']['input_assets']==[]

def test_selected_table_preview_never_walks_directory_and_keeps_path_guards(context,tmp_path):
    app,_,project=context
    root=tmp_path/'inputs';root.mkdir();(root/'one.csv').write_text('sample,value\n001,1\n')
    outside=tmp_path/'outside.csv';outside.write_text('secret\nhidden\n');(root/'link.csv').symlink_to(outside)
    asset=ProjectAsset(project_id=project.id,asset_type='pep',original_name='目录',storage_path=str(root));db.session.add(asset);db.session.commit()
    endpoint=f'/api/projects/{project.id}/assets/{asset.id}/table-preview'
    with patch('flask_app.services.directory_table_catalog.directory_table_names',side_effect=AssertionError('selected file must not enumerate')):
        response=app.test_client().get(endpoint,query_string={'file':'one.csv','include_files':'false'})
        assert response.status_code==200 and response.json['rows']==[['001','1']] and response.json['files']==[]
        for name in ['../outside.csv','link.csv','/etc/passwd']:
            assert app.test_client().get(endpoint,query_string={'file':name,'include_files':'false'}).status_code==400
