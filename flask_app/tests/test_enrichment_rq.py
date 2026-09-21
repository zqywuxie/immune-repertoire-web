"""Opt-in real R/KEGG integration using synthetic inputs and an isolated queue."""
import importlib
import os
import subprocess
import uuid
from pathlib import Path
import pandas as pd
import pytest
from redis import Redis
from rq import Queue, Worker


@pytest.mark.skipif(os.environ.get('RUN_ENRICHMENT_INTEGRATION') != '1', reason='需要显式启用真实 R 与 KEGG 联网集成验收')
def test_expression_to_enrichment_real_rq(tmp_path, monkeypatch):
    from flask_app.config import TestingConfig
    monkeypatch.setattr(TestingConfig,'SQLALCHEMY_DATABASE_URI',f"sqlite:///{tmp_path / 'jobs.db'}")
    monkeypatch.setattr(TestingConfig,'REQUIRE_LOGIN',False)
    monkeypatch.setattr(TestingConfig,'RESULTS_FOLDER',tmp_path/'results')
    monkeypatch.setenv('JOB_QUEUE','redis')
    module=importlib.import_module('flask_app.app')
    app=module.create_app('testing');monkeypatch.setattr(module,'app',app)
    from flask_app.models.database import db,Project,ProjectAsset
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services import persistent_queue
    connection=Redis.from_url(os.environ['REDIS_URL'])
    queue=Queue('enrichment-regression-'+uuid.uuid4().hex,connection=connection)
    monkeypatch.setattr(persistent_queue,'redis_queue',lambda:queue)
    background=tmp_path/'background.txt'
    subprocess.run(['Rscript','-e','suppressPackageStartupMessages(library(org.Hs.eg.db)); writeLines(head(AnnotationDbi::keys(org.Hs.eg.db,keytype="SYMBOL"),2000), "'+str(background)+'")'],check=True)
    selected='CD3D CD3E CD3G CD247 CD4 CD8A CD8B LCK ZAP70 LAT LCP2 ITK FYN PTPRC CD28 CTLA4 ICOS PDCD1 IL2 IL2RA IL2RB JAK1 JAK3 STAT5A STAT5B IL7R CD40 CD40LG HLA-DRA'.split()
    genes=list(dict.fromkeys(selected+background.read_text().splitlines()))
    expression=tmp_path/'expression.csv'
    values={'Gene':genes}
    for group in ['A','B']:
        for index in range(1,5):
            values[f'tpm_{group}_{index}']=[(100 if group=='A' and gene in selected else 10)+index for gene in genes]
    pd.DataFrame(values).to_csv(expression,index=False)
    with app.app_context():
        db.session.add(Project(id='enrich-project',name='合成富集链'));db.session.flush()
        db.session.add(ProjectAsset(project_id='enrich-project',asset_type='transcriptome',storage_path=str(expression),original_name=expression.name,size=expression.stat().st_size,metadata_json={'asset_set':'Set1'}));db.session.commit()
        response=app.test_client().post('/api/script-hub/batches',json={'project_id':'enrich-project','asset_set':'Set1','items':[
            {'module':'volcano','payload':{'input_mode':'expression','comparisons':[['A','B']],'force_rerun':True}},
            {'module':'go-kegg-enrichment','upstream_from':0,'payload':{'do_gsea':False,'simplify_go':False,'show_category':5,'force_rerun':True}}
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
            assert parent['status']=='completed',[(child['status'],child.get('detail')) for child in children]
            assert len(children)==2
            upstream,downstream=children
            assert downstream['payload']['upstream_input']['source_job_id']==upstream['job_id']
            assert downstream['result']['metadata']['reused_differential_results'] is True
            output=Path(downstream['result']['output_base'])
            assert list((output/'enrichment_results').rglob('*.csv'))
            originals=list((Path(upstream['result']['output_base'])/'DEG').rglob('DEG_A_vs_B.csv'))
            copies=list((output/'DEG').rglob('DEG_A_vs_B.csv'))
            assert originals and copies and originals[0].read_bytes()==copies[0].read_bytes()
            response=app.test_client().get(downstream['result']['zip_url'])
            assert response.status_code==200, (response.json, downstream['result']['zip_url'], str(output), [(a.asset_type,(a.metadata_json or {}).get('job_id'),a.storage_path) for a in ProjectAsset.query.all()], downstream['payload'].get('analysis_signature'))
            response.close()
        finally:
            for task_id in queue.finished_job_registry.get_job_ids()+queue.failed_job_registry.get_job_ids():
                task=queue.fetch_job(task_id)
                if task:task.delete()
            queue.delete()
            db.session.remove();db.drop_all()
