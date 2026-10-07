from datetime import datetime,timedelta
from unittest.mock import patch
from flask_app.models.database import db,ProjectAsset
from flask_app.tests.test_data_management_contracts import context

def test_result_filters_apply_after_cross_source_dedup_and_keep_catalog_facets(context):
    app,_,project=context;now=datetime(2026,10,1)
    definitions=[('sql-a','job-1','profile',{'asset_set':'甲'}),('sql-b','job-2','profile',{'config_json':{'asset_set':'乙'}}),
                 ('sql-c','job-3','profile',{}),('sql-d','job-4','vj',{'group_label':'甲'})]
    for name,job,kind,scope in definitions:
        db.session.add(ProjectAsset(id=name,project_id=project.id,asset_type='processed_result',original_name=name,
            storage_path='/result/'+job,uploaded_at=now,metadata_json={'job_id':job,'analysis_type':kind,**scope}))
    db.session.commit()
    docs=[{'_id':'mongo-duplicate','project_id':project.id,'job_id':'job-1','analysis_type':'vj','asset_set':'乙','output_base':'/result/job-1','created_at':now+timedelta(days=1)},
          {'_id':'mongo-a','project_id':project.id,'job_id':'job-5','analysis_type':'profile','asset_set':'甲','output_base':'/result/job-5','created_at':now},
          {'_id':'mongo-b','project_id':project.id,'job_id':'job-6','analysis_type':'vj','metadata_json':{'dataset':'乙'},'output_base':'/result/job-6','created_at':now},
          {'_id':'mongo-c','project_id':project.id,'job_id':'job-7','analysis_type':'profile','input_assets':[{'asset_set':'甲'}],'output_base':'/result/job-7','created_at':now},
          {'_id':'mongo-d','project_id':project.id,'job_id':'job-8','analysis_type':'profile','metadata_json':{'config_json':{'asset_set':'乙'}},'output_base':'/result/job-8','created_at':now}]
    with patch('flask_app.services.mongo_service.get_project_results',return_value=docs):
        client=app.test_client();url=f'/api/projects/{project.id}/results'
        all_results=client.get(url).json
        a=client.get(url,query_string={'asset_set':'甲','page':2,'page_size':1}).json
        b=client.get(url,query_string={'asset_set':'乙','analysis_type':'profile'}).json
        unknown=client.get(url,query_string={'unscoped':'true'}).json
        task=client.get(url,query_string={'job_id':'job-6','asset_set':'乙','analysis_type':'vj'}).json
        prefix=client.get(url,query_string={'job_id':'job'}).json
        assert client.get(url,query_string={'asset_set':'甲','unscoped':'true'}).status_code==400
    assert all_results['pagination']['total']==8
    assert all_results['facets']=={'datasets':[{'name':'乙','count':3},{'name':'甲','count':3}],
        'analysis_types':[{'name':'profile','count':6},{'name':'vj','count':2}], 'unscoped_count':2}
    assert a['pagination']['total']==3 and len(a['results'])==1
    assert a['facets']==b['facets']==unknown['facets']==all_results['facets']
    assert {item['id'] for item in b['results']}=={'sql-b','mongo-d'}
    assert {item['id'] for item in unknown['results']}=={'sql-c','mongo-c'}
    assert [item['id'] for item in task['results']]==['mongo-b']
    assert task['results'][0]['metadata']['asset_set']=='乙'
    assert prefix['pagination']['total']==0
    assert 'mongo-duplicate' not in {item['id'] for item in all_results['results']}

def test_result_filters_never_guess_default_dataset_from_missing_scope(context):
    app,_,project=context
    db.session.add(ProjectAsset(project_id=project.id,asset_type='processed_result',original_name='旧结果',storage_path='/old',metadata_json={}))
    db.session.commit()
    with patch('flask_app.services.mongo_service.get_project_results',return_value=[]):
        url=f'/api/projects/{project.id}/results';client=app.test_client()
        assert client.get(url+'?asset_set=Set1').json['pagination']['total']==0
        assert client.get(url+'?unscoped=true').json['pagination']['total']==1
