"""Real container R regression for preserving downstream pathway evidence."""
import shutil
import subprocess

import pytest

from flask_app.services.go_kegg_enrichment_service import GoKeggEnrichmentService


@pytest.mark.skipif(not shutil.which('Rscript'), reason='需要容器内的 R 分析环境')
def test_full_export_preserves_nonsignificant_terms_and_legacy_statistics(tmp_path):
    source = tmp_path / 'service.R'
    source.write_text(GoKeggEnrichmentService._r_script(), encoding='utf-8')
    script = tmp_path / 'verify.R'
    script.write_text(r'''
suppressPackageStartupMessages(library(clusterProfiler))
suppressPackageStartupMessages(library(BiocParallel))
register(SerialParam())
# Load the actual production export helpers without executing the entire
# GO/KEGG workflow (which also requires online KEGG annotation).
for (expr in parse("service.R")) {
  if (is.call(expr) && identical(expr[[1]], as.name("<-")) &&
      as.character(expr[[2]]) %in% c("write_result", "export_full_gsea")) eval(expr)
}
set.seed(19)
ranked <- sort(setNames(rnorm(500), paste0("G", 1:500)), decreasing=TRUE)
sets <- c(list(positive=names(ranked)[1:25], negative=tail(names(ranked),25)),
          setNames(lapply(1:24, function(i) sample(names(ranked),30)), paste0("random",1:24)))
mapping <- do.call(rbind,lapply(names(sets),function(id) data.frame(term=id,gene=sets[[id]])))
calculate <- function(cutoff) {
  set.seed(73)
  GSEA(ranked, TERM2GENE=mapping, minGSSize=10, maxGSSize=100,
       pvalueCutoff=cutoff, pAdjustMethod="BH", verbose=FALSE,
       eps=1e-5, BPPARAM=SerialParam())
}
legacy <- calculate(.05)
complete <- calculate(1)
before <- as.data.frame(complete)
visible <- export_full_gsea(complete,"full.csv",.05)
saved <- read.csv("full.csv",check.names=FALSE)
stopifnot(nrow(saved)>nrow(as.data.frame(legacy)), nrow(as.data.frame(legacy))>0)
stopifnot(any(saved$p.adjust>.05), identical(saved$ID,before$ID))
stopifnot(isTRUE(all.equal(saved$NES,before$NES,tolerance=1e-12)))
stopifnot(isTRUE(all.equal(saved$pvalue,before$pvalue,tolerance=1e-12)))
stopifnot(isTRUE(all.equal(as.data.frame(visible),as.data.frame(legacy),tolerance=1e-12)))
stopifnot(visible@params$pvalueCutoff==.05, nrow(as.data.frame(complete))==nrow(before))
stopifnot(is.null(export_full_gsea(NULL,"absent.csv",.05)), !file.exists("absent.csv"))
cat("PASS: full terms retained; filtered statistics unchanged\n")
''', encoding='utf-8')
    result = subprocess.run(['Rscript', str(script)], cwd=tmp_path, capture_output=True, text=True, timeout=180)
    assert result.returncode == 0, result.stdout + result.stderr
    assert 'PASS:' in result.stdout
