import json
import zipfile
from types import SimpleNamespace
from flask_app.tests.test_persistent_queue import application
import pytest
from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService


def test_reuses_exact_differential_tables_without_recomputing(application, tmp_path, monkeypatch):
    from flask_app.services import go_kegg_enrichment_service as module
    source = tmp_path / 'source' / 'A_vs_B'
    source.mkdir(parents=True)
    table = source / 'DEG_A_vs_B.csv'
    table.write_text('gene_symbol,significant,t,logFC\nTP53,Up,4.25,1.20\nEGFR,Down,-3.50,-1.25\n',encoding='utf-8')
    original = table.read_bytes()
    monkeypatch.setattr(module.shutil, 'which', lambda name:'/usr/bin/Rscript')
    monkeypatch.setattr(module.VolcanoService, 'generate_expression_report', lambda *args, **kwargs:pytest.fail('must not recompute differential expression'))
    def run(command, **kwargs):
        assert (module.Path(command[2]) / 'A_vs_B' / table.name).read_bytes() == original
        return SimpleNamespace(returncode=0,stdout='',stderr='')
    monkeypatch.setattr(module.subprocess, 'run',run)
    report = GoKeggEnrichmentService(output_parent=tmp_path/'results').generate_report(
        deg_directory=str(source.parent), differential_metadata={'pvalue_threshold':0.01}, do_gsea=True)
    assert report.metadata['reused_differential_results'] is True
    assert report.metadata['pvalue_threshold'] == 0.01
    assert table.read_bytes() == original
    with zipfile.ZipFile(report.zip_path) as archive:
        metadata = json.loads(archive.read('go_kegg_enrichment_metadata.json'))
        assert metadata['source_deg_files'] == ['A_vs_B/DEG_A_vs_B.csv']


def test_reuse_rejects_significant_only_or_missing_ranking(tmp_path):
    source = tmp_path/'source';source.mkdir()
    (source/'DEG_significant_A.csv').write_text('gene_symbol,significant\nTP53,Up\n')
    with pytest.raises(ValueError,match='完整差异表达表'):
        GoKeggEnrichmentService._copy_deg_inputs(source,tmp_path/'out',do_gsea=False)
    (source/'DEG_A.csv').write_text('gene_symbol,significant\nTP53,Up\n')
    with pytest.raises(ValueError,match='排序统计量'):
        GoKeggEnrichmentService._copy_deg_inputs(source,tmp_path/'out',do_gsea=True)
