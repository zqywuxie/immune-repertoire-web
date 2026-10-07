"""Paged identifier candidates and exact single registration preserve scope and text identity."""
import pytest
from sqlalchemy import event
from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import Project, ProjectAsset, SampleRecord, User, db

def record(project, identifier, dataset='甲', **metadata):
    result = SampleRecord(project_id=project.id, sample_id=identifier, sample_name=identifier or '空编号',
        sequence_id=f'序列{identifier}' if identifier else None, institution='研究机构',
        extra_metadata={'asset_set':dataset, **metadata})
    db.session.add(result)
    return result

def test_catalog_pages_distinct_text_ids_with_scope_and_legacy_full_contract(context):
    app, _, project = context
    for index in range(46): record(project, f'{index:03d}')
    record(project, '001'); record(project, ''); record(project, '乙编号', '乙')
    db.session.commit(); client=app.test_client()
    args={'project_id':project.id,'asset_set':'甲','view':'catalog','field':'sample_id'}
    pages=[client.get('/api/samples/field-options',query_string={**args,'page':page}).json for page in [1,2,3]]
    assert [len(page['values']) for page in pages] == [20,20,6]
    assert all(page['pagination']['total']==46 for page in pages)
    values=[value for page in pages for value in page['values']]
    assert len(set(values))==46 and '001' in values and '乙编号' not in values
    low=client.get('/api/samples/field-options',query_string={**args,'view':'filters','field':''}).json['fields']
    assert 'sample_id' not in low and 'sequence_id' not in low and low['institution']==['研究机构']
    full=client.get('/api/samples/field-options',query_string={**args,'view':''}).json['fields']['sample_id']
    assert full==values
    seq=client.get('/api/samples/field-options',query_string={**args,'field':'sequence_id','q':'序列001'}).json
    assert seq['values']==['序列001'] and seq['pagination']['total']==1

def test_catalog_search_treats_percent_and_underscore_as_literal(context):
    app,_,project=context
    for value in ['A%1','AB1','A_1','AC1']: record(project,value)
    db.session.commit(); client=app.test_client()
    for term,expected in [('%',['A%1']),('_',['A_1'])]:
        data=client.get('/api/samples/field-options',query_string={'project_id':project.id,'view':'catalog','field':'sample_id','q':term}).json
        assert data['values']==expected

@pytest.mark.parametrize('parameters',[{'view':'wrong'},{'field':'institution'},{'page':'0'},{'page':'1.2'},
    {'page_size':'101'},{'page_size':'-2'},{'page_size':'二十'},{'q':'x'*201}])
def test_catalog_rejects_invalid_parameters(context,parameters):
    app,_,project=context
    response=app.test_client().get('/api/samples/field-options',query_string={'project_id':project.id,'view':'catalog','field':'sample_id',**parameters})
    assert response.status_code==400

def test_catalog_access_scope_matches_existing_sample_options(context):
    app,_,project=context
    owner=User(username='甲用户',email='owner@example.test',password_hash='unused')
    foreign=User(username='乙用户',email='foreign@example.test',password_hash='unused')
    db.session.add_all([owner,foreign]);db.session.flush();project.user_id=owner.id
    other=Project(name='他人项目',user_id=foreign.id);db.session.add(other);db.session.flush()
    record(project,'001');record(other,'秘密');db.session.commit();app.config['REQUIRE_LOGIN']=True
    client=app.test_client()
    with client.session_transaction() as session: session.update(_user_id=str(owner.id),_fresh=True)
    response=client.get('/api/samples/field-options?view=catalog&field=sample_id').json
    assert response['values']==['001'] and response['pagination']['total']==1
    assert client.get('/api/samples/field-options',query_string={'view':'catalog','field':'sample_id','project_id':other.id}).json['values']==[]

def test_single_registration_loads_only_target_candidates_and_preserves_manual_fields(context):
    app,_,project=context
    db.session.add(ProjectAsset(project_id=project.id,asset_type='profile',original_name='输入.csv',storage_path='/synthetic/input',
        metadata_json={'asset_set':'甲','validation':{'status':'valid','summary':{'inputs':[{'samples':['001']}]}}}))
    target=record(project,'001',manual_fields=['illness']);target.illness='人工疾病'
    target_id=target.id
    for index in range(250):record(project,f'X{index:03d}')
    record(project,'001','乙');record(project,'001',input_sample_id=None);record(project,'001',input_sample_id='其他编号')
    db.session.commit();target_id=target.id;project_id=project.id;db.session.expunge_all();loaded=[]
    def on_load(value,_context):loaded.append(value.sample_id)
    event.listen(SampleRecord,'load',on_load)
    try:
        response=app.test_client().get(f'/api/projects/{project_id}/samples/registration?asset_set=甲&sample_id=001')
    finally:event.remove(SampleRecord,'load',on_load)
    assert response.status_code==200 and response.json['sample']['id']==target_id
    assert response.json['sample']['illness']=='人工疾病'
    assert loaded and set(loaded)=={'001'} and len(loaded)<=3
    # An explicit mapped ID participates even when the registration's original ID differs.
    record(db.session.get(Project,project_id),'映射原编号',input_sample_id='001');db.session.commit()
    duplicate=app.test_client().get(f'/api/projects/{project_id}/samples/registration?asset_set=甲&sample_id=001')
    assert duplicate.status_code==400 and '多条登记' in duplicate.json['message']


def test_twenty_thousand_identifier_candidates_keep_page_bound_and_text_order(context):
    app,_,project=context
    for offset in range(0,20000,1000):
        db.session.bulk_insert_mappings(SampleRecord,[{
            'project_id':project.id,'sample_id':f'S{index:05d}','sample_name':f'样本{index}',
            'sequence_id':f'序列{index:05d}','extra_metadata':{'asset_set':'甲'}
        } for index in range(offset,offset+1000)])
    db.session.commit();client=app.test_client()
    args={'project_id':project.id,'asset_set':'甲','view':'catalog','field':'sample_id','page':1000}
    response=client.get('/api/samples/field-options',query_string=args)
    assert response.status_code==200 and len(response.data)<1000
    assert response.json['pagination']=={'page':1000,'page_size':20,'total':20000,'total_pages':1000}
    assert response.json['values']==[f'S{index:05d}' for index in range(19980,20000)]
    exact=client.get('/api/samples/field-options',query_string={**args,'q':'S00001','page':1}).json
    assert exact['values']==['S00001'] and exact['pagination']['total']==1
