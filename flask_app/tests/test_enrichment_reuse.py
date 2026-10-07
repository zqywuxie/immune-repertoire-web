import json
import shutil
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
        full=module.Path(command[3])/'GO'/'BP'/'A_vs_B'/'GSEA'/'GSEA_GO_BP_full.csv'
        full.parent.mkdir(parents=True,exist_ok=True)
        full.write_text('ID,NES,pvalue,p.adjust\nGO:0002250,0.5,0.8,0.9\n')
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
        assert len(metadata['full_go_gsea_tables']) == 1
        assert metadata['full_go_gsea_tables'][0] in archive.namelist()
        assert metadata['go_gsea_export_policy'] == module.GO_GSEA_EXPORT_POLICY


def test_reuse_rejects_significant_only_or_missing_ranking(tmp_path):
    source = tmp_path/'source';source.mkdir()
    (source/'DEG_significant_A.csv').write_text('gene_symbol,significant\nTP53,Up\n')
    with pytest.raises(ValueError,match='完整差异表达表'):
        GoKeggEnrichmentService._copy_deg_inputs(source,tmp_path/'out',do_gsea=False)
    (source/'DEG_A.csv').write_text('gene_symbol,significant\nTP53,Up\n')
    with pytest.raises(ValueError,match='排序统计量'):
        GoKeggEnrichmentService._copy_deg_inputs(source,tmp_path/'out',do_gsea=True)


def test_export_policy_is_part_of_cache_contract(application, tmp_path):
    from flask_app.routes.api_script_hub._common import _build_script_cache_context
    from flask_app.services.go_kegg_enrichment_service import GO_GSEA_EXPORT_POLICY, GO_ORA_EXPORT_POLICY
    source=tmp_path/'DEG_A_vs_B.csv'
    source.write_text('gene_symbol,significant,t\nTP53,Up,4.25\n')
    context=_build_script_cache_context(project_id=None,module_name='go-kegg-enrichment',
        input_paths=[{'asset_type':'differential_expression','path':str(source)}],
        config_json={'do_gsea':True,'go_gsea_export_policy':'old'})
    assert context['config_json']['go_gsea_export_policy']==GO_GSEA_EXPORT_POLICY
    assert context['config_json']['go_ora_export_policy']==GO_ORA_EXPORT_POLICY


@pytest.mark.skipif(shutil.which("Rscript") is None, reason="需要容器内 R 与人类富集注释")
@pytest.mark.parametrize("symbol, message", [
    ("NO_SUCH_HUMAN_GENE_001", "没有可映射的人类基因符号"),
    ("TP53", "可映射的人类背景基因不足 10 个"),
])
def test_native_annotation_failure_explains_input_without_claiming_empty_result(application, tmp_path, symbol, message):
    source = tmp_path / "source" / "01_vs_02"
    source.mkdir(parents=True)
    table = source / "DEG_01_vs_02.csv"
    table.write_text(f"gene_symbol,significant,t,logFC\n{symbol},Not,0.25,0.1\n", encoding="utf-8")
    original = table.read_bytes()
    with pytest.raises(RuntimeError, match=message):
        GoKeggEnrichmentService(output_parent=tmp_path / "results").generate_report(
            deg_directory=str(source.parent), do_gsea=False)
    assert table.read_bytes() == original
    logs = list((tmp_path / "results").rglob("go_kegg_enrichment.log"))
    assert len(logs) == 1
    assert "STDERR:" in logs[0].read_text(encoding="utf-8")
    assert not list((tmp_path / "results").rglob("go_kegg_enrichment_metadata.json"))


def test_cached_task_preserves_dataset_and_reusable_differential_files(application, tmp_path, monkeypatch):
    from flask_app.routes.api_script_hub import _common as shared
    from flask_app.models.database import db, Project
    from flask_app.services.differential_artifacts import differential_candidates
    source = tmp_path / "scientific" / "DEG" / "02_vs_01"
    source.mkdir(parents=True)
    table = source / "DEG_02_vs_01.csv"
    table.write_text("gene_symbol,significant,t,logFC\nTP53,Not,0.2,0.1\n", encoding="utf-8")
    result = {"module": "volcano", "job_id": "original-output", "output_base": str(source.parent.parent),
        "metadata": {"input_mode": "expression", "selected_expression_samples": ["tpm_01_001", "tpm_02_001"]},
        "csv_urls": ["/api/script-hub/results/original-output/DEG/02_vs_01/DEG_02_vs_01.csv"], "reused_result": True}
    monkeypatch.setattr(shared, "_find_reusable_script_result", lambda *args: result)
    with application.app_context():
        db.session.add(Project(id="cached-expression-project", name="缓存结果验收"))
        db.session.commit()
        context = {"project_id": "cached-expression-project", "asset_set": "Set2", "source_assets": [],
            "analysis_signature": "synthetic-expression-signature", "input_assets": [],
            "config_json": {"input_mode": "expression", "comparisons": [["02", "01"]]},
            "upstream_input": {"artifact_id": "registered-upstream", "source_job_id": "original-task"}}
        with application.test_request_context(json={"asset_set": "Set2"}):
            response = shared._try_reuse_script_result(context, "volcano")
        task = shared.get_script_hub_job_service().get_job(response["task_id"])
        assert task["payload"]["asset_set"] == "Set2"
        assert task["payload"]["source_assets"] == []
        assert task["payload"]["upstream_input"] == context["upstream_input"]
        assert task["detail"] == "已复用当前项目的分析结果，无需重复计算。"
        candidate = next(item for item in differential_candidates("cached-expression-project", "Set2") if item["job_id"] == response["task_id"])
        assert candidate["status"] == "available", candidate
        assert candidate["path"] == str(source.parent)
        assert candidate["metadata"]["selected_expression_samples"] == result["metadata"]["selected_expression_samples"]
        table.unlink()
        candidate = next(item for item in differential_candidates("cached-expression-project", "Set2") if item["job_id"] == response["task_id"])
        assert candidate["status"] == "unavailable"
