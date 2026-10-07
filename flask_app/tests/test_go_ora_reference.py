import os
import shutil
import subprocess
from pathlib import Path

import pytest

from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService


@pytest.mark.skipif(
    not os.environ.get("REFERENCE_PIPELINE") or not shutil.which("Rscript"),
    reason="需要容器内 GO 注释库与只读挂载的原始 pipeline",
)
def test_platform_go_ora_matches_pipeline_and_keeps_full_terms(tmp_path):
    reference_root = Path(os.environ["REFERENCE_PIPELINE"]) / "06.Transcriptome"
    common_script = reference_root / "enrichment_common.R"
    if not common_script.is_file():
        pytest.skip("未找到原始 enrichment_common.R")

    service_path = tmp_path / "service.R"
    service_path.write_text(GoKeggEnrichmentService._r_script(), encoding="utf-8")
    runner = tmp_path / "compare_go.R"
    runner.write_text(
        r'''args <- commandArgs(trailingOnly = TRUE)
service_path <- args[[1]]
reference_path <- args[[2]]
result_path <- args[[3]]
suppressPackageStartupMessages(library(clusterProfiler))
suppressPackageStartupMessages(library(org.Hs.eg.db))
suppressPackageStartupMessages(library(AnnotationDbi))

find_assignment <- function(expressions, name) {
  matches <- expressions[vapply(expressions, function(expr) {
    is.call(expr) && identical(expr[[1]], as.name("<-")) &&
      identical(expr[[2]], as.name(name))
  }, logical(1))]
  if (!length(matches)) stop("Missing function definition: ", name)
  matches[[1]]
}

reference_env <- new.env(parent = globalenv())
reference_env$org.Hs.eg.db <- org.Hs.eg.db
reference_env$enrichment_output_pvalue_cutoff <- 1
reference_env$pAdjustMethod_enrich <- "BH"
reference_env$simplify_go <- FALSE
reference_env$simplify_cutoff <- 0.7
reference_exprs <- parse(reference_path)
eval(find_assignment(reference_exprs, "apply_output_cutoffs"), reference_env)
eval(find_assignment(reference_exprs, "run_go_enrich"), reference_env)

service_env <- new.env(parent = globalenv())
service_env$org.Hs.eg.db <- org.Hs.eg.db
service_exprs <- parse(service_path)
eval(find_assignment(service_exprs, "run_go_ora_full"), service_env)

annotation <- suppressMessages(select(
  org.Hs.eg.db, keys = "GO:0002376", keytype = "GOALL", columns = "SYMBOL"
))
symbols <- unique(na.omit(annotation$SYMBOL))
mapped <- suppressMessages(bitr(symbols, fromType = "SYMBOL", toType = "ENTREZID",
                                OrgDb = org.Hs.eg.db, drop = TRUE))
genes <- unique(mapped$ENTREZID[seq_len(min(80, nrow(mapped)))])
background_map <- suppressMessages(bitr(keys(org.Hs.eg.db, keytype = "SYMBOL"), fromType = "SYMBOL",
                                        toType = "ENTREZID", OrgDb = org.Hs.eg.db,
                                        drop = TRUE))
background <- unique(background_map$ENTREZID)
expected <- reference_env$run_go_enrich(genes, background, "synthetic", "BP")
observed <- service_env$run_go_ora_full(genes, background, "BP", "BH")
expected_df <- as.data.frame(expected)
observed_df <- as.data.frame(observed)
if (!nrow(expected_df) || !nrow(observed_df)) stop("GO test input produced no terms")
if (!identical(names(expected_df), names(observed_df))) stop("GO columns differ")
if (!isTRUE(all.equal(expected_df, observed_df, tolerance = 1e-12, check.attributes = FALSE))) {
  stop("Platform GO ORA differs from reference helper")
}
if (!any(observed_df$pvalue > 0.05 | observed_df$p.adjust > 0.05)) {
  stop("Synthetic result did not exercise complete, non-significant term retention")
}
write.csv(observed_df, result_path, row.names = FALSE)
cat("PASS: GO ORA values match; complete BP term table retained\n")
''',
        encoding="utf-8",
    )
    result = subprocess.run(
        [
            shutil.which("Rscript"),
            str(runner),
            str(service_path),
            str(common_script),
            str(tmp_path / "go_results.csv"),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=300,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "PASS:" in result.stdout
