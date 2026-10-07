import os
import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from flask_app.services.volcano_service import VolcanoService


def test_limma_failure_reports_r_error_instead_of_execution_halted(tmp_path, monkeypatch):
    monkeypatch.setattr("flask_app.services.volcano_service.shutil.which", lambda _: "/usr/bin/Rscript")
    monkeypatch.setattr(
        "flask_app.services.volcano_service.subprocess.run",
        lambda *args, **kwargs: subprocess.CompletedProcess(
            args=args[0],
            returncode=1,
            stdout="",
            stderr="Error in loadNamespace(x) : there is no package called 'limma'\nExecution halted\n",
        ),
    )
    service = VolcanoService(output_parent=tmp_path / "results")
    expression = pd.DataFrame(
        {f"sample_{index}": [index + 1, index + 2] for index in range(1, 7)},
        index=["G1", "G2"],
    )
    sample_groups = {
        "sample_1": "A", "sample_2": "A", "sample_3": "A",
        "sample_4": "B", "sample_5": "B", "sample_6": "B",
    }

    with pytest.raises(RuntimeError, match="there is no package called 'limma'"):
        service._expression_de_one_comparison(
            expression,
            sample_groups,
            "A",
            "B",
            pvalue_threshold=0.05,
            logfc_cutoff=1.0,
            quality_output=tmp_path / "results" / "weights.csv",
        )


@pytest.mark.skipif(
    not os.environ.get("REFERENCE_PIPELINE") or not shutil.which("Rscript"),
    reason="需要容器内 R/limma 和只读挂载的原始 pipeline",
)
def test_expression_deg_matches_reference_limma(tmp_path):
    reference_script = (
        Path(os.environ["REFERENCE_PIPELINE"])
        / "06.Transcriptome"
        / "01.DEG_analysis.R"
    )
    if not reference_script.is_file():
        pytest.skip("未找到原始 06.Transcriptome/01.DEG_analysis.R")

    expression = pd.DataFrame(
        {
            "gene": [f"G{i}" for i in range(1, 13)],
            "tpm_A_1": [100, 3, 12, 9, 4, 50, 2, 21, 18, 7, 5, 30],
            "tpm_A_2": [91, 4, 14, 8, 5, 42, 3, 19, 17, 6, 6, 28],
            "tpm_A_3": [110, 2, 10, 10, 4, 55, 2, 22, 20, 9, 4, 32],
            "tpm_B_1": [5, 80, 13, 6, 60, 4, 30, 8, 17, 35, 4, 11],
            "tpm_B_2": [4, 72, 12, 7, 55, 5, 33, 7, 18, 31, 5, 10],
            "tpm_B_3": [6, 88, 11, 5, 64, 3, 28, 9, 16, 39, 3, 13],
        }
    )
    expression_path = tmp_path / "aligned.csv"
    expression.to_csv(expression_path, index=False)

    report = VolcanoService(output_parent=tmp_path / "platform-results").generate_expression_report(
        expression_path=str(expression_path),
        comparisons=[["A", "B"]],
        pvalue_threshold=0.05,
        logfc_cutoff=1.0,
    )
    platform = pd.read_csv(report.csv_paths[0]).set_index("gene_symbol").sort_index()

    groups_path = tmp_path / "groups.csv"
    pd.DataFrame(
        {
            "sample": expression.columns[1:],
            "group": ["A", "A", "A", "B", "B", "B"],
        }
    ).to_csv(groups_path, index=False)
    reference_output = tmp_path / "reference.csv"
    reference_runner = tmp_path / "run_reference.R"
    reference_runner.write_text(
        r'''args <- commandArgs(trailingOnly = TRUE)
reference_path <- args[[1]]
expression_path <- args[[2]]
groups_path <- args[[3]]
output_path <- args[[4]]
quality_path <- args[[5]]
suppressPackageStartupMessages(library(limma))
parsed <- parse(reference_path)
definition <- parsed[vapply(parsed, function(x) {
  is.call(x) && identical(x[[1]], as.name("<-")) &&
    identical(x[[2]], as.name("run_limma"))
}, logical(1))][[1]]
env <- new.env(parent = globalenv())
env$expression_data_type <- "TPM"
env$sample_quality_weights <- TRUE
env$deg_out <- function(comp, file, subdir = "") {
  if (identical(file, "sample_quality_weights.csv")) quality_path
  else tempfile(fileext = ".csv")
}
eval(definition, envir = env)
table <- read.csv(expression_path, check.names = FALSE)
rownames(table) <- table$gene
table$gene <- NULL
raw <- as.matrix(table)
storage.mode(raw) <- "numeric"
expr_matrix <- limma::normalizeBetweenArrays(log2(raw + 1), method = "quantile")
groups <- read.csv(groups_path, stringsAsFactors = FALSE)
sample_info <- data.frame(
  sample = groups$sample,
  group = factor(groups$group, levels = c("B", "A")),
  row.names = groups$sample
)
result <- env$run_limma(expr_matrix, sample_info, "A", "B")
write.csv(result, output_path, row.names = FALSE)
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            shutil.which("Rscript"),
            str(reference_runner),
            str(reference_script),
            str(expression_path),
            str(groups_path),
            str(reference_output),
            str(tmp_path / "reference_weights.csv"),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    expected = pd.read_csv(reference_output).set_index("gene_symbol").sort_index()

    columns = ["logFC", "AveExpr", "t", "P.Value", "adj.P.Val", "B"]
    for column in columns:
        np.testing.assert_allclose(
            platform[column].to_numpy(), expected[column].to_numpy(), rtol=1e-9, atol=1e-11
        )
    assert platform["significant"].equals(platform["significant_fdr"])
    assert report.metadata["differential_method"] == "limma::lmFit + eBayes(robust=TRUE)"
    quality_path = report.output_base / "DEG" / "A_vs_B" / "QC" / "sample_quality_weights.csv"
    quality = pd.read_csv(quality_path)
    assert quality["sample"].tolist() == expression.columns[1:].tolist()
    assert quality["group"].tolist() == ["A", "A", "A", "B", "B", "B"]
    assert np.isfinite(quality["sample_weight"]).all()
    reference_weights = pd.read_csv(tmp_path / "reference_weights.csv")
    np.testing.assert_allclose(quality["sample_weight"], reference_weights["sample_weight"], rtol=1e-9, atol=1e-11)
