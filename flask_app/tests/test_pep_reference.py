"""Compare synthetic matrices against the mounted original pipeline scripts."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pandas as pd
import pytest

from flask_app.services.pep_analysis_service import PepAnalysisService


def test_clone_tracking_normalizes_shared_cdr3_and_exports_plot_data(tmp_path):
    field_dir = tmp_path / "group"
    arranged_dir = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
    source_dir = field_dir / "Pep_shared_cate" / "Pep_shared"
    arranged_dir.mkdir(parents=True)
    source_dir.mkdir(parents=True)
    source = source_dir / "TRB.csv"
    pd.DataFrame([
        ["CDR3(pep)", "S1", "S2", "S3"],
        ["category", "A", "B", "B"],
        ["CASS1", 10, 5, 0],
        ["CASS2", 4, 0, 8],
        ["CASS3", 0, 2, 0],
    ]).to_csv(source, index=False, header=False)
    arranged = arranged_dir / "TRB.csv"
    pd.DataFrame([
        ["CDR3(pep)", "category", "A__sum", "A__count", "B__sum", "B__count", "all_num"],
        ["category", " ", " ", " ", " ", " ", " "],
        ["CASS1", "T1DM__count", 10, 1, 5, 1, 2],
        ["CASS2", "T1DM__count", 4, 1, 8, 1, 2],
        ["CASS3", "B__count", 0, 0, 2, 1, 1],
    ]).to_csv(arranged, index=False, header=False)

    images, tables = PepAnalysisService(output_parent=tmp_path / "results")._run_step9_for_group(
        ["TRB"], field_dir,
    )

    result = pd.read_csv(next(path for path in tables if path.endswith("shared_cdr3_abundance.csv")))
    assert result["cdr3"].tolist() == ["CASS1", "CASS2"]
    assert result["clone_id"].tolist() == ["C0001", "C0002"]
    assert result.loc[0, "A"] == pytest.approx(100 * 10 / 14)
    assert result.loc[1, "B"] == pytest.approx(100 * 8 / 15)
    denominators = pd.read_csv(next(path for path in tables if path.endswith("group_denominators.csv")))
    assert denominators["total_count"].tolist() == [14, 15]
    assert denominators["sample_count"].tolist() == [1, 2]
    assert len(images) == 1
    assert Path(images[0]).is_file()
    assert Path(images[0]).with_suffix(".pdf").is_file()
    assert Path(images[0]).with_suffix(".csv").is_file()


def test_clone_tracking_rejects_inconsistent_presence_counts(tmp_path):
    source = tmp_path / "source.csv"
    arranged = tmp_path / "arranged.csv"
    pd.DataFrame([
        ["CDR3(pep)", "S1", "S2"], ["category", "A", "B"], ["CASS1", 5, 4],
    ]).to_csv(source, index=False, header=False)
    pd.DataFrame([
        ["CDR3(pep)", "category", "A__sum", "A__count", "B__sum", "B__count"],
        ["category", " ", " ", " ", " ", " "], ["CASS1", "T1DM__count", 5, 0, 4, 1],
    ]).to_csv(arranged, index=False, header=False)
    with pytest.raises(ValueError, match="presence/count disagreement"):
        PepAnalysisService._prepare_clone_tracking(arranged, source)


def test_category_heatmap_payload_groups_and_normalizes_rows(tmp_path):
    arranged = tmp_path / "TRB.csv"
    pd.DataFrame([
        ["CDR3(pep)", "S1__TRB", "S2__TRB", "A__sum", "A__count", "B__sum", "B__count", "category"],
        ["category", "A", "B", " ", " ", " ", " ", " "],
        ["CASS-A", 10, 0, 10, 1, 0, 0, "A__count"],
        ["CASS-B", 0, 20, 0, 0, 20, 1, "B__count"],
        ["CASS-AB", 5, 15, 5, 1, 15, 1, "('A__count', 'B__count')"],
    ]).to_csv(arranged, index=False, header=False)

    payload = PepAnalysisService._read_cdr3_category_heatmaps(arranged, "TRB")

    assert [section["category"] for section in payload["sections"]] == [
        "('A__count', 'B__count')", "A__count", "B__count",
    ]
    assert payload["sample_groups"] == ["A", "B"]
    shared = payload["sections"][0]
    assert shared["records"][0]["cdr3"] == "CASS-AB"
    assert shared["matrix"][0] == pytest.approx([1 / 3, 1.0])


def test_category_heatmap_step_exports_each_category_and_summary(tmp_path):
    field_dir = tmp_path / "group"
    arranged_dir = field_dir / "arrage_pep" / "Pep_shared_cate" / "Pep_shared"
    arranged_dir.mkdir(parents=True)
    pd.DataFrame([
        ["CDR3(pep)", "S1__TRB", "S2__TRB", "A__sum", "A__count", "B__sum", "B__count", "category"],
        ["category", "A", "B", " ", " ", " ", " ", " "],
        ["CASS-A", 10, 0, 10, 1, 0, 0, "A__count"],
        ["CASS-B", 0, 20, 0, 0, 20, 1, "B__count"],
        ["CASS-AB", 5, 15, 5, 1, 15, 1, "('A__count', 'B__count')"],
    ]).to_csv(arranged_dir / "TRB.csv", index=False, header=False)

    paths = PepAnalysisService(output_parent=tmp_path / "results")._run_step10_for_group(["TRB"], field_dir)

    assert len(paths) == 6
    assert all(Path(path).is_file() and Path(path).suffix == ".png" for path in paths)
    assert any("single" in path for path in paths)
    assert any("two" in path for path in paths)
    assert sum("/ALL/" in path.replace("\\", "/") for path in paths) == 3


@pytest.mark.parametrize('suffix', ['__TRB.csv', '_TRB.csv', '__TRB.csv.gz'])
def test_original_category_outputs(tmp_path, suffix):
    reference = os.environ.get('REFERENCE_PIPELINE')
    if not reference:
        pytest.skip('需要只读挂载原始 pipeline 并设置 REFERENCE_PIPELINE')
    samples = ['001', '1', 'patient__A', 'missing', 'unmatched']
    names = [sample + suffix for sample in samples]
    profile = pd.DataFrame({'sample': samples[:-1], 'group': ['A', 'B', 'A', None]})
    profile_path = tmp_path / 'profile.csv'
    profile.to_csv(profile_path, index=False)
    base = tmp_path / 'outputs' / '03.UCDR3' / '1.Pep'
    usage = base / '2.Pep_shared' / 'usage'
    shared = base / '2.Pep_shared' / 'Pep_shared'
    usage.mkdir(parents=True)
    shared.mkdir(parents=True)
    pd.DataFrame({'Unnamed: 0': names, 'TRBV1': [.1,.2,.3,.4,.5], 'TRBV2': [.9,.8,.7,.6,.5]}).to_csv(usage/'TRB.csv', index=False)
    pd.DataFrame({'CDR3(pep)': ['CASSA','CASSB'], **{name:[i+1,i+2] for i,name in enumerate(names)}}).to_csv(shared/'TRB.csv', index=False)
    config = tmp_path / 'config.json'
    config.write_text(json.dumps({'outputs': {'root': str(tmp_path/'outputs')}, 'paths': {
        'datapoint_input': str(profile_path), 'pep_usage_output': str(usage),
        'pep_shared_output': str(shared), 'pep_usage_cate_output': str(tmp_path/'reference_usage'),
        'pep_category_output': str(tmp_path/'reference_shared')},
        'datapoint': {'sample_column':'sample', 'group_column':'group', 'group_order':['A','B']}}))
    for script in ['3.add_cate_shared.py','4.add_cate_usage.py']:
        subprocess.run([sys.executable, '-B', str(Path(reference)/'03.UCDR3'/'1.Pep'/script), '--config', str(config)], check=True, capture_output=True, text=True)
    PepAnalysisService._add_cate_usage(usage/'TRB.csv', tmp_path/'platform_usage.csv', profile, 'group')
    PepAnalysisService._add_cate_shared(shared/'TRB.csv', tmp_path/'platform_shared.csv', profile, 'group')
    expected = pd.read_csv(base/'4.add_cate_usage'/'TRB.csv').rename(columns={'group':'Category'}).sort_values('sample').reset_index(drop=True)
    actual = pd.read_csv(tmp_path/'platform_usage.csv').sort_values('sample').reset_index(drop=True)
    pd.testing.assert_frame_equal(actual, expected)
    assert set(actual['sample']) == set(names[:3])
    expected = pd.read_csv(base/'3.add_cate_shared'/'TRB.csv', dtype=str)
    actual = pd.read_csv(tmp_path/'platform_shared.csv', dtype=str)
    expected.iloc[0,0] = 'category'  # Existing platform contract for the group row.
    pd.testing.assert_frame_equal(actual[sorted(actual.columns)], expected[sorted(expected.columns)])


@pytest.mark.parametrize('identifiers', [['001','001'], ['001',None]])
def test_invalid_metadata_rejected_before_analysis(tmp_path, identifiers):
    pep = tmp_path/'pep'
    pep.mkdir()
    profile = tmp_path/'profile.csv'
    pd.DataFrame({'sample': identifiers, 'group':['A','B']}).to_csv(profile,index=False)
    with pytest.raises(ValueError, match='样本编号'):
        PepAnalysisService(output_parent=tmp_path/'results').generate_report(
            pep_data_dir=str(pep),profile_path=str(profile),group_fields=['group'],selected_chains=['TRB'],optional_steps=set())


@pytest.mark.parametrize('selected', ['A-1', 'A1', '病例甲', '病例乙'])
def test_selection_preserves_distinct_identifiers(tmp_path, selected):
    samples = ['A-1', 'A1', '病例甲', '病例乙']
    pep = tmp_path/'pep'
    pep.mkdir()
    profile = tmp_path/'profile.csv'
    pd.DataFrame({'sample': samples, 'group': ['A']*4}).to_csv(profile,index=False)
    for sample in samples:
        pd.DataFrame({'CDR3(pep)':['CASSA'], 'V':['TRBV1'], 'J':['TRBJ1'], 'copy':[5]}).to_csv(pep/f'{sample}__TRB.csv',index=False)
    report = PepAnalysisService(output_parent=tmp_path/'results').generate_report(
        pep_data_dir=str(pep), profile_path=str(profile), group_fields=['group'],
        selected_chains=['TRB'], selected_samples=[selected], optional_steps=set())
    tables = list(report.output_base.rglob('df_VJ_all.csv'))
    assert tables
    table = pd.read_csv(tables[0])
    assert table['sample'].tolist() == [f'{selected}__TRB.csv']


def test_group_and_sample_selections_filter_pep_analysis_inputs(tmp_path):
    pep = tmp_path / 'pep'
    pep.mkdir()
    profile = tmp_path / 'profile.csv'
    pd.DataFrame({'sample': ['S1', 'S2'], 'group': ['A', 'B']}).to_csv(profile, index=False)
    for sample in ['S1', 'S2']:
        pd.DataFrame({
            'CDR3(pep)': [f'CASS-{sample}'], 'V': ['TRBV1'], 'J': ['TRBJ1'], 'copy': [5],
        }).to_csv(pep / f'{sample}__TRB.csv', index=False)

    report = PepAnalysisService(output_parent=tmp_path / 'results').generate_report(
        pep_data_dir=str(pep), profile_path=str(profile), group_fields=['group'],
        selected_chains=['TRB'], optional_steps=set(),
        selected_group_values={'group': ['A']},
        selected_samples_by_group={'group': {'A': ['S1']}},
    )

    tables = list(report.output_base.rglob('df_VJ_all.csv'))
    assert tables
    table = pd.read_csv(tables[0])
    assert table['sample'].tolist() == ['S1__TRB.csv']


def test_batch_field_keeps_same_sample_ids_as_distinct_pep_identities(tmp_path):
    pep = tmp_path / 'pep'
    profile = tmp_path / 'Profile.csv'
    pd.DataFrame({
        'sample': ['S1', 'S1'], 'batch': ['batch-a', 'batch-b'], 'group': ['A', 'B'],
    }).to_csv(profile, index=False)
    for batch, group, count in [('batch-a', 'A', 2), ('batch-b', 'B', 7)]:
        pep_file = pep / batch / 'TRB' / 'S1__TRB.csv'
        pep_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            'CDR3(pep)': [f'CASS-{batch}'], 'V': ['TRBV1'], 'J': ['TRBJ1'], 'copy': [count],
        }).to_csv(pep_file, index=False)

    report = PepAnalysisService(output_parent=tmp_path / 'results').generate_report(
        pep_data_dir=str(pep), pep_paths=[str(pep)], profile_path=str(profile),
        group_fields=['group'], selected_chains=['TRB'], batch_field='batch', optional_steps=set(),
    )

    shared = pd.read_csv(report.output_base / 'Pep_shared' / 'TRB.csv')
    assert set(shared.columns[1:]) == {'batch-a::S1', 'batch-b::S1'}
    shared_values = shared.set_index('CDR3(pep)')
    assert shared_values.loc['CASS-batch-a', 'batch-a::S1'] == 2
    assert shared_values.loc['CASS-batch-b', 'batch-b::S1'] == 7
    categorized = pd.read_csv(report.output_base / 'group' / 'Pep_shared_cate' / 'Pep_shared' / 'TRB.csv')
    category_row = categorized.iloc[0].to_dict()
    assert category_row['batch-a::S1'] == 'A'
    assert category_row['batch-b::S1'] == 'B'
    manifest = json.loads((report.output_base / 'cache_manifest.json').read_text(encoding='utf-8'))
    assert manifest['batch_field'] == 'batch'
    assert manifest['sample_identity_rule'] == 'batch::sample; each part escapes % as %25 and :: as %3A%3A'

    filtered = PepAnalysisService(output_parent=tmp_path / 'filtered-results').generate_report(
        pep_data_dir=str(pep), pep_paths=[str(pep)], profile_path=str(profile),
        group_fields=['group'], selected_chains=['TRB'], batch_field='batch', optional_steps=set(),
        selected_group_values={'group': ['A']},
    )
    filtered_shared = pd.read_csv(filtered.output_base / 'Pep_shared' / 'TRB.csv')
    assert filtered_shared.columns[1:].tolist() == ['batch-a::S1']


def test_batch_sample_identity_escapes_delimiter_inside_identifiers(tmp_path):
    pep = tmp_path / 'pep'
    profile = tmp_path / 'Profile.csv'
    pd.DataFrame({
        'sample': ['S1', 'dup::S1'], 'batch': ['batch::dup', 'batch'], 'group': ['A', 'B'],
    }).to_csv(profile, index=False)
    rows = [('batch::dup', 'S1', 'CASS-batch-a', 2), ('batch', 'dup::S1', 'CASS-batch-b', 7)]
    for batch, sample, cdr3, count in rows:
        pep_file = pep / batch / 'TRB' / f'{sample}__TRB.csv'
        pep_file.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame({
            'CDR3(pep)': [cdr3], 'V': ['TRBV1'], 'J': ['TRBJ1'], 'copy': [count],
        }).to_csv(pep_file, index=False)

    report = PepAnalysisService(output_parent=tmp_path / 'results').generate_report(
        pep_data_dir=str(pep), pep_paths=[str(pep)], profile_path=str(profile),
        group_fields=['group'], selected_chains=['TRB'], batch_field='batch', optional_steps=set(),
    )

    shared = pd.read_csv(report.output_base / 'Pep_shared' / 'TRB.csv')
    assert set(shared.columns[1:]) == {'batch%3A%3Adup::S1', 'batch::dup%3A%3AS1'}
    values = shared.set_index('CDR3(pep)')
    assert values.loc['CASS-batch-a', 'batch%3A%3Adup::S1'] == 2
    assert values.loc['CASS-batch-b', 'batch::dup%3A%3AS1'] == 7
    assert report.metadata['sample_identity_rule'] == 'batch::sample; each part escapes % as %25 and :: as %3A%3A'
