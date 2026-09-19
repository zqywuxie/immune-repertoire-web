"""Real isolated Redis/RQ worker executes a complete synthetic batch."""
import importlib
import os
import uuid
from pathlib import Path
import pandas as pd
from redis import Redis
from rq import Queue, Worker


def test_mapped_workbook_executes_real_profile_batch(tmp_path, monkeypatch):
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
        profile=tmp_path/"profile.xlsx"
        from openpyxl import Workbook
        workbook=Workbook();workbook.active.title='说明';workbook.active.append(['请选择数据工作表'])
        sheet=workbook.create_sheet('实验数据');sheet.append(['受试者编号','group','metric'])
        for sample,group,metric in zip(['A1','A2','A3','B1','B2','B3'],['A']*3+['B']*3,[1,2,4,6,8,9]):sheet.append([sample,group,metric])
        workbook.save(profile);original=profile.read_bytes()
        db.session.add(Project(id="rq-project",name="队列合成回归"));db.session.flush()
        db.session.add(ProjectAsset(project_id="rq-project",asset_type="profile",storage_path=str(profile),original_name=profile.name,size=profile.stat().st_size,metadata_json={"asset_set":"Set1"}));db.session.commit()
        asset=ProjectAsset.query.filter_by(project_id='rq-project',asset_type='profile').one()
        prepared=app.test_client().post(f'/api/projects/rq-project/assets/{asset.id}/prepare-input',json={'sheet_name':'实验数据','identifier_column':'受试者编号'})
        assert prepared.status_code==200,prepared.json
        assert profile.read_bytes()==original
        original_asset_id=asset.id
        prepared_asset=prepared.json['input_preparation']['prepared_asset_id']
        prepared_path=db.session.get(ProjectAsset,prepared_asset).storage_path
        payload={"profile_path":str(profile),"grouptype_fields":["group"],"param_begin":"metric","param_over":"metric","selected_group_values":{"group":["A","B"]},"selected_samples_by_group":{"group":{"A":["A1","A2","A3"],"B":["B1","B2","B3"]}},"force_rerun":True}
        response=app.test_client().post("/api/script-hub/batches",json={"project_id":"rq-project","asset_set":"Set1","items":[{"module":"profile","payload":payload},{"module":"profile","payload":payload,"depends_on":[0]}]})
        assert response.status_code==202,response.json
        parent_id=response.json["job_id"]
        db.session.remove()
        db.engine.dispose()
        try:
            worker=Worker([queue],connection=connection,work_horse_killed_handler=persistent_queue.record_killed)
            worker.work(burst=True,with_scheduler=False,logging_level="WARNING")
            db.session.remove()
            parent=get_background_job_service().get_job(parent_id)
            assert parent["status"]=="completed", [(item["status"],item["error"]) for item in parent["payload"]["items"]]
            assert parent["result"]["completed_count"]==2
            assert len(queue)==0
            archive_items = []
            for item in parent["payload"]["items"]:
                child=get_background_job_service().get_job(item["job_id"])
                assert child["status"]=="completed",child
                assert child['payload']['input_assets'][0]['path']==prepared_path
                assert child['payload']['source_assets'][0]['asset_id']==original_asset_id
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
