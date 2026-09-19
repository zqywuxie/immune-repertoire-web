"""Real files and database ownership back upstream result resolution."""
from pathlib import Path
import pytest
from flask import Flask, jsonify, request
from flask_app.models.database import db, Project, ProjectAsset, AnalysisJob
from flask_app.services.analysis_artifacts import capture_input_lineage, scoped_pep_candidates, resolve_upstream_input, revalidate_job_upstream
from flask_app.exceptions import ValidationError


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import script_hub_bp
    from flask_app.routes.api_script_hub import tasks_results
    app = Flask(__name__)
    app.config.update(TESTING=True, REQUIRE_LOGIN=False, SQLALCHEMY_DATABASE_URI='sqlite:///:memory:',
                      SQLALCHEMY_TRACK_MODIFICATIONS=False, RESULTS_FOLDER=str(tmp_path/'results'))
    db.init_app(app); app.register_blueprint(script_hub_bp)
    with app.app_context():
        db.create_all()
        db.session.add(Project(id='project', name='测试项目')); db.session.flush()
        candidates = []
        for dataset in ['Set1', 'Set2']:
            source = tmp_path/f'{dataset}-profile.csv'
            source.write_text('sample,group,value\nA1,A,1\nB1,B,2\n', encoding='utf-8')
            asset = ProjectAsset(id=f'input-{dataset}', project_id='project', asset_type='profile', storage_path=str(source),
                original_name=source.name, size=source.stat().st_size, metadata_json={'asset_set':dataset})
            db.session.add(asset); db.session.flush()
            lineage = capture_input_lineage('project',[{'path':str(source),'asset_type':'profile'}],dataset)
            output = tmp_path/f'{dataset}-features.csv'
            output.write_text('Sample,Category,V1,V2\nA1,A,1,4\nB1,B,3,2\n',encoding='utf-8')
            db.session.add(AnalysisJob(id=f'job-{dataset}',job_type='script_hub',module='pep-analysis',status='completed',
                project_id='project',result={'output_base':str(tmp_path)},payload={**lineage,'input_assets':[{'path':str(source)}]}))
            candidates.append({'id':dataset,'job_id':f'job-{dataset}','cache_type':'umapin_table','usage_type':'VJ',
                'path':str(output),'status':'available','chains':['TRB'],'group_fields':['group']})
        db.session.commit()
        monkeypatch.setattr(tasks_results,'_build_pep_cache_candidates',lambda project_id:candidates)
        yield app, candidates, tmp_path
        db.session.remove(); db.drop_all()


def test_only_selected_dataset_and_real_file_reaches_inspector(artifacts):
    app, _, _ = artifacts
    client=app.test_client()
    response=client.get('/api/script-hub/pep-cache-candidates?project_id=project&asset_set=Set2&cache_type=umapin')
    assert response.status_code==200
    candidates=response.json['candidates']
    assert len(candidates)==1 and candidates[0]['job_id']=='job-Set2'
    response=client.post('/api/script-hub/umapin/inspect',json={'project_id':'project','asset_set':'Set2',
        'upstream_artifact_id':candidates[0]['id'], 'data_path':'/untrusted/override.csv'})
    assert response.status_code==200, response.json
    assert Path(response.json['data_path']).name=='Set2-features.csv'
    assert 'V1' in response.json['columns']


def test_cross_dataset_reference_is_rejected(artifacts):
    app, _, _=artifacts
    ref=scoped_pep_candidates('project','Set1','umapin')[0]['id']
    response=app.test_client().post('/api/script-hub/umapin/inspect',json={
        'project_id':'project','asset_set':'Set2','upstream_artifact_id':ref})
    assert response.status_code==400


def test_worker_rechecks_source_change_and_missing_output(artifacts):
    _, _, tmp_path=artifacts
    ref=scoped_pep_candidates('project','Set2','umapin')[0]['id']
    data={'project_id':'project','asset_set':'Set2','upstream_artifact_id':ref}
    upstream=resolve_upstream_input('umapin',data)
    job={'payload':{'upstream_input':upstream}}
    revalidate_job_upstream(job)
    source=tmp_path/'Set2-profile.csv'
    source.write_text(source.read_text()+'C1,C,999\n')
    with pytest.raises(ValidationError,match='修改'):
        revalidate_job_upstream(job)
    (tmp_path/'Set2-features.csv').unlink()
    assert scoped_pep_candidates('project','Set2','umapin')[0]['status']=='unavailable'


def test_failed_source_and_unknown_legacy_source_not_selected(artifacts):
    _, candidates, _=artifacts
    db.session.get(AnalysisJob,'job-Set2').status='failed';db.session.commit()
    assert scoped_pep_candidates('project','Set2','umapin')[0]['status']=='unavailable'
    candidates.append({**candidates[0],'job_id':'unknown','id':'legacy'})
    result=scoped_pep_candidates('project','Set1','umapin')
    assert any(item['status']=='unavailable' and '无法确认' in item['reason'] for item in result)


def test_multiple_results_require_an_explicit_selection(artifacts):
    _, candidates, tmp_path=artifacts
    other=tmp_path/'another.csv';other.write_text('Sample,Category,V1\nA1,A,2\n')
    candidates.append({**candidates[1],'id':'other','path':str(other)})
    with pytest.raises(ValidationError,match='请选择'):
        resolve_upstream_input('umapin',{'project_id':'project','asset_set':'Set2'})
