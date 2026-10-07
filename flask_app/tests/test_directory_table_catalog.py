"""Directory paging keeps complete counts and path boundaries without eager sizes."""
from pathlib import Path
from unittest.mock import patch
from flask_app.tests.test_data_management_contracts import context
from flask_app.models.database import ProjectAsset, db

def test_directory_page_reads_only_page_sizes_and_preserves_nested_sorted_names(context,tmp_path):
    app,_,project=context
    root=tmp_path/'tables';root.mkdir();nested=root/'子目录';nested.mkdir()
    for number in range(121):(root/f'{number:03d}.csv').write_text('sample,value\n001,1\n')
    (nested/'中文.tsv').write_text('sample\tvalue\n001\t2\n')
    (root/'ignored.png').write_bytes(b'synthetic')
    outside=tmp_path/'external';outside.mkdir();(outside/'hidden.csv').write_text('secret')
    (root/'shortcut').symlink_to(outside,target_is_directory=True);(root/'link.csv').symlink_to(outside/'hidden.csv')
    asset=ProjectAsset(project_id=project.id,asset_type='pep',original_name='目录',storage_path=str(root));db.session.add(asset);db.session.commit()
    endpoint=f'/api/projects/{project.id}/assets/{asset.id}/table-preview'
    stat=Path.stat;read_sizes=[]
    def track(path,*args,**kwargs):
        if str(path).startswith(str(root)+'/') and path.suffix=='.csv':read_sizes.append(path.name)
        return stat(path,*args,**kwargs)
    with patch.object(Path,'stat',track):response=app.test_client().get(endpoint+'?page=2&page_size=20')
    assert response.status_code==200
    assert response.json['pagination']['total']==122
    assert [entry['name'] for entry in response.json['files']]==[f'{number:03d}.csv' for number in range(20,40)]
    assert read_sizes==[f'{number:03d}.csv' for number in range(20,40)]
    last=app.test_client().get(endpoint+'?page=7&page_size=20').json
    assert [entry['name'] for entry in last['files']]==['120.csv','子目录/中文.tsv']
    assert app.test_client().get(endpoint,query_string={'file':'子目录/中文.tsv','include_files':'false'}).json['rows']==[['001','2']]
    for name in ['link.csv','shortcut/hidden.csv','../external/hidden.csv']:
        assert app.test_client().get(endpoint,query_string={'file':name,'include_files':'false'}).status_code==400

def test_reference_sql_does_not_load_finished_validation_payloads(context):
    from sqlalchemy import event
    from flask_app.models.database import AnalysisJob
    from flask_app.services.project_asset_lineage import asset_lineage
    app,_,project=context
    asset=ProjectAsset(project_id=project.id,asset_type='profile',original_name='目标.csv',storage_path='/synthetic/target.csv');db.session.add(asset);db.session.flush()
    for number in range(80):
        db.session.add(AnalysisJob(project_id=project.id,job_type='input_validation',module='profile',status='completed',payload={'asset_id':asset.id,'report':'x'*10000}))
    for kind,status in [('script_hub','completed'),('input_validation','queued')]:
        db.session.add(AnalysisJob(project_id=project.id,job_type=kind,module='profile',status=status,payload={'asset_id':asset.id}))
    db.session.commit();statements=[]
    def query(_connection,_cursor,statement,_params,_context,_many):
        if 'FROM analysis_jobs' in statement and statement.lstrip().upper().startswith('SELECT'):statements.append(statement)
    event.listen(db.engine,'before_cursor_execute',query)
    try:result=asset_lineage(asset,'jobs')
    finally:event.remove(db.engine,'before_cursor_execute',query)
    assert result['pagination']['total']==2
    assert {item['status'] for item in result['items']}=={'queued','completed'}
    assert len(statements)==1 and 'NOT IN' in statements[0] and 'job_type !=' in statements[0]


def test_compressed_tsv_preview_preserves_text_ids_and_uses_tab_columns(context,tmp_path):
    import gzip
    app,_,project=context
    source=tmp_path/'compressed.tsv.gz'
    with gzip.open(source,'wt',encoding='utf-8') as output:output.write('sample\tvalue\n001\t2\n')
    asset=ProjectAsset(project_id=project.id,asset_type='profile',original_name=source.name,storage_path=str(source));db.session.add(asset);db.session.commit()
    response=app.test_client().get(f'/api/projects/{project.id}/assets/{asset.id}/table-preview?include_files=false')
    assert response.status_code==200 and response.json['columns']==['sample','value']
    assert response.json['rows']==[['001','2']]
