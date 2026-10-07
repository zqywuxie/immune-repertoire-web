import importlib
import os
import uuid
import pytest
from redis import Redis
from rq import Queue,Worker
from flask_app.tests.test_infiltration import inputs

@pytest.mark.skipif(not os.environ.get('RUN_INFILTRATION_RQ'),reason='需要隔离 Redis 队列')
@pytest.mark.parametrize("analysis_module", ["immune-infiltration", "immune-infiltration-consistency", "immune-infiltration-concordance", "immune-infiltration-paired", "immune-infiltration-pathway", "immune-infiltration-sample-pathway"])
def test_infiltration_batch_rq(tmp_path,monkeypatch,analysis_module):
    from flask_app.config import TestingConfig
    monkeypatch.setattr(TestingConfig,'SQLALCHEMY_DATABASE_URI',f'sqlite:///{tmp_path / "batch.db"}')
    monkeypatch.setattr(TestingConfig,'REQUIRE_LOGIN',False)
    monkeypatch.setattr(TestingConfig,'RESULTS_FOLDER',tmp_path/'results')
    monkeypatch.setenv('FLASK_CONFIG','testing')
    monkeypatch.setenv('JOB_QUEUE','redis')
    module=importlib.import_module('flask_app.app');app=module.create_app('testing');monkeypatch.setattr(module,'app',app)
    monkeypatch.setattr('flask_app.services.mongo_service.save_result',lambda **kwargs:'synthetic-result')
    from flask_app.models.database import db,Project,ProjectAsset
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services import persistent_queue
    connection=Redis.from_url(os.environ['REDIS_URL']);queue=Queue('infiltration-'+uuid.uuid4().hex,connection=connection)
    monkeypatch.setattr(persistent_queue,'redis_queue',lambda:queue)
    with app.app_context():
        profile,deconv=inputs(tmp_path)
        extra_assets=[]
        if analysis_module == 'immune-infiltration-sample-pathway':
            import pandas as pd
            sample_ids=[f'{i:03d}' for i in range(1,13)]
            pd.DataFrame({'sample':sample_ids,'group':['01']*6+['02']*6}).to_csv(profile,index=False)
            pd.DataFrame({'Mixture':sample_ids,'T cells':[i/12 for i in range(1,13)],
                'B cells':[1-i/12 for i in range(1,13)]}).to_csv(deconv,index=False)
            expression=tmp_path/'expression.tsv'
            gene_output=tmp_path/'go-genes.txt'
            gene_command="suppressPackageStartupMessages({library(AnnotationDbi);library(org.Hs.eg.db)}); ids<-c('GO:0002250','GO:0046649','GO:0042110','GO:0042113','GO:0006959','GO:0045087','GO:0002274','GO:0006954','GO:0019221','GO:0006956'); a<-AnnotationDbi::select(org.Hs.eg.db::org.Hs.eg.db,keys=ids,keytype='GOALL',columns=c('SYMBOL','ONTOLOGYALL')); g<-unique(toupper(a$SYMBOL[!is.na(a$ONTOLOGYALL)&a$ONTOLOGYALL=='BP'&!is.na(a$SYMBOL)])); write.table(head(g,1000),commandArgs(TRUE)[1],row.names=FALSE,col.names=FALSE,quote=FALSE)"
            import subprocess
            subprocess.run(['Rscript','-e',gene_command,str(gene_output)],check=True,capture_output=True,text=True)
            genes=gene_output.read_text(encoding='utf-8').splitlines()
            frame={'Gene':genes}
            for index,sample in enumerate(sample_ids):frame[sample]=[float(gene_index+index+1) for gene_index in range(len(genes))]
            pd.DataFrame(frame).to_csv(expression,sep='\t',index=False)
            extra_assets.append(('transcriptome',expression))
        if analysis_module in {'immune-infiltration-concordance','immune-infiltration-paired'}:
            import pandas as pd
            frame=pd.read_csv(profile,dtype=str);frame['IGHA1']=range(8);frame.to_csv(profile,index=False)
        if analysis_module == 'immune-infiltration-paired':
            frame['sample']=['P'+str(i).zfill(3) for i in range(8)]
            frame.to_csv(profile,index=False)
        if analysis_module == 'immune-infiltration-pathway':
            from flask_app.tests.test_pathway_artifacts import source_fixture
            source_data,source,_,_,_=source_fixture(app,tmp_path)
            project=db.session.get(Project,source_data['project_id'])
        else:
            project=Project(name='队列浸润验收');db.session.add(project);db.session.flush()
        for kind,path in [('profile',profile),('deconvolution',deconv),*extra_assets]:
            db.session.add(ProjectAsset(project_id=project.id,asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'Set1'}))
        db.session.commit()
        selected_ids = [f'{i:03d}' for i in [*range(1,6),*range(7,12)]] if analysis_module == 'immune-infiltration-sample-pathway' else [f'{i:03d}' for i in [0,1,2,4,5,6]]
        result=app.test_client().post('/api/script-hub/batches',json={'project_id':project.id,'asset_set':'Set1','items':[{'module':analysis_module,'payload':{**({'comparison':['A','B'],'upstream_artifact_id':'go-source:go-bp:0'} if analysis_module == 'immune-infiltration-pathway' else {'comparison':['01','02']} if analysis_module == 'immune-infiltration-sample-pathway' else {}),'selected_infiltration_samples':selected_ids,'output_name':'队列实际浸润范围','group_field':'group','cell_columns':['T cells','B cells'],'score_type':'absolute','sample_pairs':[{'deconvolution_sample':f'{i:03d}','profile_sample':('P' if analysis_module == 'immune-infiltration-paired' else '')+f'{i:03d}'} for i in [0,1,2,4,5,6]]}}]})
        assert result.status_code==202,result.json
        parent_id=result.json['job_id'];db.session.remove();db.engine.dispose()
        try:
            Worker([queue],connection=connection).work(burst=True,with_scheduler=False,logging_level='WARNING')
            db.session.remove();parent=get_background_job_service().get_job(parent_id)
            assert parent['status']=='completed', (parent.get('detail'), parent['payload']['items'], [get_background_job_service().get_job(item['job_id']) for item in parent['payload']['items'] if item.get('job_id')])
            child=get_background_job_service().get_job(parent['payload']['items'][0]['job_id'])
            assert child['status']=='completed',child
            assert child['result']['result_id']=='synthetic-result'
            assert child['result']['metadata']['score_type']=='absolute'
            assert child['result']['metadata']['sample_count'] == (10 if analysis_module == 'immune-infiltration-sample-pathway' else 6)
            assert child['result']['metadata']['output_name'] == '队列实际浸润范围'
            if analysis_module != 'immune-infiltration-paired':
                assert child['result']['metadata']['selected_infiltration_samples'] == selected_ids
            from pathlib import Path
            assert Path(child['result']['output_base']).parent.name == analysis_module
            response=app.test_client().get(child['result']['zip_url'])
            assert response.status_code==200 and len(response.data)>100
        finally:
            queue.delete(delete_jobs=True);db.session.remove();db.drop_all()
