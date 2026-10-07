"""Actual selected expression columns through real RQ and native R enrichment (empty ORA, no GSEA)."""
import importlib
import os
import subprocess
import uuid
import zipfile
from io import BytesIO
from pathlib import Path
import pandas as pd
import pytest
from redis import Redis
from rq import Queue, Worker


@pytest.mark.skipif(os.environ.get('RUN_EXPRESSION_SELECTION_RQ') != '1', reason='需要显式启用隔离 Redis 与真实表达样本 RQ 验收')
def test_selected_expression_to_enrichment_real_rq(tmp_path, monkeypatch):
    from flask_app.config import TestingConfig
    monkeypatch.setattr(TestingConfig,'SQLALCHEMY_DATABASE_URI',f"sqlite:///{tmp_path / 'jobs.db'}")
    monkeypatch.setattr(TestingConfig,'REQUIRE_LOGIN',False)
    monkeypatch.setattr(TestingConfig,'RESULTS_FOLDER',tmp_path/'results')
    monkeypatch.setenv('JOB_QUEUE','redis')
    monkeypatch.setattr('flask_app.services.mongo_service.save_result', lambda **kwargs: 'isolated-expression-result')
    module=importlib.import_module('flask_app.app')
    app=module.create_app('testing');monkeypatch.setattr(module,'app',app)
    from flask_app.models.database import db,Project,ProjectAsset
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services import persistent_queue
    connection=Redis.from_url(os.environ['REDIS_URL'])
    queue=Queue('enrichment-regression-'+uuid.uuid4().hex,connection=connection)
    monkeypatch.setattr(persistent_queue,'redis_queue',lambda:queue)
    from flask_app.tests.test_expression_selection import expression_table
    expression = tmp_path / 'expression.csv'
    expression_table(expression)
    selected_samples = [f'tpm_{group}_{index:03d}' for group in ['01', '02'] for index in range(1, 4)]
    with app.app_context():
        db.session.add(Project(id='enrich-project',name='合成富集链'));db.session.flush()
        db.session.add(ProjectAsset(project_id='enrich-project',asset_type='transcriptome',storage_path=str(expression),original_name=expression.name,size=expression.stat().st_size,metadata_json={'asset_set':'Set1'}));db.session.commit()
        response=app.test_client().post('/api/script-hub/batches',json={'project_id':'enrich-project','asset_set':'Set1','items':[
            {'module':'volcano','payload':{'input_mode':'expression','comparisons':[['02','01']],'selected_expression_groups':['01','02'],'selected_expression_samples':selected_samples,'pvalue_threshold':1e-300,'logfc_cutoff':0,'output_name':'真实选定表达样本','force_rerun':True}},
            {'module':'go-kegg-enrichment','upstream_from':0,'payload':{'do_gsea':False,'simplify_go':False,'show_category':5,'output_name':'真实复用表达结果','force_rerun':True}}
        ]})
        if response.status_code != 202 and response.json.get('job_id'):
            print(get_background_job_service().get_job(response.json['job_id']))
        assert response.status_code==202,response.json
        parent_id=response.json['job_id']
        from flask_app.services.deployment_maintenance import set_maintenance
        app.config['MAINTENANCE_DIRECTORY']=str(tmp_path/'maintenance')
        set_maintenance(tmp_path/'maintenance', 'integration', True)
        db.session.remove();db.engine.dispose()
        try:
            Worker([queue],connection=connection,work_horse_killed_handler=persistent_queue.record_killed).work(burst=True,logging_level='WARNING')
            db.session.remove()
            service=get_background_job_service()
            parent=service.get_job(parent_id)
            children=[service.get_job(item['job_id']) for item in parent['payload']['items'] if item.get('job_id')]
            if parent['status']!='completed':
                for child in children:
                    if child['status']!='completed':
                        print('ENRICHMENT FAILURE:', child.get('detail'))
            assert parent['status']=='completed',[(child['status'],child.get('detail')) for child in children]
            assert len(children)==2
            upstream,downstream=children
            assert downstream['payload']['upstream_input']['source_job_id']==upstream['job_id']
            assert downstream['result']['metadata']['reused_differential_results'] is True
            assert downstream['result']['metadata']['do_gsea'] is False
            assert upstream['result']['metadata']['selected_expression_samples'] == selected_samples
            assert downstream['result']['metadata']['selected_expression_samples'] == selected_samples
            assert downstream['result']['metadata']['sample_count'] == 6
            assert downstream['result']['metadata']['logfc_cutoff'] == 0
            assert downstream['result']['metadata']['output_name'] == '真实复用表达结果'
            quality = pd.read_csv(Path(upstream['result']['output_base'])/'DEG'/'02_vs_01'/'QC'/'sample_quality_weights.csv', dtype={'group': str})
            assert quality['sample'].tolist() == selected_samples
            assert set(quality['group']) == {'01', '02'}
            output=Path(downstream['result']['output_base'])
            assert (output/'go_kegg_enrichment.log').is_file()
            assert downstream['result']['metadata']['full_go_gsea_tables'] == []
            originals=list((Path(upstream['result']['output_base'])/'DEG').rglob('DEG_02_vs_01.csv'))
            copies=list((output/'DEG').rglob('DEG_02_vs_01.csv'))
            assert originals and copies and originals[0].read_bytes()==copies[0].read_bytes()
            response=app.test_client().get(downstream['result']['zip_url'])
            assert response.status_code==200, (response.json, downstream['result']['zip_url'], str(output), [(a.asset_type,(a.metadata_json or {}).get('job_id'),a.storage_path) for a in ProjectAsset.query.all()], downstream['payload'].get('analysis_signature'))
            with zipfile.ZipFile(BytesIO(response.data)) as archive:
                assert any(name.endswith('DEG_02_vs_01.csv') for name in archive.namelist())
            response.close()
            viewer = app.test_client().get(downstream['result']['viewer_url'])
            assert viewer.status_code == 200
            assert '沿用来源比较、实际样本范围与筛选标记' in viewer.get_data(as_text=True)
            assert '本次未运行 GSEA' in viewer.get_data(as_text=True)
            viewer.close()
        finally:
            for task_id in queue.finished_job_registry.get_job_ids()+queue.failed_job_registry.get_job_ids():
                task=queue.fetch_job(task_id)
                if task:task.delete()
            queue.delete()
            db.session.remove();db.drop_all()
