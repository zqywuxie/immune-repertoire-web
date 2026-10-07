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


def test_ungrouped_vj_source_is_unavailable_only_for_grouped_analyses(artifacts):
    app, candidates, tmp_path = artifacts
    raw = candidates[1]
    raw.update(cache_type='vj_usage', available_for=['volcano', 'umapin', 'ml-analysis'])
    Path(raw['path']).write_text('sample,V1,V2\nA1,1,4\nB1,3,2\n', encoding='utf-8')
    original = Path(raw['path']).read_bytes()
    general = scoped_pep_candidates('project', 'Set2')[0]
    assert general['status'] == 'available'
    assert 'volcano' not in general['available_for']
    assert 'umapin' not in general['available_for']
    assert 'ml-analysis' in general['available_for']
    rejected = app.test_client().get('/api/script-hub/pep-cache-candidates?project_id=project&asset_set=Set2&cache_type=volcano')
    assert rejected.status_code == 200
    source = rejected.json['candidates'][0]
    assert source['status'] == 'unavailable' and '分组' in source['reason']
    with pytest.raises(ValidationError, match='分组'):
        resolve_upstream_input('volcano', {'project_id':'project', 'asset_set':'Set2',
            'input_mode':'usage', 'upstream_artifact_id':source['artifact_id']})
    ml = resolve_upstream_input('ml-analysis', {'project_id':'project', 'asset_set':'Set2',
        'mode':'vj', 'upstream_artifact_id':source['artifact_id']})
    assert ml['path'] == str(Path(raw['path']).resolve())
    assert Path(raw['path']).read_bytes() == original


@pytest.mark.parametrize('column', ['Category', 'category', 'group', 'therapy', 'disease'])
def test_vj_group_headers_match_real_inspection_and_worker_revalidation(artifacts, column):
    from flask_app.services.volcano_service import VolcanoService
    _, candidates, _ = artifacts
    raw = candidates[1]
    raw.update(cache_type='vj_usage', available_for=['ml-analysis'])
    path = Path(raw['path'])
    path.write_text(f'sample,{column},V1,V2\nA1,01,1,4\nB1,1,3,2\n', encoding='utf-8')
    source = scoped_pep_candidates('project', 'Set2', 'volcano')[0]
    assert source['status'] == 'available' and 'volcano' in source['available_for']
    inspected = VolcanoService.prepare_usage_inputs(str(path))
    assert inspected['groups'] == ['01', '1']
    ref = resolve_upstream_input('volcano', {'project_id':'project', 'asset_set':'Set2',
        'input_mode':'usage', 'upstream_artifact_id':source['artifact_id']})
    revalidate_job_upstream({'payload':{'upstream_input':ref}})
    path.write_text('sample,V1,V2\nA1,1,4\nB1,3,2\n', encoding='utf-8')
    with pytest.raises(ValidationError, match='分组'):
        revalidate_job_upstream({'payload':{'upstream_input':ref}})


def test_vj_directory_checks_every_selected_summary_and_honors_worker_priority(artifacts):
    import gzip
    from flask_app.services.volcano_service import VolcanoService
    _, candidates, tmp_path = artifacts
    folder = tmp_path / 'usage' / '1VJusage'
    folder.mkdir(parents=True)
    good = 'sample,Category,V1\nA1,A,1\nB1,B,2\n'
    (folder/'TRB.csv').write_text(good, encoding='utf-8')
    (folder/'df_1.csv').write_text(good, encoding='utf-8')
    with gzip.open(folder/'df_2.csv.gz', 'wt', encoding='utf-8') as stream:
        stream.write('sample,V1\nA1,1\nB1,2\n')
    candidates[1].update(cache_type='vj_usage', path=str(folder), available_for=['volcano'])
    source = scoped_pep_candidates('project', 'Set2', 'volcano')[0]
    assert source['status'] == 'unavailable'
    # A valid chain file cannot override invalid df* files selected by the worker.
    with pytest.raises(ValueError):
        VolcanoService.prepare_usage_inputs(str(folder))
    with gzip.open(folder/'df_2.csv.gz', 'wt', encoding='utf-8') as stream:
        stream.write(good)
    assert scoped_pep_candidates('project', 'Set2', 'volcano')[0]['status'] == 'available'
    assert len(VolcanoService.prepare_usage_inputs(str(folder))['tables']) == 2


def test_vj_legacy_directory_uses_the_same_parent_summary_as_worker(artifacts):
    from flask_app.services.volcano_service import VolcanoService
    _, candidates, tmp_path = artifacts
    folder = tmp_path / 'legacy' / 'usage' / '1VJusage'
    folder.mkdir(parents=True)
    (folder/'TRB.csv').write_text('sample,V1\nA1,1\nB1,2\n', encoding='utf-8')
    summary = folder.parent / 'df_VJ_all.csv'
    summary.write_text('sample,Category,V1\nA1,01,1\nB1,1,2\n', encoding='utf-8')
    candidates[1].update(cache_type='vj_usage', path=str(folder))
    source = scoped_pep_candidates('project', 'Set2', 'volcano')[0]
    assert source['status'] == 'available' and 'volcano' in source['available_for']
    assert VolcanoService.prepare_usage_inputs(str(folder))['groups'] == ['01', '1']


@pytest.mark.parametrize('sample_header', ['Sample', 'SAMPLE'])
def test_vj_sample_header_case_preserves_original_ids_in_listing_and_inspection(artifacts, sample_header):
    from flask_app.services.volcano_service import VolcanoService
    _, candidates, _ = artifacts
    raw = candidates[1]
    raw.update(cache_type='vj_usage')
    Path(raw['path']).write_text(f'{sample_header},Category,V1\n001,01,1\n010,1,2\n', encoding='utf-8')
    source = scoped_pep_candidates('project', 'Set2', 'volcano')[0]
    assert source['status'] == 'available'
    inspected = VolcanoService.prepare_usage_inputs(source['path'])
    assert inspected['samples'] == ['001', '010']
    assert inspected['groups'] == ['01', '1']


def test_legacy_ungrouped_usage_reports_chinese_input_error(tmp_path):
    from flask_app.services.volcano_service import VolcanoService
    source = tmp_path/'usage.csv'
    source.write_text('sample,V1\n001,1\n', encoding='utf-8')
    with pytest.raises(ValueError, match='缺少.*分组'):
        VolcanoService.prepare_usage_inputs(str(source))


@pytest.mark.parametrize('group_header', ['Category', 'category', 'group', 'therapy', 'disease'])
def test_feature_source_accepts_actual_group_aliases_and_column_order(artifacts, group_header):
    from flask_app.services.umapin_service import UmapinService
    _, candidates, _ = artifacts
    path = Path(candidates[1]['path'])
    # The group column may follow numerical features in real exported summaries.
    path.write_text(f'Sample,V1,V2,{group_header}\n001,1,4,01\n010,3,2,1\n011,5,1,1\n', encoding='utf-8')
    original = path.read_bytes()
    inspected = UmapinService.prepare_input(data_path=str(path))
    assert inspected['category_col'] == group_header
    assert inspected['samples'].tolist() == ['001', '010', '011']
    source = scoped_pep_candidates('project', 'Set2', 'umapin')[0]
    assert source['status'] == 'available', source
    assert 'umapin' in source['available_for']
    ref = resolve_upstream_input('umapin', {'project_id':'project', 'asset_set':'Set2',
        'upstream_artifact_id':source['artifact_id']})
    revalidate_job_upstream({'payload':{'upstream_input':ref}})
    assert path.read_bytes() == original


def test_feature_directory_checks_the_worker_selected_summary_not_another_chain(artifacts):
    from flask_app.services.umapin_service import UmapinService
    _, candidates, tmp_path = artifacts
    folder = tmp_path/'features'
    folder.mkdir()
    (folder/'df_VJ_all.csv').write_text('sample,V1\n001,1\n010,2\n011,3\n', encoding='utf-8')
    (folder/'TRB.csv').write_text('sample,Category,V1\n001,01,1\n010,1,2\n011,1,3\n', encoding='utf-8')
    candidates[1]['path'] = str(folder)
    with pytest.raises(ValueError, match='分组'):
        UmapinService.prepare_input(data_path=str(folder))
    source = scoped_pep_candidates('project', 'Set2', 'umapin')[0]
    assert source['status'] == 'unavailable'
    assert 'umapin' not in source['available_for']
    # Preserve the worker's first named-summary priority even if another summary is valid.
    (folder/'df_1VJusage_all.csv').write_text((folder/'TRB.csv').read_text(), encoding='utf-8')
    assert scoped_pep_candidates('project', 'Set2', 'umapin')[0]['status'] == 'unavailable'


def test_feature_parent_summary_is_not_labeled_as_this_directory_output(artifacts):
    from flask_app.services.umapin_service import UmapinService
    _, candidates, tmp_path = artifacts
    folder = tmp_path/'legacy'/'usage'/'0VJusage'
    folder.mkdir(parents=True)
    (folder/'TRB.csv').write_text('sample,V1\n001,1\n010,2\n011,3\n', encoding='utf-8')
    summary = folder.parent/'df_VJ_all.csv'
    summary.write_text('sample,group,V1\n001,01,1\n010,1,2\n011,1,3\n', encoding='utf-8')
    candidates[1]['path'] = str(folder)
    # Keep legacy service fallback, but do not advertise a parent's weighted summary
    # as a feature table belonging to this raw clone-frequency directory.
    assert UmapinService.prepare_input(data_path=str(folder))['source'] == summary
    source = scoped_pep_candidates('project', 'Set2', 'umapin')[0]
    assert source['status'] == 'unavailable' and 'umapin' not in source['available_for']


@pytest.mark.parametrize('header', ['sample,Category', 'Category'])
def test_feature_metadata_only_table_has_no_feature_eligibility(artifacts, header):
    _, candidates, _ = artifacts
    path = Path(candidates[1]['path'])
    body = '001,01\n010,1\n011,1\n' if ',' in header else '01\n1\n1\n'
    path.write_text(header+'\n'+body, encoding='utf-8')
    source = scoped_pep_candidates('project', 'Set2', 'umapin')[0]
    assert source['status'] == 'unavailable' and 'umapin' not in source['available_for']
