"""Bounded catalog queries, exact global statistics and current-account scope."""
from datetime import datetime
from unittest.mock import patch
import pytest
from sqlalchemy import event
from flask_app.models.database import Project, ProjectAsset, SampleRecord, User, db
from flask_app.routes import api_projects
from flask_app.tests.test_data_management_contracts import context


def test_more_than_200_projects_traverse_without_gaps_or_duplicates(context):
    app, _, original = context
    now = datetime(2026, 10, 5)
    for index in range(207):
        db.session.add(Project(id=f'catalog-{index:03}', name=f'研究{index:03}', created_at=now, updated_at=now))
    db.session.commit()
    client = app.test_client()
    pages = [client.get(f'/api/projects?page={page}&page_size=50&sort=created_desc').json for page in range(1, 6)]
    ids = [project['id'] for page in pages for project in page['projects']]
    assert len(ids) == len(set(ids)) == 208
    assert original.id in ids
    assert [len(page['projects']) for page in pages] == [50, 50, 50, 50, 8]
    assert all(page['pagination']['total'] == 208 for page in pages)
    repeated = client.get('/api/projects?page=2&page_size=50&sort=created_desc').json
    assert repeated == pages[1]


def test_server_search_status_sort_and_legacy_filters_are_composable(context):
    app, _, _ = context
    for identifier, name, institution, status in [
        ('q1', '课题_A%', '南华研究所', 'active'), ('q2', '课题BA其他', '北京', 'active'),
        ('q3', '免疫研究', '课题_A%机构', 'archived'), ('q4', '免疫二', '南华研究所', 'paused')]:
        db.session.add(Project(id=identifier, name=name, institution=institution, status=status, cooperation_level='internal'))
    db.session.commit()
    client = app.test_client()
    result = client.get('/api/projects', query_string={'q':'_A%', 'sort':'name_asc'}).json
    assert {row['id'] for row in result['projects']} == {'q1','q3'}
    active = client.get('/api/projects', query_string={'q':'课题', 'status':'active', 'institution':'南华', 'cooperation_level':'internal'}).json
    assert [row['id'] for row in active['projects']] == ['q1']
    ordered = client.get('/api/projects?q=免疫&sort=name_desc').json['projects']
    assert [row['name'] for row in ordered] == sorted([row['name'] for row in ordered], reverse=True)


def test_page_count_batching_projects_only_current_page_and_never_full_metadata(context):
    app, _, _ = context
    for index in range(35):
        identifier=f'bounded-{index:03}'
        db.session.add(Project(id=identifier,name=f'限量{index:03}'))
        db.session.add(ProjectAsset(project_id=identifier,asset_type='profile',original_name='输入.csv',storage_path='/synthetic/input',
            metadata_json={'asset_set':'甲','huge_unused_report':['unused']*100,'validation':{'summary':{'inputs':[{'samples':['001']}]}}}))
    db.session.commit()
    statements=[]
    def capture(connection,cursor,statement,parameters,context,many):
        if statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(db.engine,'before_cursor_execute',capture)
    try:
        with patch('flask_app.services.mongo_service.get_projects_results',return_value=[]) as mongo:
            response=app.test_client().get('/api/projects?q=限量&page=2&page_size=10&sort=name_asc')
            assert response.status_code==200
            data=response.json
            assert len(data['projects'])==10 and data['pagination']['total']==35
            assert all(row['input_sample_count']==1 for row in data['projects'])
            assert mongo.call_count==1 and set(mongo.call_args.args[0])=={row['id'] for row in data['projects']}
    finally:event.remove(db.engine,'before_cursor_execute',capture)
    assert len(statements)==7
    assert not any('project_asset.metadata_json AS' in statement for statement in statements)
    assert 'huge_unused_report' not in response.get_data(as_text=True)


def test_selector_skips_assets_samples_groups_and_result_queries(context):
    app,_,project=context
    with patch('flask_app.services.project_catalog_service._counts',side_effect=AssertionError('selector must not read counts')):
        response=app.test_client().get('/api/projects?view=selector&page_size=20')
    assert response.status_code==200
    assert response.json['projects'][0]['id']==project.id
    assert 'asset_counts' not in response.json['projects'][0]
    assert response.json['pagination']['total']==1


def test_statistics_are_independent_exact_and_preserve_result_identity(context):
    app,_,project=context
    other=Project(id='stats-other',name='另外研究',status='archived')
    db.session.add(other)
    for identifier,kind,dataset,samples,historical in [
        ('input-a','profile','甲',['001','001'],False),('input-b','pep','乙',['001'],False),
        ('input-history','profile','甲',['002'],True)]:
        db.session.add(ProjectAsset(id=identifier,project_id=project.id,asset_type=kind,original_name=identifier,
            storage_path='/synthetic/'+identifier,metadata_json={'asset_set':dataset,'superseded':historical,'validation':{'summary':{'inputs':[{'samples':samples}]}}}))
    for identifier,path in [('result-a','/synthetic/out/a'),('result-a-duplicate','/synthetic/out/a'),('result-b','/synthetic/out/b')]:
        db.session.add(ProjectAsset(id=identifier,project_id=project.id,asset_type='processed_result',original_name=identifier,
            storage_path=path,metadata_json={'job_id':'one-job','analysis_signature':'same'}))
    db.session.add(SampleRecord(project_id=project.id,sample_id='001',sample_name='001'))
    db.session.commit()
    docs=[{'_id':'mongo-copy','project_id':project.id,'job_id':'one-job','analysis_signature':'same','output_base':'/synthetic/out/a'},
          {'_id':'mongo-new','project_id':other.id,'job_id':'another-job','output_base':'/synthetic/out/c'}]
    with patch('flask_app.services.mongo_service.get_projects_results',side_effect=lambda ids,**kwargs:[doc for doc in docs if doc['project_id'] in ids]):
        client=app.test_client()
        stats=client.get('/api/projects/statistics?q=no-match&page=999').json
        page=client.get('/api/projects?page_size=1&status=archived').json
        assert page['pagination']['total']==1 and len(page['projects'])==1
        assert stats['project_count']==2 and stats['status_counts']=={'active':1,'archived':1}
        assert stats['result_count']==3 and stats['file_count']==5
        assert stats['pep_project_count']==1
        assert stats['input_sample_count']==2 and stats['dataset_count']==2 and stats['registered_sample_count']==1
        assert page['projects'][0]['result_count']==1
        assert client.get('/api/projects/statistics').json==stats


@pytest.mark.parametrize('role',['user','admin'])
def test_pages_selector_and_statistics_are_account_scoped(context,role):
    app,_,project=context
    user=User(username='catalog-owner',email='catalog-owner@example.invalid',password_hash='synthetic',role=role)
    other=User(username='catalog-foreign',email='catalog-foreign@example.invalid',password_hash='synthetic')
    db.session.add_all([user,other]);db.session.flush()
    project.user_id=user.id
    db.session.add(Project(name='不可见项目',user_id=other.id))
    db.session.commit();app.config['REQUIRE_LOGIN']=True
    client=app.test_client()
    with client.session_transaction() as session:session['_user_id']=str(user.id);session['_fresh']=True
    for view in ['summary','selector']:
        data=client.get('/api/projects',query_string={'view':view}).json
        assert data['pagination']['total']==1 and [row['id'] for row in data['projects']]==[project.id]
    assert client.get('/api/projects/statistics').json['project_count']==1


@pytest.mark.parametrize('parameter',['sort=unknown','view=unknown'])
def test_unknown_catalog_modes_return_chinese_error(context,parameter):
    app,_,_=context
    response=app.test_client().get('/api/projects?'+parameter)
    assert response.status_code==400 and '请选择有效' in response.json['message']


def test_empty_page_bounds_and_empty_statistics(context):
    app,_,project=context
    client=app.test_client()
    missing=client.get('/api/projects?q=no-match').json
    assert missing['projects']==[] and missing['pagination']['total']==0
    outside=client.get('/api/projects?page=999').json
    assert outside['projects']==[] and outside['pagination']['total']==1
    bound=client.get('/api/projects?page=-9&page_size=999&view=selector').json['pagination']
    assert bound['page']==1 and bound['page_size']==200
    db.session.delete(project);db.session.commit()
    assert client.get('/api/projects/statistics').json=={'project_count':0,'status_counts':{},'pep_project_count':0,'file_count':0,'result_count':0,
        'input_sample_count':0,'registered_sample_count':0,'dataset_count':0,'group_spec_count':0}
