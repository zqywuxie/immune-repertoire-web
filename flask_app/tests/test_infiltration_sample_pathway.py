import json
import os
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.exceptions import ValidationError
from flask_app.services.infiltration_sample_pathway import (
    inspect_sample_pathway,
    write_expression_subset,
)
from flask_app.services.infiltration_service import generate_report
from flask_app.tests.test_profile_workflow import profile_app


def make_inputs(tmp_path, groups=None):
    sample_ids = [f"{index:03d}" for index in range(1, 13)]
    if groups is None:
        groups = ["病例"] * 6 + ["对照"] * 6
    profile = tmp_path / "profile.csv"
    deconvolution = tmp_path / "deconvolution.csv"
    expression = tmp_path / "expression.tsv"
    pd.DataFrame({"sample": sample_ids, "group": groups}).to_csv(profile, index=False)
    pd.DataFrame({
        "Mixture": sample_ids,
        "T cells": np.linspace(0.1, 0.9, len(sample_ids)),
        "B cells": np.linspace(0.8, 0.2, len(sample_ids)),
    }).to_csv(deconvolution, index=False)
    matrix = {"Gene": [f"GENE{i}" for i in range(12)]}
    matrix.update({sample: np.arange(1, 13) + index for index, sample in enumerate(sample_ids)})
    pd.DataFrame(matrix).to_csv(expression, sep="\t", index=False)
    return profile, deconvolution, expression, sample_ids


def test_sample_pathway_inspects_three_way_intersection_and_explicit_groups(profile_app, tmp_path):
    profile, deconvolution, expression, sample_ids = make_inputs(tmp_path)
    table = pd.read_csv(expression, sep="\t")
    table["extra"] = np.arange(len(table))
    table.to_csv(expression, sep="\t", index=False)

    inspected = inspect_sample_pathway(
        str(profile), str(deconvolution), str(expression), "group", ["T cells"]
    )
    assert inspected["comparison_groups"] == ["病例", "对照"]
    assert inspected["expression_match_count"] == 12
    assert inspected["unused_expression_sample_count"] == 1
    assert inspected["group_counts"] == {"病例": 6, "对照": 6}

    summary, selected, metadata = inspect_sample_pathway(
        str(profile), str(deconvolution), str(expression), "group", ["T cells"], ["病例", "对照"]
    )
    assert summary["sample_count"] == 12
    assert selected["sample"].tolist() == sample_ids
    assert metadata.set_index("sample").loc["001", "group"] == "病例"


def test_sample_pathway_rejects_too_few_joint_samples_and_bad_comparison(profile_app, tmp_path):
    profile, deconvolution, expression, _ = make_inputs(
        tmp_path, ["病例"] * 8 + ["对照"] * 4
    )
    table = pd.read_csv(expression, sep="\t").drop(columns=["005", "006", "011", "012"])
    table.to_csv(expression, sep="\t", index=False)
    with pytest.raises(ValidationError, match="至少需要 10 个共同匹配样本"):
        inspect_sample_pathway(
            str(profile), str(deconvolution), str(expression), "group", ["T cells"], ["病例", "对照"]
        )
    with pytest.raises(ValidationError, match="两个不同的比较组"):
        inspect_sample_pathway(
            str(profile), str(deconvolution), str(expression), "group", ["T cells"], ["病例", "病例"]
        )


def test_expression_subset_preserves_requested_samples_and_rejects_bad_values(tmp_path):
    expression = tmp_path / "expression.csv"
    output = tmp_path / "subset.csv"
    expression.write_text("Gene,001,002\nA,2,3\nB,NA,4\n", encoding="utf-8")
    assert write_expression_subset(str(expression), ["002", "001"], output) == 2
    result = pd.read_csv(output)
    assert result.columns.tolist() == ["Gene", "sample_1", "sample_2"]
    assert result["sample_1"].tolist() == [3, 4]
    assert result["sample_2"].tolist() == [2, 0]

    expression.write_text("Gene,001\nA,-1\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="不能含负值"):
        write_expression_subset(str(expression), ["001"], output)
    expression.write_text("Gene,001\nA,not-a-number\n", encoding="utf-8")
    with pytest.raises(ValidationError, match="非数值"):
        write_expression_subset(str(expression), ["001"], output)


def test_sample_pathway_api_uses_selected_project_transcriptome_and_submits(profile_app, tmp_path, monkeypatch):
    from flask_app.models.database import Project, ProjectAsset, db
    from flask_app.routes.api_script_hub import _common as shared

    profile, deconvolution, expression, _ = make_inputs(tmp_path)
    project = Project(name="GO 样本级通路输入")
    db.session.add(project)
    db.session.flush()
    for kind, path in (("profile", profile), ("deconvolution", deconvolution), ("transcriptome", expression)):
        db.session.add(ProjectAsset(
            project_id=project.id,
            asset_type=kind,
            original_name=path.name,
            storage_path=str(path),
            size=path.stat().st_size,
            metadata_json={"asset_set": "Set1"},
        ))
    db.session.commit()

    submit = []
    monkeypatch.setattr(shared._script_executor, "submit", lambda *args, **kwargs: submit.append((args, kwargs)))
    monkeypatch.setattr(shared, "_set_task_state", lambda *args, **kwargs: None)
    client = profile_app.test_client()
    payload = {
        "project_id": project.id,
        "asset_set": "Set1",
        "group_field": "group",
        "cell_columns": ["T cells"],
        "score_type": "relative",
        "comparison": ["病例", "对照"],
    }
    inspected = client.post("/api/script-hub/immune-infiltration-sample-pathway/inspect", json=payload)
    assert inspected.status_code == 200, inspected.json
    assert inspected.json["expression_match_count"] == 12
    assert inspected.json["comparison_groups"] == ["病例", "对照"]

    submitted = client.post("/api/script-hub/immune-infiltration-sample-pathway/run", json=payload)
    assert submitted.status_code == 200, submitted.json
    assert len(submit) == 1
    kwargs = submit[0][1]
    assert kwargs["module"] == "immune-infiltration-sample-pathway"
    assert kwargs["expression_path"] == str(expression)
    context = kwargs["app_context_app"]
    assert context is profile_app


def test_sample_pathway_real_r_ssgsea_and_within_group_permutation(profile_app, tmp_path):
    profile, deconvolution, expression, _ = make_inputs(tmp_path)
    sample_ids = [f"S{index:03d}" for index in range(1, 13)]
    pd.DataFrame({"sample": sample_ids, "group": ["病例"] * 6 + ["对照"] * 6}).to_csv(profile, index=False)
    pd.DataFrame({
        "Mixture": sample_ids,
        "T cells": np.linspace(0.1, 0.9, len(sample_ids)),
        "B cells": np.linspace(0.8, 0.2, len(sample_ids)),
    }).to_csv(deconvolution, index=False)
    # Use actual GOALL-annotated human symbols so at least one fixed term has adequate coverage.
    command = [
        "Rscript", "-e",
        "suppressPackageStartupMessages({library(AnnotationDbi);library(org.Hs.eg.db);library(GO.db)}); "
        "ids<-c('GO:0002250','GO:0046649','GO:0042110','GO:0042113','GO:0006959','GO:0045087','GO:0002274','GO:0006954','GO:0019221','GO:0006956'); "
        "a<-AnnotationDbi::select(org.Hs.eg.db::org.Hs.eg.db,keys=ids,keytype='GOALL',columns=c('SYMBOL','ONTOLOGYALL')); "
        "g<-unique(toupper(a$SYMBOL[!is.na(a$ONTOLOGYALL)&a$ONTOLOGYALL=='BP'&!is.na(a$SYMBOL)])); "
        "write.table(head(g,1500),commandArgs(TRUE)[1],row.names=FALSE,col.names=FALSE,quote=FALSE)",
        str(tmp_path / "genes.txt"),
    ]
    subprocess.run(command, check=True, capture_output=True, text=True)
    genes = (tmp_path / "genes.txt").read_text(encoding="utf-8").splitlines()
    assert len(genes) >= 10
    rng = np.random.default_rng(42)
    matrix = {"Gene": genes}
    for index, sample in enumerate(sample_ids):
        matrix[sample] = rng.lognormal(mean=1 + (index // 6) * 0.2, sigma=0.5, size=len(genes))
    pd.DataFrame(matrix).to_csv(expression, sep="\t", index=False)

    _, output, summary = generate_report(
        str(profile), str(deconvolution), "group", ["T cells", "B cells"],
        tmp_path / "results", lambda *args: None, lambda: False,
        score_type="relative", analysis_kind="sample_pathway",
        comparison=["病例", "对照"], expression_path=str(expression),
    )
    assert summary["sample_count"] == 12
    assert not list((tmp_path / "results").glob("infiltration_*.csv"))
    coverage = pd.read_csv(output / "GO_sample_gene_coverage.csv")
    assert coverage["Included"].any()
    statistics = pd.read_csv(output / "GO_sample_partial_statistics.csv")
    assert set(statistics["CellType"]) == {"T cells", "B cells"}
    assert statistics["n"].eq(12).all()
    assert statistics["p_value"].between(0, 1).all()
    assert statistics["q_value"].between(0, 1).all()
    assert (output / "GO_sample_partial.png").stat().st_size > 0
    assert not list(output.parent.glob("infiltration_*.csv"))

    reference = os.environ.get("REFERENCE_PIPELINE")
    if reference:
        reference = Path(reference)
        reference_output = tmp_path / "reference-output"
        config_path = tmp_path / "reference-config.json"
        config_path.write_text(json.dumps({
            "default_profile": "default",
            "datapoint_profiles": {"default": {
                "input_path_key": "comparison_profile",
                "sample_column": "sample",
                "group_column": "group",
                "group_order": ["病例", "对照"],
            }},
            "paths": {"comparison_profile": str(profile)},
            "outputs": {"root": str(tmp_path / "reference-project")},
            "immune_infiltration": {
                "sample_column": "sample",
                "group_column": "category",
                "cell_columns": ["T cells", "B cells"],
                "comparisons": [["病例", "对照"]],
            },
            "transcriptome": {"gene_column": "Gene"},
        }, ensure_ascii=False), encoding="utf-8")
        reference_script = reference / "07.immuneInfiltration" / "05.plot_deconv_pathway_concordance.R"
        subprocess.run([
            "Rscript", str(reference_script),
            f"--config={config_path}",
            f"--input={deconvolution}",
            f"--expression={expression}",
            f"--go-gsea={tmp_path / 'missing-go-gsea.csv'}",
            "--comparison=病例:对照",
            "--cell-cols=T cells,B cells",
            f"--output={reference_output}",
        ], check=True, capture_output=True, text=True)
        reference_scores = pd.read_csv(
            reference_output / "panel_D1_GO_sample" / "D1_sample_GO_ssGSEA_scores.csv"
        ).set_index("Pathway")
        platform_scores = pd.read_csv(output / "GO_sample_ssGSEA_scores.csv").set_index("Pathway")
        assert reference_scores.index.tolist() == platform_scores.index.tolist()
        np.testing.assert_allclose(reference_scores[sample_ids], platform_scores[sample_ids], rtol=1e-12, atol=1e-12)
        reference_stats = pd.read_csv(
            reference_output / "panel_D1_GO_sample" / "D1_sample_GO_cell_partial_statistics.csv"
        ).set_index(["Pathway", "CellType"]).sort_index()
        platform_stats = statistics.set_index(["Pathway", "CellType"]).sort_index()
        assert reference_stats.index.equals(platform_stats.index)
        for field in ("n", "rho", "p_value", "q_value", "n_permutations"):
            np.testing.assert_allclose(reference_stats[field], platform_stats[field], rtol=1e-12, atol=1e-12)
