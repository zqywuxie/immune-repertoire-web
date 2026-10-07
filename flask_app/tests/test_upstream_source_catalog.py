"""Management paging preserves real source identity and strict availability."""
import pytest
from flask_app.tests.test_analysis_artifacts import artifacts
from flask_app.models.database import db, AnalysisJob
from flask_app.exceptions import AppException


def setup_client(artifacts):
    app, raw, folder = artifacts
    app.register_error_handler(AppException, lambda error: (error.to_dict(), error.http_status))
    raw.clear()
    for index in range(45):
        path=folder/f'feature-{index:03d}.csv'
        path.write_text('sample,Category,V1\n001,A,1\n010,B,2\n', encoding='utf-8')
        raw.append({'id':str(index), 'job_id':'job-Set1', 'cache_type':'umapin_table',
                    'path':str(path),'status':'available','report':'x'*100000})
    raw.append({'id':'missing','job_id':'job-Set1','cache_type':'umapin_table',
                'path':str(folder/'missing.csv'),'status':'missing'})
    job=db.session.get(AnalysisJob,'job-Set1')
    job.payload={**job.payload,'task_name':'中文来源任务'}
    db.session.commit()
    return app.test_client(),raw,folder


def test_summary_catalog_and_full_source_contract(artifacts):
    client,raw,folder=setup_client(artifacts)
    url='/api/script-hub/pep-cache-candidates?project_id=project&asset_set=Set1&cache_type=umapin'
    summary=client.get(url+'&view=summary')
    assert summary.status_code==200,summary.json
    assert set(summary.json)=={'success','summary'}
    assert summary.json['summary']['total']==46 and summary.json['summary']['available']==45
    assert summary.json['summary']['unavailable']==1
    assert 'path' not in summary.get_data(as_text=True)
    pages=[client.get(url+f'&view=catalog&page={page}&page_size=20').json for page in (1,2,3)]
    assert [len(page['candidates']) for page in pages]==[20,20,6]
    ids=[row['id'] for page in pages for row in page['candidates']]
    assert len(set(ids))==46
    assert all(row['source_task_name']=='中文来源任务' for page in pages for row in page['candidates'])
    assert all('path' not in row and 'report' not in row and 'files' not in row for page in pages for row in page['candidates'])
    assert pages[0]['pagination']=={'page':1,'page_size':20,'total':46,'total_pages':3}
    searched=client.get(url+'&view=catalog&q=feature-007').json
    # The explicit artifact ID embeds its file identity; name/path is not substituted.
    assert searched['pagination']['total']==1
    selected=searched['candidates'][0]
    assert selected['id'] in ids and selected['status']=='available'
    inspected=client.post('/api/script-hub/umapin/inspect',json={
        'project_id':'project','asset_set':'Set1','upstream_artifact_id':selected['id']})
    assert inspected.status_code==200,inspected.json
    assert inspected.json['data_path']==str(folder/'feature-007.csv')
    full=client.get(url).json['candidates']
    assert len(full)==46 and any(item.get('path') for item in full)
    unavailable=client.get(url+'&view=catalog&status=unavailable').json
    assert unavailable['pagination']['total']==1
    assert unavailable['summary']['available']==45
    assert unavailable['candidates'][0]['reason']
    # Editing actual source bytes invalidates the same identity on the next read.
    (folder/'Set1-profile.csv').write_text('sample,group,value\n001,A,999\n',encoding='utf-8')
    changed=client.get(url+'&view=summary').json
    assert changed['summary']['available']==0


@pytest.mark.parametrize('extra', ['view=bad','view=catalog&page=0','view=catalog&page_size=101',
                                 'view=catalog&page=oops','view=catalog&status=missing'])
def test_invalid_catalog_options_rejected(artifacts,extra):
    client,_,_=setup_client(artifacts)
    response=client.get('/api/script-hub/pep-cache-candidates?project_id=project&asset_set=Set1&'+extra)
    assert response.status_code==400


@pytest.mark.parametrize('endpoint', ['pep-cache-candidates','go-kegg-enrichment/sources','immune-infiltration-pathway/sources'])
def test_management_views_require_explicit_dataset(artifacts,endpoint):
    client,_,_=setup_client(artifacts)
    assert client.get('/api/script-hub/'+endpoint+'?project_id=project&view=summary').status_code==400


def test_expression_and_pathway_routes_preserve_full_contracts(artifacts):
    client,_,folder=setup_client(artifacts)
    from flask_app.services.path_access_service import PathAccessService
    # Existing source services authorize the real synthetic output root.
    app=artifacts[0]
    app.config['FILE_BROWSER_ROOT']=str(folder)
    app.config['ALLOWED_EXTERNAL_DATA_ROOTS']=[str(folder)]
    db.session.add(AnalysisJob(id='expr-job',project_id='project',module='volcano',job_type='script_hub',
        status='failed',payload={'asset_set':'Set1','task_name':'中文差异来源'},
        result={'metadata':{'input_mode':'expression','comparisons':[['A','B']], 'heavy':'x'*100000}}))
    db.session.add(AnalysisJob(id='go-job',project_id='project',module='go-kegg-enrichment',job_type='script_hub',
        status='completed',payload={'asset_set':'Set1','task_name':'中文通路来源'},
        result={'metadata':{'comparisons':[{'group1':'A','group2':'A'}]}}))
    db.session.commit()
    for endpoint,identity in [('go-kegg-enrichment/sources','expr-job:deg'),('immune-infiltration-pathway/sources','go-job:go-bp:0')]:
        url='/api/script-hub/'+endpoint+'?project_id=project&asset_set=Set1'
        full=client.get(url).json['candidates']
        catalog=client.get(url+'&view=catalog&q=中文').json
        assert len(full)==1 and full[0]['id']==identity
        assert catalog['candidates'][0]['id']==identity
        assert catalog['candidates'][0]['status']=='unavailable'
        assert catalog['summary']['available']==0
        assert 'metadata' not in catalog['candidates'][0] and 'path' not in catalog['candidates'][0]
        assert 'candidates' not in client.get(url+'&view=summary').json


def test_management_path_reason_is_chinese_without_changing_source_validation(artifacts):
    client,_,folder=setup_client(artifacts)
    db.session.add(AnalysisJob(id='missing-expression',project_id='project',module='volcano',job_type='script_hub',
        status='completed',payload={'asset_set':'Set1','task_name':'缺失路径来源'},
        result={'output_base':str(folder/'does-not-exist'),'metadata':{'input_mode':'expression','comparisons':[['A','B']]}}))
    db.session.commit()
    # Use real filesystem checks; TESTING otherwise permits nonexistent paths.
    artifacts[0].config['TESTING']=False
    url='/api/script-hub/go-kegg-enrichment/sources?project_id=project&asset_set=Set1'
    full=client.get(url).json['candidates'][0]
    managed=client.get(url+'&view=catalog').json['candidates'][0]
    assert full['reason']=='Path does not exist'
    assert managed['reason']=='来源路径不存在，请检查来源文件或重新运行。'
    assert managed['id']==full['id'] and managed['status']==full['status']=='unavailable'
    assert managed['description']=='比较：A → B'
    assert client.get(url+'&view=catalog&q=B').json['pagination']['total']==1
