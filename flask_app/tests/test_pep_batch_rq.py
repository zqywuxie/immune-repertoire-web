"""Real isolated Redis/RQ worker executes a complete synthetic batch."""
import importlib
import os
import uuid
from pathlib import Path
import pandas as pd
from redis import Redis
from rq import Queue, Worker


def test_real_batch_pep_output_feeds_downstream(tmp_path, monkeypatch):
    from flask_app.config import TestingConfig
    monkeypatch.setattr(TestingConfig,"SQLALCHEMY_DATABASE_URI",f"sqlite:///{tmp_path / 'batch.db'}")
    monkeypatch.setattr(TestingConfig,"REQUIRE_LOGIN",False)
    monkeypatch.setattr(TestingConfig,"RESULTS_FOLDER",tmp_path/"results")
    monkeypatch.setenv("JOB_QUEUE","redis")
    module=importlib.import_module("flask_app.app")
    app=module.create_app("testing")
    monkeypatch.setattr(module,"app",app)
    from flask_app.models.database import db,Project,ProjectAsset
    from flask_app.services.background_job_service import get_background_job_service
    from flask_app.services import persistent_queue
    connection=Redis.from_url(os.environ["REDIS_URL"])
    queue=Queue("batch-regression-"+uuid.uuid4().hex,connection=connection)
    monkeypatch.setattr(persistent_queue,"redis_queue",lambda:queue)
    with app.app_context():
        profile=tmp_path/'profile.csv'
        pep=tmp_path/'pep';pep.mkdir()
        samples=[f'S{i}' for i in range(8)]
        pd.DataFrame({'sample':samples,'group':['A']*4+['B']*4}).to_csv(profile,index=False)
        for i,sample in enumerate(samples):
            pd.DataFrame({'CDR3(pep)':['CASSA','CASSB','CASSC','CASSD'],'V':['TRBV1','TRBV2','TRBV3','TRBV4'],'J':['TRBJ1']*4,'copy':[i+1,10-i,(i+2)**2,5]}).to_csv(pep/f'{sample}__TRB.csv',index=False)
        db.session.add(Project(id='rq-project',name='真实上下游批次'));db.session.flush()
        for kind,path in [('profile',profile),('pep',pep)]:
            db.session.add(ProjectAsset(project_id='rq-project',asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'Set1'}))
        db.session.commit()
        response=app.test_client().post('/api/script-hub/batches',json={'project_id':'rq-project','asset_set':'Set1','items':[
            {'module':'pep-analysis','payload':{'group_fields':['group'],'selected_chains':['TRB'],'optional_steps':[],'force_rerun':True}},
            {'module':'umapin','upstream_from':0,'payload':{'category_col':'Category','n_neighbors':3,'force_rerun':True}},
        ]})
        assert response.status_code==202,response.json
        parent_id=response.json["job_id"]
        db.session.remove()
        db.engine.dispose()
        try:
            worker=Worker([queue],connection=connection,work_horse_killed_handler=persistent_queue.record_killed)
            worker.work(burst=True,with_scheduler=False,logging_level="WARNING")
            db.session.remove()
            parent=get_background_job_service().get_job(parent_id)
            if parent['status'] != 'completed':
                from flask_app.services.analysis_artifacts import scoped_pep_candidates
                print([(item['path'], item['status'], item.get('reason'), item['job_id']) for item in scoped_pep_candidates('rq-project','Set1','umapin')])
                print([(item.get('module'), {key: get_background_job_service().get_job(item['job_id']).get(key) for key in ('status', 'detail', 'error')}) for item in parent['payload']['items'] if item.get('job_id')])
            assert parent["status"]=="completed", (parent.get('error'), parent.get('detail'), parent['payload']['items'])
            assert parent["result"]["completed_count"]==2
            assert len(queue)==0
            source_id=parent['payload']['items'][0]['job_id']
            downstream=get_background_job_service().get_job(parent['payload']['items'][1]['job_id'])
            assert downstream['payload']['upstream_input']['source_job_id']==source_id
            archive_items = []
            for item in parent["payload"]["items"]:
                child=get_background_job_service().get_job(item["job_id"])
                assert child["status"]=="completed",child
                assert child["parent_job_id"]==parent_id
                response=app.test_client().get(f"/api/jobs/{item['job_id']}/results")
                assert response.status_code==200,response.json
                outputs=response.json["outputs"]
                assert outputs, response.json
                assert any(".csv" in output["url"] for output in outputs),outputs
                csv=next(output for output in outputs if ".csv" in output["url"])
                download=app.test_client().get(csv["url"])
                assert download.status_code==200 and len(download.data)>0
                preview = app.test_client().post(f"/api/jobs/{item['job_id']}/table-preview", json={"url": csv["url"], "limit": 2})
                assert preview.status_code == 200, preview.json
                assert preview.json["columns"] and 0 < len(preview.json["rows"]) <= 2
                assert all(isinstance(value, str) for row in preview.json["rows"] for value in row)
                archive_items.append({"job_id": item["job_id"], "url": csv["url"]})
            archive_response = app.test_client().post("/api/jobs/results/archive", json={"items": archive_items})
            assert archive_response.status_code == 200, archive_response.json
            import io, zipfile
            with zipfile.ZipFile(io.BytesIO(archive_response.data)) as bundle:
                assert len(bundle.namelist()) == 2
                assert all(len(bundle.read(name)) > 0 for name in bundle.namelist())
            archive_response.close()
        finally:
            queue.delete(delete_jobs=True)
            db.session.remove()
            db.drop_all()
