"""Sample aliases must reach real analysis inputs without merging samples."""
import csv
from pathlib import Path

import pandas as pd
import pytest

from flask_app.exceptions import ValidationError
from flask_app.tests.test_profile_workflow import profile_app


@pytest.fixture
def mapping_project(profile_app):
    from flask_app.models.database import Project, db
    from flask_app.routes.api_projects import project_api_bp
    profile_app.register_blueprint(project_api_bp)
    project = Project(name="样本编号对应回归")
    db.session.add(project)
    db.session.commit()
    return project


def register(project, kind, path):
    from flask_app.models.database import ProjectAsset, db
    asset = ProjectAsset(project_id=project.id, asset_type=kind, storage_path=str(path),
                         original_name=path.name, size=path.stat().st_size, metadata_json={"asset_set": "Set2"})
    db.session.add(asset)
    db.session.commit()
    return asset


ALIASES = [{"source_sample": "RNA-001", "target_sample": "001"},
           {"source_sample": "RNA-002", "target_sample": "002"}]


@pytest.mark.parametrize("kind,content,identifier,orientation,expected", [
    ("profile", "编号,group,metric\nRNA-001,A,1.2500\nRNA-002,B,2.300\n003,B,5\n", "编号", "genes_are_rows",
     [["sample", "group", "metric"], ["001", "A", "1.2500"], ["002", "B", "2.300"], ["003", "B", "5"]]),
    ("deconvolution", "Mixture,T cells,B cells\nRNA-001,0.200,0.800\nRNA-002,0.100,0.900\n003,0.3,0.7\n", "Mixture", "genes_are_rows",
     [["sample", "T cells", "B cells"], ["001", "0.200", "0.800"], ["002", "0.100", "0.900"], ["003", "0.3", "0.7"]]),
    ("transcriptome", "symbol,RNA-001,RNA-002,003\nG1,1.2500,2.300,5\n", "symbol", "genes_are_rows",
     [["Gene", "001", "002", "003"], ["G1", "1.2500", "2.300", "5"]]),
    ("transcriptome", "sample,G1\nRNA-001,1.25\nRNA-002,2.3\n003,5\n", "sample", "samples_are_rows",
     [["Gene", "001", "002", "003"], ["G1", "1.25", "2.3", "5.0"]]),
])
def test_mapped_rows_and_columns_are_registered_and_used(profile_app, mapping_project, tmp_path, kind, content, identifier, orientation, expected):
    from flask_app.services.input_preparation import analysis_input_path
    from flask_app.routes.api_script_hub._common import _request_registered_assets
    source = tmp_path / "original.csv"
    source.write_text(content, encoding="utf-8")
    original = source.read_bytes()
    asset = register(mapping_project, kind, source)
    url = f"/api/projects/{mapping_project.id}/assets/{asset.id}"
    client = profile_app.test_client()
    response = client.post(f"{url}/prepare-input", json={"identifier_column": identifier,
                           "orientation": orientation, "sample_mappings": ALIASES})
    assert response.status_code == 200, response.json
    prepared = Path(analysis_input_path(asset))
    with prepared.open(encoding="utf-8", newline="") as stream:
        assert list(csv.reader(stream)) == expected
    selection = _request_registered_assets({"project_id": mapping_project.id, "asset_set": "Set2"})
    assert selection[f"{kind}_path"] == str(prepared)
    restored = client.post(f"{url}/input-schema", json={})
    assert restored.status_code == 200
    assert restored.json["input_preparation"]["sample_mappings"] == ALIASES
    assert source.read_bytes() == original


@pytest.mark.parametrize("entries,match", [
    ({"RNA-001": "001"}, "映射列表"),
    ([{"source_sample": "RNA-001", "target_sample": ""}], "原编号和统一编号"),
    ([{"source_sample": "RNA-001", "target_sample": "001"}, {"source_sample": "RNA-001", "target_sample": "003"}], "一对一"),
    ([{"source_sample": "RNA-001", "target_sample": "001"}, {"source_sample": "RNA-002", "target_sample": "001"}], "一对一"),
    ([{"source_sample": "typo", "target_sample": "001"}], "不在所选数据"),
    ([{"source_sample": "RNA-001", "target_sample": "RNA-002"}], "重复样本编号"),
])
def test_invalid_sample_correspondence_does_not_replace_preparation(profile_app, mapping_project, tmp_path, entries, match):
    from flask_app.models.database import ProjectAsset
    from flask_app.services.input_preparation import prepare_table, analysis_input_path
    source = tmp_path / "profile.csv"
    source.write_text("sample,group\nRNA-001,A\nRNA-002,B\n", encoding="utf-8")
    original = source.read_bytes()
    asset = register(mapping_project, "profile", source)
    options = {"identifier_column": "sample", "sample_mappings": ALIASES}
    previous = prepare_table(asset, options, tmp_path / "projects")
    previous_path = analysis_input_path(asset)
    with pytest.raises(ValidationError, match=match):
        prepare_table(asset, {**options, "sample_mappings": entries}, tmp_path / "projects")
    assert analysis_input_path(asset) == previous_path
    assert asset.metadata_json["input_preparation"] == previous
    assert ProjectAsset.query.filter_by(project_id=mapping_project.id, asset_type="prepared_input").count() == 1
    assert source.read_bytes() == original
    assert list(Path(previous_path).parent.glob("*.csv")) == [Path(previous_path)]


@pytest.mark.parametrize("orientation,content,identifier", [
    ("genes_are_rows", "Gene,RNA-001,002\nG1,1,2\n", "Gene"),
    ("samples_are_rows", "sample,G1\nRNA-001,1\n002,2\n", "sample"),
])
def test_expression_alias_cannot_overwrite_unmapped_sample(profile_app, mapping_project, tmp_path, orientation, content, identifier):
    from flask_app.services.input_preparation import prepare_table
    source = tmp_path / "expression.csv"
    source.write_text(content, encoding="utf-8")
    asset = register(mapping_project, "transcriptome", source)
    with pytest.raises(ValidationError, match="重复"):
        prepare_table(asset, {"identifier_column": identifier, "orientation": orientation,
                      "sample_mappings": [{"source_sample": "RNA-001", "target_sample": "002"}]}, tmp_path / "projects")


def test_mapping_scans_beyond_preview_and_rejects_stale_queued_reference(profile_app, mapping_project, tmp_path):
    from flask_app.services.input_preparation import prepare_table, analysis_input_path, revalidate_prepared_sources
    from flask_app.services.analysis_artifacts import capture_input_lineage
    source = tmp_path / "profile.csv"
    source.write_text("sample,group,value\n" + "".join(f"S{i:04d},A,{i}\n" for i in range(5101)), encoding="utf-8")
    asset = register(mapping_project, "profile", source)
    options = {"identifier_column": "sample", "sample_mappings": [{"source_sample": "S5100", "target_sample": "001"}]}
    prepare_table(asset, options, tmp_path / "projects")
    prepared = analysis_input_path(asset)
    frame = pd.read_csv(prepared, dtype={"sample": str})
    assert frame.iloc[-1].to_dict() == {"sample": "001", "group": "A", "value": 5100}
    job = {"payload": capture_input_lineage(mapping_project.id, [{"asset_type": "profile", "path": prepared}], "Set2")}
    revalidate_prepared_sources(job)
    prepare_table(asset, {**options, "sample_mappings": [{"source_sample": "S5100", "target_sample": "002"}]}, tmp_path / "projects")
    with pytest.raises(ValidationError, match="映射已改变"):
        revalidate_prepared_sources(job)
    assert Path(prepared).is_file()


def test_profile_aliases_reach_real_pep_group_output(profile_app, mapping_project, tmp_path):
    from flask_app.services.input_preparation import prepare_table
    from flask_app.services.pep_analysis_service import PepAnalysisService
    from flask_app.routes.api_script_hub._common import _profile_path_from_request
    samples = [f"{i:03d}" for i in range(1, 7)]
    source = tmp_path / "profile.csv"
    pd.DataFrame({"sample": [f"RNA-{sample}" for sample in samples], "group": ["A"] * 3 + ["B"] * 3}).to_csv(source, index=False)
    asset = register(mapping_project, "profile", source)
    aliases = [{"source_sample": f"RNA-{sample}", "target_sample": sample} for sample in samples]
    prepare_table(asset, {"identifier_column": "sample", "sample_mappings": aliases}, tmp_path / "projects")
    pep = tmp_path / "pep"
    pep.mkdir()
    for index, sample in enumerate(samples):
        pd.DataFrame({"CDR3(pep)": ["CASSA", "CASSB"], "V": ["TRBV1", "TRBV2"],
                      "J": ["TRBJ1", "TRBJ2"], "copy": [index + 1, 9 - index]}).to_csv(pep / f"{sample}__TRB.csv", index=False)
    prepared = _profile_path_from_request({"project_id": mapping_project.id, "asset_set": "Set2"}, "profile_path")
    report = PepAnalysisService(output_parent=tmp_path / "results").generate_report(
        pep_data_dir=str(pep), profile_path=prepared, group_fields=["group"], selected_chains=["TRB"], optional_steps=set())
    output = pd.read_csv(next(report.output_base.rglob("df_VJ_all.csv")))
    groups = dict(zip(output["sample"], output["Category"]))
    assert groups == {f"{sample}__TRB.csv": "A" if index < 3 else "B" for index, sample in enumerate(samples)}
    assert pd.read_csv(source, dtype=str)["sample"].tolist() == [f"RNA-{sample}" for sample in samples]


def test_deconvolution_aliases_reach_real_api_analysis_and_download(profile_app, mapping_project, tmp_path, monkeypatch):
    import numpy as np
    from flask_app.tests.test_infiltration import inputs
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.services.input_preparation import prepare_table
    profile, deconv = inputs(tmp_path)
    frame = pd.read_csv(deconv, dtype={"Mixture": str})
    aliases = [{"source_sample": f"CIB-{sample}", "target_sample": sample} for sample in frame["Mixture"]]
    frame["Mixture"] = "CIB-" + frame["Mixture"]
    frame.to_csv(deconv, index=False)
    original = deconv.read_bytes()
    register(mapping_project, "profile", profile)
    asset = register(mapping_project, "deconvolution", deconv)
    prepare_table(asset, {"identifier_column": "Mixture", "sample_mappings": aliases}, tmp_path / "projects")
    monkeypatch.setattr(shared._script_executor, "submit", lambda fn, task, **kwargs: fn(task, **kwargs))
    monkeypatch.setattr("flask_app.services.mongo_service.save_result", lambda **kwargs: "synthetic-result")
    data = {"project_id": mapping_project.id, "asset_set": "Set2", "group_field": "group", "score_type": "relative", "cell_columns": ["T cells", "B cells"]}
    client = profile_app.test_client()
    inspection = client.post("/api/script-hub/immune-infiltration/inspect", json=data)
    assert inspection.status_code == 200, inspection.json
    assert inspection.json["group_counts"] == {"A": 4, "B": 4}
    response = client.post("/api/script-hub/immune-infiltration/run", json=data)
    assert response.status_code == 200, response.json
    task = shared._get_task_state(response.json["task_id"])
    assert task["status"] == "completed", task
    matrix = pd.read_csv(next(Path(task["result"]["output_base"]).rglob("panel_A_shift_normalized_matrix.csv")), dtype={"sample": str}).sort_values("sample")
    assert matrix["sample"].tolist() == [f"{i:03d}" for i in range(8)]
    np.testing.assert_allclose(matrix["raw_T cells"], np.arange(1, 9) / 10)
    assert client.get(task["result"]["zip_url"]).status_code == 200
    assert deconv.read_bytes() == original



def test_batch_scoped_mapping_restores_and_checks_selected_analysis_identity(profile_app, mapping_project, tmp_path):
    from flask_app.services.input_preparation import analysis_input_path
    from flask_app.services.input_quality import validate_analysis_inputs
    source = tmp_path / 'profile-batches.csv'
    source.write_text('编号,batch,group,value\nRNA-001,批次甲,A,1.2500\nRNA-001,批次乙,B,2.300\n', encoding='utf-8')
    original = source.read_bytes()
    asset = register(mapping_project, 'profile', source)
    aliases = [
        {'source_sample': 'RNA-001', 'target_sample': '001', 'source_batch': '批次甲'},
        {'source_sample': 'RNA-001', 'target_sample': '002', 'source_batch': '批次乙'},
    ]
    client = profile_app.test_client()
    url = f'/api/projects/{mapping_project.id}/assets/{asset.id}'
    options = {'identifier_column': '编号', 'batch_field': 'batch', 'sample_mappings': aliases}
    response = client.post(f'{url}/prepare-input', json=options)
    assert response.status_code == 200, response.json
    prepared = analysis_input_path(asset)
    with Path(prepared).open(encoding='utf-8', newline='') as stream:
        assert list(csv.reader(stream)) == [
            ['sample', 'batch', 'group', 'value'], ['001', '批次甲', 'A', '1.2500'], ['002', '批次乙', 'B', '2.300'],
        ]
    restored = client.post(f'{url}/input-schema', json={}).json['input_preparation']
    assert restored['batch_field'] == 'batch'
    assert restored['sample_mappings'] == aliases
    # Different batches may intentionally retain the same normalized sample ID.
    aliases[1]['target_sample'] = '001'
    assert client.post(f'{url}/prepare-input', json=options).status_code == 200
    inputs = [{'asset_type': 'profile', 'path': analysis_input_path(asset)}]
    quality = validate_analysis_inputs(inputs, {'batch_field': 'batch'})
    assert quality['inputs'][0]['sample_count'] == 2
    assert quality['inputs'][0]['batch_count'] == 2
    with pytest.raises(ValidationError, match='批次字段'):
        validate_analysis_inputs(inputs)
    inspection = client.post('/api/script-hub/data-selection/inspect', json={
        'project_id': mapping_project.id, 'asset_set': 'Set2',
    })
    assert inspection.status_code == 200, inspection.json
    report = inspection.json['input_quality']['inputs'][0]
    assert report['sample_count'] == 2
    assert report['batch_count'] == 2
    assert report['status'] == 'checked'
    # Batch scope belongs to the selected source, not all profiles in the project.
    plain = tmp_path / 'plain-profile.csv'
    plain.write_text('sample,group\n003,A\n004,B\n', encoding='utf-8')
    register(mapping_project, 'profile', plain)
    inspection = client.post('/api/script-hub/data-selection/inspect', json={
        'project_id': mapping_project.id, 'asset_set': 'Set2', 'profile_path': str(plain),
    })
    assert inspection.status_code == 200, inspection.json
    report = inspection.json['input_quality']['inputs'][0]
    assert report['status'] == 'checked'
    assert report['sample_count'] == 2
    assert 'batch_field' not in report
    assert source.read_bytes() == original


@pytest.mark.parametrize('options,match', [
    ({'batch_field': 'missing'}, '实际数据列'),
    ({'batch_field': 'sample'}, '实际数据列'),
    ({'batch_field': ['batch']}, '有效的样本批次字段'),
    ({'sample_mappings': [{'source_sample': 'RNA-001', 'target_sample': '001', 'source_batch': '批次甲'}]}, '先选择样本批次字段'),
    ({'batch_field': 'batch', 'sample_mappings': [{'source_sample': 'RNA-001', 'target_sample': '001'}]}, '原批次'),
    ({'batch_field': 'batch', 'sample_mappings': [{'source_sample': 'RNA-001', 'target_sample': '001', 'source_batch': '不存在批次'}]}, '不在所选数据'),
    ({'batch_field': 'batch', 'sample_mappings': [
        {'source_sample': 'RNA-001', 'target_sample': '001', 'source_batch': '批次甲'},
        {'source_sample': 'RNA-002', 'target_sample': '001', 'source_batch': '批次甲'},
    ]}, '一对一'),
    ({'batch_field': 'batch', 'sample_mappings': [{'source_sample': 'RNA-001', 'target_sample': 'RNA-002', 'source_batch': '批次甲'}]}, '重复样本编号'),
])
def test_batch_mapping_rejects_ambiguous_or_wrong_scope(profile_app, mapping_project, tmp_path, options, match):
    from flask_app.models.database import ProjectAsset
    from flask_app.services.input_preparation import prepare_table
    source = tmp_path / 'profile.csv'
    source.write_text('sample,batch,group\nRNA-001,批次甲,A\nRNA-002,批次甲,A\nRNA-001,批次乙,B\n', encoding='utf-8')
    asset = register(mapping_project, 'profile', source)
    with pytest.raises(ValidationError, match=match):
        prepare_table(asset, {'identifier_column': 'sample', **options}, tmp_path / 'projects')
    assert 'input_preparation' not in asset.metadata_json
    assert ProjectAsset.query.filter_by(project_id=mapping_project.id, asset_type='prepared_input').count() == 0


def test_batch_field_alone_preserves_duplicates_across_batches_and_rejects_duplicates_inside_one_batch(profile_app, mapping_project, tmp_path):
    from flask_app.services.input_preparation import prepare_table, analysis_input_path
    source = tmp_path / 'profile.csv'
    source.write_text('编号,batch,group\n001,批次甲,A\n001,批次乙,B\n', encoding='utf-8')
    asset = register(mapping_project, 'profile', source)
    prepare_table(asset, {'identifier_column': '编号', 'batch_field': 'batch'}, tmp_path / 'projects')
    assert pd.read_csv(analysis_input_path(asset), dtype=str)['sample'].tolist() == ['001', '001']
    invalid = tmp_path / 'same-batch.csv'
    invalid.write_text('编号,batch,group\n001,批次甲,A\n001,批次甲,B\n', encoding='utf-8')
    bad = register(mapping_project, 'profile', invalid)
    with pytest.raises(ValidationError, match='重复样本编号'):
        prepare_table(bad, {'identifier_column': '编号', 'batch_field': 'batch'}, tmp_path / 'projects')


def test_batch_scope_is_not_silently_applied_to_expression(profile_app, mapping_project, tmp_path):
    from flask_app.services.input_preparation import prepare_table
    source = tmp_path / 'expression.csv'
    source.write_text('Gene,batch,001\nG1,1,2\n', encoding='utf-8')
    asset = register(mapping_project, 'transcriptome', source)
    with pytest.raises(ValidationError, match='仅用于样本指标表'):
        prepare_table(asset, {'identifier_column': 'Gene', 'batch_field': 'batch'}, tmp_path / 'projects')


def test_batch_scoped_profile_aliases_reach_real_pep_results(profile_app, mapping_project, tmp_path):
    from flask_app.services.input_preparation import prepare_table
    from flask_app.services.pep_analysis_service import PepAnalysisService
    from flask_app.routes.api_script_hub._common import _profile_path_from_request
    samples = ['001', '002', '003']
    batches = ['批次甲', '批次乙']
    source = tmp_path / 'profile.csv'
    rows, aliases = [], []
    pep = tmp_path / 'pep'
    for batch, group in zip(batches, ['A', 'B']):
        folder = pep / batch / 'TRB'
        folder.mkdir(parents=True)
        for index, sample in enumerate(samples):
            rows.append({'编号': f'RNA-{sample}', 'batch': batch, 'group': group})
            aliases.append({'source_sample': f'RNA-{sample}', 'target_sample': sample, 'source_batch': batch})
            pd.DataFrame({'CDR3(pep)': ['CASSA', 'CASSB'], 'V': ['TRBV1', 'TRBV2'], 'J': ['TRBJ1', 'TRBJ2'],
                          'copy': [index + 1, 9 - index]}).to_csv(folder / f'{sample}__TRB.csv', index=False)
    pd.DataFrame(rows)[['group', 'batch', '编号']].to_csv(source, index=False)
    asset = register(mapping_project, 'profile', source)
    prepare_table(asset, {'identifier_column': '编号', 'batch_field': 'batch', 'sample_mappings': aliases}, tmp_path / 'projects')
    prepared = _profile_path_from_request({'project_id': mapping_project.id, 'asset_set': 'Set2'}, 'profile_path')
    assert pd.read_csv(prepared, nrows=0).columns[0] == 'sample'
    report = PepAnalysisService(output_parent=tmp_path / 'results').generate_report(
        pep_data_dir=str(pep), profile_path=prepared, group_fields=['group'], batch_field='batch', selected_chains=['TRB'], optional_steps=set())
    output = pd.read_csv(next(report.output_base.rglob('df_VJ_all.csv')))
    assert dict(zip(output['sample'], output['Category'])) == {
        f'{batch}::{sample}': group for batch, group in zip(batches, ['A', 'B']) for sample in samples
    }
    assert len(output) == 6

@pytest.mark.parametrize('aliases, expected', [
    ([], ['RNA-001', 'RNA-002']),
    (ALIASES, ['RNA-001', 'RNA-002']),
])
def test_preparation_updates_management_coverage_and_registration_with_original_ids(profile_app, mapping_project, tmp_path, aliases, expected):
    from flask_app.services.input_validation_cache import validate_uploaded_asset
    source = tmp_path / 'custom-identifiers.csv'
    source.write_text('编号,group,metric\nRNA-001,A,1\nRNA-002,B,2\n', encoding='utf-8')
    original = source.read_bytes()
    asset = register(mapping_project, 'profile', source)
    import hashlib
    from flask_app.models.database import db
    from flask_app.services.input_validation_cache import snapshot
    asset.metadata_json = {**asset.metadata_json, 'content_version':hashlib.sha256(original).hexdigest(),
                           'upload_snapshot':snapshot(source)}
    db.session.commit()
    validate_uploaded_asset(asset)
    assert asset.metadata_json['validation']['status'] == 'needs_mapping'
    client = profile_app.test_client()
    url = f'/api/projects/{mapping_project.id}/assets/{asset.id}'
    response = client.post(url + '/prepare-input', json={'identifier_column':'编号', 'sample_mappings':aliases})
    assert response.status_code == 200, response.json
    coverage = client.get(f'/api/projects/{mapping_project.id}/input-samples?asset_set=Set2').json
    assert [row['sample_id'] for row in coverage['samples']] == expected
    assert coverage['unresolved'] == []
    registration = client.post(f'/api/projects/{mapping_project.id}/samples/registration', json={
        'asset_set':'Set2', 'sample_id':'RNA-001', 'fields':{'institution':'登记机构'}})
    assert registration.status_code == 200, registration.json
    if aliases:
        with pytest.raises(ValidationError, match='没有识别到此样本'):
            client.post(f'/api/projects/{mapping_project.id}/samples/registration', json={
                'asset_set':'Set2', 'sample_id':'001', 'fields':{'institution':'不能替代原编号'}})
    validate_uploaded_asset(asset)
    assert asset.metadata_json['validation']['summary']['inputs'][0]['samples'] == expected
    assert client.delete(url + '/prepare-input').status_code == 200
    assert asset.metadata_json['validation']['status'] == 'needs_mapping'
    assert source.read_bytes() == original


def test_prepared_management_coverage_uses_selected_worksheet(profile_app, mapping_project, tmp_path):
    source = tmp_path / 'selected-sheet.xlsx'
    with pd.ExcelWriter(source) as workbook:
        pd.DataFrame({'编号':['wrong'], 'group':['A']}).to_excel(workbook, sheet_name='忽略', index=False)
        pd.DataFrame({'编号':['001','002'], 'group':['A','B']}).to_excel(workbook, sheet_name='实际输入', index=False)
    asset = register(mapping_project, 'profile', source)
    client = profile_app.test_client()
    response = client.post(f'/api/projects/{mapping_project.id}/assets/{asset.id}/prepare-input', json={
        'identifier_column':'编号', 'sheet_name':'实际输入'})
    assert response.status_code == 200, response.json
    from flask_app.services.input_validation_cache import validate_uploaded_asset
    validate_uploaded_asset(asset)
    assert asset.metadata_json['validation']['summary']['inputs'][0]['samples'] == ['001','002']


def test_actual_profile_results_retain_dataset_scope_in_sql_and_mongo(profile_app, mapping_project, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.models.database import ProjectAsset, db
    saved = []
    def save_result(**kwargs):
        saved.append(kwargs)
        return 'synthetic-result-' + str(len(saved))
    monkeypatch.setattr('flask_app.services.mongo_service.save_result', save_result)
    monkeypatch.setattr(shared._script_executor, 'submit', lambda fn, task, **kwargs: fn(task, **kwargs))
    client = profile_app.test_client()
    for dataset, offset in [('甲',0), ('乙',100)]:
        source = tmp_path / (dataset + '.csv')
        source.write_text('sample,group,metric\n001,A,'+str(1+offset)+'\n002,A,'+str(2+offset)+'\n003,B,'+str(8+offset)+'\n004,B,'+str(9+offset)+'\n', encoding='utf-8')
        asset = register(mapping_project, 'profile', source)
        asset.metadata_json = {'asset_set':dataset}
        db.session.commit()
        response = client.post('/api/script-hub/profile/run', json={'project_id':mapping_project.id,
            'asset_set':dataset, 'datapoint_path':str(source), 'grouptype_fields':['group'],
            'group_order':'A,B', 'param_begin':'metric', 'param_over':'metric', 'force_rerun':True})
        assert response.status_code == 200, response.json
        task = shared._get_task_state(response.json['task_id'])
        assert task['status'] == 'completed', task
        assert task['config_json']['asset_set'] == dataset
        assert client.get(task['result']['zip_url']).status_code == 200
    results = ProjectAsset.query.filter_by(project_id=mapping_project.id, asset_type='processed_result').all()
    assert {asset.metadata_json['asset_set'] for asset in results} == {'甲','乙'}
    assert {item['config_json']['asset_set'] for item in saved} == {'甲','乙'}
    assert {item['metadata_json']['asset_set'] for item in saved} == {'甲','乙'}
