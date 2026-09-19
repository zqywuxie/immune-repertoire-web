from unittest.mock import Mock
import pytest
from flask_app.tests.test_persistent_queue import application
from flask_app.models.database import Project, AnalysisJob, db
from flask_app.services.analysis_artifacts import revalidate_job_upstream
from flask_app.services.background_job_service import get_background_job_service
from flask_app.exceptions import ValidationError


def test_project_deg_binding_uses_registered_results_and_rechecks_changes(application, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import enrichment
    application.config['REQUIRE_LOGIN'] = False
    directory = tmp_path/'result'/'DEG'/'A_vs_B'
    directory.mkdir(parents=True)
    table = directory/'DEG_A_vs_B.csv'
    table.write_text('gene_symbol,significant,t\nTP53,Up,4.5\nEGFR,Down,-3.5\n')
    db.session.add(Project(id='project', name='合成项目'));db.session.flush()
    source = AnalysisJob(id='source-deg',job_type='script_hub',module='volcano',status='completed',project_id='project',
        payload={'asset_set':'Set1'},result={'output_base':str(tmp_path/'result'), 'metadata':{'input_mode':'expression','pvalue_threshold':0.01}})
    db.session.add(source);db.session.commit()
    executor = Mock()
    monkeypatch.setattr(enrichment, '_script_executor', executor)
    client = application.test_client()
    response = client.get('/api/script-hub/go-kegg-enrichment/sources?project_id=project&asset_set=Set1')
    assert response.status_code == 200, response.json
    assert response.json['candidates'][0]['status'] == 'available'
    payload = {'project_id':'project','asset_set':'Set1','input_mode':'deg','upstream_artifact_id':'source-deg:deg',
               'deg_directory':'/untrusted/override','expression_path':'/untrusted/input.csv','force_rerun':True}
    wrong = client.post('/api/script-hub/go-kegg-enrichment/run',json={**payload,'asset_set':'Set2'})
    assert wrong.status_code == 400
    response = client.post('/api/script-hub/go-kegg-enrichment/run',json=payload)
    assert response.status_code == 200, response.json
    args = executor.submit.call_args.kwargs
    assert args['deg_directory'] == str(directory.parent)
    assert args['expression_path'] == ''
    assert args['differential_metadata']['pvalue_threshold'] == 0.01
    job = get_background_job_service().get_job(response.json['task_id'])
    assert job['payload']['upstream_input']['source_job_id'] == source.id
    revalidate_job_upstream(job)
    table.write_text(table.read_text()+'NEW,Up,6\n')
    with pytest.raises(ValidationError, match='差异表达结果已改变'):
        revalidate_job_upstream(job)
    from flask_app.services.analysis_batch_service import validate_batch, bind_batch_upstream
    plan = validate_batch({'items':[
        {'module':'volcano','payload':{'input_mode':'expression'}},
        {'module':'go-kegg-enrichment','payload':{},'upstream_from':0}]})
    assert plan[1]['depends_on'] == [0]
    plan[0].update(status='completed',job_id='source-deg')
    bound = {'expression_path':'/wrong','upstream_artifact_id':'old:deg'}
    bind_batch_upstream({'project_id':'project','payload':{'asset_set':'Set1','items':plan}},plan[1],bound)
    assert bound['upstream_artifact_id'] == 'source-deg:deg'
    assert bound['input_mode'] == 'deg' and 'expression_path' not in bound
    with pytest.raises(ValidationError):
        validate_batch({'items':[
            {'module':'volcano','payload':{'input_mode':'usage'}},
            {'module':'go-kegg-enrichment','payload':{},'upstream_from':0}]})
    source.status='failed';db.session.commit()
    assert client.post('/api/script-hub/go-kegg-enrichment/run',json=payload).status_code == 400
