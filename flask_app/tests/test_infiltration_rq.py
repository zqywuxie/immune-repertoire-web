import importlib
import os
import uuid
import pytest
from redis import Redis
from rq import Queue,Worker
from flask_app.tests.test_infiltration import inputs

@pytest.mark.skipif(not os.environ.get('RUN_INFILTRATION_RQ'),reason='需要隔离 Redis 队列')
def test_infiltration_batch_rq(tmp_path,monkeypatch):
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
        project=Project(name='队列浸润验收');db.session.add(project);db.session.flush()
        for kind,path in [('profile',profile),('deconvolution',deconv)]:
            db.session.add(ProjectAsset(project_id=project.id,asset_type=kind,storage_path=str(path),original_name=path.name,size=path.stat().st_size,metadata_json={'asset_set':'test'}))
        db.session.commit()
        result=app.test_client().post('/api/script-hub/batches',json={'project_id':project.id,'asset_set':'test','items':[{'module':'immune-infiltration','payload':{'group_field':'group','cell_columns':['T cells','B cells'],'score_type':'absolute'}}]})
        assert result.status_code==202,result.json
        parent_id=result.json['job_id'];db.session.remove();db.engine.dispose()
        try:
            Worker([queue],connection=connection).work(burst=True,with_scheduler=False,logging_level='WARNING')
            db.session.remove();parent=get_background_job_service().get_job(parent_id)
            assert parent['status']=='completed',parent
            child=get_background_job_service().get_job(parent['payload']['items'][0]['job_id'])
            assert child['status']=='completed',child
            assert child['result']['result_id']=='synthetic-result'
            assert child['result']['metadata']['score_type']=='absolute'
            response=app.test_client().get(child['result']['zip_url'])
            assert response.status_code==200 and len(response.data)>100
        finally:
            queue.delete(delete_jobs=True);db.session.remove();db.drop_all()
