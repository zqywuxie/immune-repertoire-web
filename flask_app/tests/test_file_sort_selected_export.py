import csv
import io
from datetime import datetime, timedelta
from openpyxl import load_workbook
import pytest
from flask_app.models.database import ProjectAsset, SampleRecord, Project, User, db
from flask_app.tests.test_data_management_contracts import context


def test_file_order_is_global_before_paging_and_searches_literal_description(context):
    app, _, project = context
    for index in range(65):
        db.session.add(ProjectAsset(project_id=project.id, asset_type='profile', original_name=f'文件{64-index:03d}.csv',
            storage_path='/synthetic/'+str(index), size=index*100,
            uploaded_at=datetime(2026,1,1)+timedelta(minutes=index), metadata_json={'asset_set':'甲',
                'description':'包含 %_ 精确说明' if index == 0 else '普通说明'}))
    db.session.add(ProjectAsset(project_id=project.id, asset_type='profile',original_name='别集.csv',storage_path='/other',
        metadata_json={'asset_set':'乙','description':'包含 %_ 精确说明'}))
    db.session.commit(); client=app.test_client(); endpoint=f'/api/projects/{project.id}/assets'
    args={'inputs_only':'true','asset_set':'甲','page_size':50}
    first=client.get(endpoint,query_string={**args,'sort':'name_asc'}).json
    second=client.get(endpoint,query_string={**args,'sort':'name_asc','page':2}).json
    names=[asset['original_name'] for asset in first['assets']+second['assets']]
    assert names == [f'文件{i:03d}.csv' for i in range(65)]
    assert first['pagination']['total'] == second['pagination']['total'] == 65
    for sort, field, reverse in [('size_asc','size',False),('size_desc','size',True),
        ('uploaded_asc','uploaded_at',False),('uploaded_desc','uploaded_at',True),('name_desc','original_name',True)]:
        result=client.get(endpoint,query_string={**args,'sort':sort,'page_size':100}).json['assets']
        assert [row[field] for row in result] == sorted([row[field] for row in result], reverse=reverse)
    for term in ['精确说明','%','_']:
        match=client.get(endpoint,query_string={**args,'q':term}).json
        assert match['pagination']['total']==1 and match['assets'][0]['original_name']=='文件064.csv'
    assert client.get(endpoint,query_string={**args,'sort':'unexpected'}).status_code == 400


def test_selected_export_uses_exact_record_ids_across_pages_and_retains_text(context):
    app, _, project = context
    records=[]
    for index in range(60):
        row=SampleRecord(project_id=project.id,sample_id=f'{index:03d}',sample_name='登记',extra_metadata={'asset_set':'甲'})
        db.session.add(row); records.append(row)
    db.session.commit(); client=app.test_client()
    ids=[records[1].id,records[55].id]
    body={'filters':{'project_id':project.id,'asset_set':'甲'},'record_ids':ids,'format':'xlsx','columns':'technical'}
    response=client.post('/api/samples/export',json=body)
    assert response.status_code==200 and response.headers['X-Export-Count']=='2'
    sheet=load_workbook(io.BytesIO(response.data)).active
    rows=list(sheet.rows); column=[cell.value for cell in rows[0]].index('样本编号')
    assert {row[column].value for row in rows[1:]} == {'001','055'}
    assert all(row[column].data_type=='s' for row in rows[1:])
    response.close()
    response=client.post('/api/samples/export',json={**body,'format':'csv','columns':'business','record_ids':ids+ids})
    assert response.status_code==200 and response.headers['X-Export-Count']=='2'
    assert {row['样本编号'] for row in csv.DictReader(io.StringIO(response.data.decode('utf-8-sig')))} == {'001','055'}
    response.close()
    db.session.delete(records[55]); db.session.commit()
    assert client.post('/api/samples/export',json=body).status_code==400


@pytest.mark.parametrize('ids',[[],None,'001',[None],[''],[' spaced '],['x'*37],['a']*5001])
def test_selected_export_never_turns_invalid_or_empty_selection_into_all_records(context,ids):
    app, _, project=context
    response=app.test_client().post('/api/samples/export',json={'filters':{'project_id':project.id},'record_ids':ids})
    assert response.status_code==400


def test_selected_export_enforces_account_and_dataset_scope(context):
    app, _, project=context
    owner=User(username='selected-owner',email='selected-owner@example.test',password_hash='unused')
    other=User(username='selected-other',email='selected-other@example.test',password_hash='unused')
    db.session.add_all([owner,other]); db.session.flush();project.user_id=owner.id
    foreign=Project(name='其他项目',user_id=other.id);db.session.add(foreign);db.session.flush()
    rows=[SampleRecord(project_id=pid,sample_id='001',sample_name='登记',extra_metadata={'asset_set':dataset})
          for pid,dataset in [(project.id,'甲'),(project.id,'乙'),(foreign.id,'甲')]]
    db.session.add_all(rows);db.session.commit();app.config['REQUIRE_LOGIN']=True
    client=app.test_client()
    with client.session_transaction() as session:session.update(_user_id=str(owner.id),_fresh=True)
    for row in rows[1:]:
        response=client.post('/api/samples/export',json={'filters':{'project_id':project.id,'asset_set':'甲'},'record_ids':[rows[0].id,row.id]})
        assert response.status_code==400
