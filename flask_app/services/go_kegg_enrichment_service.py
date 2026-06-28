"""
GO / KEGG enrichment service for Script Hub expression-matrix workflows.

The differential-expression step is delegated to VolcanoService so volcano
plots and DEG tables stay consistent with the existing volcano module. GO/KEGG
ORA and GSEA are executed through Rscript + clusterProfiler when available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from flask_app.services.volcano_service import VolcanoService


@dataclass
class GoKeggEnrichmentReport:
    job_id: str
    output_base: Path
    png_paths: List[str]
    pdf_paths: List[str]
    csv_paths: List[str]
    zip_path: str
    log_path: str
    metadata: Dict[str, Any]


class GoKeggEnrichmentService:
    """Run GO/KEGG enrichment from an RNA-seq expression matrix."""

    def __init__(self, *, output_parent: Path) -> None:
        self.output_parent = output_parent.resolve()

    @staticmethod
    def inspect_expression_matrix(expression_path: str, group_prefix: str = "tpm_") -> Dict[str, Any]:
        return VolcanoService.inspect_expression_matrix(expression_path, group_prefix=group_prefix)

    def generate_report(
        self,
        *,
        expression_path: str,
        group_prefix: str = "tpm_",
        comparisons: Optional[Sequence[Sequence[str]]] = None,
        pvalue_threshold: float = 0.05,
        logfc_cutoff: float = 1.0,
        enrich_pvalue_cutoff: float = 0.05,
        p_adjust_method: str = "none",
        show_category: int = 20,
        simplify_go: bool = True,
        do_gsea: bool = True,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> GoKeggEnrichmentReport:
        expression_file = Path(expression_path)
        if not expression_file.exists() or not expression_file.is_file():
            raise FileNotFoundError(f"Expression matrix not found: {expression_path}")

        rscript = shutil.which("Rscript")
        if not rscript:
            raise RuntimeError("Rscript is not available. Install R and Bioconductor packages: clusterProfiler, org.Hs.eg.db, enrichplot, DOSE.")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        job_id = self._allocate_job_id(output_name or "go_kegg_enrichment")
        output_base = self.output_parent / job_id
        output_base.mkdir(parents=True, exist_ok=True)

        if progress_callback:
            progress_callback(5, "GO/KEGG", "生成差异表达和火山图")

        volcano_report = VolcanoService(output_parent=self.output_parent).generate_expression_report(
            expression_path=str(expression_file),
            group_prefix=group_prefix,
            comparisons=comparisons,
            pvalue_threshold=pvalue_threshold,
            logfc_cutoff=logfc_cutoff,
            output_base=output_base,
            job_id=job_id,
            progress_callback=lambda progress, stage, detail, meta=None: (
                progress_callback(5 + float(progress or 0) * 0.25, stage, detail, meta)
                if progress_callback else None
            ),
        )

        if progress_callback:
            progress_callback(34, "GO/KEGG", "准备 clusterProfiler 脚本")

        r_script_path = output_base / "run_go_kegg_enrichment.R"
        r_script_path.write_text(self._r_script(), encoding="utf-8")
        log_path = output_base / "go_kegg_enrichment.log"
        enrichment_dir = output_base / "enrichment_results"
        enrichment_dir.mkdir(parents=True, exist_ok=True)

        command = [
            rscript,
            str(r_script_path),
            str(output_base / "DEG"),
            str(enrichment_dir),
            str(enrich_pvalue_cutoff),
            str(p_adjust_method or "none"),
            str(int(show_category or 20)),
            "TRUE" if simplify_go else "FALSE",
            "TRUE" if do_gsea else "FALSE",
        ]
        if progress_callback:
            progress_callback(42, "GO/KEGG", "运行 Rscript / clusterProfiler")

        completed = subprocess.run(
            command,
            cwd=str(output_base),
            text=True,
            capture_output=True,
            check=False,
        )
        log_path.write_text(
            "COMMAND:\n" + " ".join(command) + "\n\nSTDOUT:\n" + completed.stdout + "\n\nSTDERR:\n" + completed.stderr,
            encoding="utf-8",
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "GO/KEGG enrichment failed. See go_kegg_enrichment.log. "
                + (completed.stderr.strip().splitlines()[-1] if completed.stderr.strip() else "")
            )

        png_paths = [str(path) for path in sorted(output_base.rglob("*.png"))]
        pdf_paths: List[str] = []
        csv_paths = [str(path) for path in sorted(output_base.rglob("*.csv"))]

        zip_path = output_base / "go_kegg_enrichment_results.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(output_base.rglob("*")):
                if path.is_file() and path.name != zip_path.name:
                    zf.write(path, path.relative_to(output_base).as_posix())

        metadata = {
            **volcano_report.metadata,
            "job_id": job_id,
            "module": "go-kegg-enrichment",
            "generated_at": datetime.now().isoformat(),
            "enrich_pvalue_cutoff": enrich_pvalue_cutoff,
            "p_adjust_method": p_adjust_method,
            "show_category": show_category,
            "simplify_go": simplify_go,
            "do_gsea": do_gsea,
            "output_counts": {
                "png": len(png_paths),
                "pdf": 0,
                "csv": len(csv_paths),
            },
        }
        (output_base / "go_kegg_enrichment_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if progress_callback:
            progress_callback(100, "GO/KEGG", f"完成 {len(csv_paths)} 个表格，{len(png_paths)} 张图")

        return GoKeggEnrichmentReport(
            job_id=job_id,
            output_base=output_base,
            png_paths=png_paths,
            pdf_paths=pdf_paths,
            csv_paths=csv_paths,
            zip_path=str(zip_path),
            log_path=str(log_path),
            metadata=metadata,
        )

    def _allocate_job_id(self, prefix: str) -> str:
        safe = VolcanoService._safe_title(prefix)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{safe}_{ts}"

    @staticmethod
    def _r_script() -> str:
        return r'''
args <- commandArgs(trailingOnly = TRUE)
deg_root <- args[[1]]
output_dir <- args[[2]]
pvalue_cutoff_enrich <- as.numeric(args[[3]])
pAdjustMethod_enrich <- args[[4]]
showCategory_num <- as.integer(args[[5]])
simplify_go <- args[[6]] == "TRUE"
do_gsea <- args[[7]] == "TRUE"

options(clusterProfiler.download.method = NULL)
required_pkgs <- c("clusterProfiler", "org.Hs.eg.db", "enrichplot", "DOSE", "ggplot2")
missing_pkgs <- required_pkgs[!vapply(required_pkgs, requireNamespace, logical(1), quietly = TRUE)]
if (length(missing_pkgs) > 0) {
  stop("Missing R packages: ", paste(missing_pkgs, collapse = ", "),
       ". Install with BiocManager::install(c('clusterProfiler','org.Hs.eg.db','enrichplot','DOSE')).")
}
suppressPackageStartupMessages({
  library(clusterProfiler)
  library(org.Hs.eg.db)
  library(enrichplot)
  library(DOSE)
  library(ggplot2)
})

dir.create(output_dir, showWarnings = FALSE, recursive = TRUE)
output_go <- file.path(output_dir, "GO")
output_kegg <- file.path(output_dir, "KEGG")
dir.create(output_go, showWarnings = FALSE, recursive = TRUE)
dir.create(output_kegg, showWarnings = FALSE, recursive = TRUE)

safe_name <- function(x) {
  x <- gsub("[^A-Za-z0-9_.-]+", "_", x)
  substr(x, 1, 120)
}
make_dir <- function(...) {
  d <- file.path(...)
  dir.create(d, showWarnings = FALSE, recursive = TRUE)
  d
}
write_result <- function(res, path) {
  if (is.null(res)) return(FALSE)
  dat <- as.data.frame(res)
  if (nrow(dat) == 0) return(FALSE)
  write.csv(dat, path, row.names = FALSE)
  TRUE
}
save_basic_plots <- function(res, out_dir, label) {
  dat <- as.data.frame(res)
  if (is.null(res) || nrow(dat) < 2) return()
  nshow <- min(showCategory_num, nrow(dat))
  p1 <- dotplot(res, showCategory = nshow, font.size = 10) +
    ggtitle(label) + theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  ggsave(file.path(out_dir, paste0("dotplot_", safe_name(label), ".png")), p1, width = 10, height = max(6, nshow * 0.32), dpi = 300, bg = "white")
  p2 <- barplot(res, showCategory = nshow, font.size = 10) +
    ggtitle(label) + theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  ggsave(file.path(out_dir, paste0("barplot_", safe_name(label), ".png")), p2, width = 12, height = max(6, nshow * 0.38), dpi = 300, bg = "white")
}
save_gsea_plots <- function(res, out_dir, label) {
  dat <- as.data.frame(res)
  if (is.null(res) || nrow(dat) < 2) return()
  save_basic_plots(res, out_dir, label)
  n_gsea <- min(5, nrow(dat))
  for (i in seq_len(n_gsea)) {
    tryCatch({
      term_desc <- dat$Description[i]
      p3 <- gseaplot2(res, geneSetID = i, color = "red",
                      rel_heights = c(1.5, 0.5, 1),
                      subplots = 1:3, pvalue_table = TRUE,
                      title = term_desc, ES_geom = "line")
      base <- paste0("gseaplot_", i, "_", safe_name(term_desc))
      ggsave(file.path(out_dir, paste0(base, ".png")), p3, width = 10, height = 7, dpi = 300, bg = "white")
    }, error = function(e) message("gseaplot failed: ", e$message))
  }
}

deg_files <- list.files(deg_root, pattern = "^DEG_.*\\.csv$", recursive = TRUE, full.names = TRUE)
deg_files <- deg_files[!grepl("significant", basename(deg_files), ignore.case = TRUE)]
if (length(deg_files) == 0) stop("No DEG CSV files found under ", deg_root)

all_symbols <- unique(unlist(lapply(deg_files, function(f) read.csv(f, check.names = FALSE)$gene_symbol)))
bg_map <- suppressMessages(bitr(all_symbols, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = org.Hs.eg.db, drop = TRUE))
bg_entrez <- unique(bg_map$ENTREZID)
if (length(bg_entrez) < 10) stop("Too few background genes mapped to ENTREZID")

go_onts <- c("BP", "CC", "MF")
for (deg_file in deg_files) {
  deg <- read.csv(deg_file, check.names = FALSE)
  comp_name <- sub("^DEG_", "", tools::file_path_sans_ext(basename(deg_file)))
  message("Processing ", comp_name)
  for (direction in c("Up", "Down")) {
    genes <- unique(deg$gene_symbol[deg$significant == direction])
    if (length(genes) < 5) {
      message("Skip ", comp_name, " ", direction, ": less than 5 significant genes")
      next
    }
    id_map <- suppressMessages(bitr(genes, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = org.Hs.eg.db, drop = TRUE))
    entrez <- unique(id_map$ENTREZID)
    if (length(entrez) < 5) next
    for (ont in go_onts) {
      go_res <- tryCatch({
        res <- enrichGO(gene = entrez, universe = bg_entrez, OrgDb = org.Hs.eg.db,
                        ont = ont, pAdjustMethod = pAdjustMethod_enrich,
                        pvalueCutoff = pvalue_cutoff_enrich, readable = TRUE)
        if (!is.null(res) && nrow(as.data.frame(res)) > 0 && simplify_go) {
          res <- tryCatch(clusterProfiler::simplify(res, cutoff = 0.7, by = "pvalue", select_fun = min),
                          error = function(e) res)
        }
        res
      }, error = function(e) { message("GO error: ", e$message); NULL })
      out_dir <- make_dir(output_go, ont, comp_name, "ORA", direction)
      if (write_result(go_res, file.path(out_dir, paste0(comp_name, "_", direction, "_GO_", ont, ".csv")))) {
        save_basic_plots(go_res, out_dir, paste0(comp_name, "_", direction, "_GO_", ont))
      }
    }
    kegg_res <- tryCatch({
      enrichKEGG(gene = entrez, universe = bg_entrez, organism = "hsa",
                 pAdjustMethod = pAdjustMethod_enrich,
                 pvalueCutoff = pvalue_cutoff_enrich)
    }, error = function(e) { message("KEGG error: ", e$message); NULL })
    out_dir <- make_dir(output_kegg, comp_name, "ORA", direction)
    if (write_result(kegg_res, file.path(out_dir, paste0("KEGG_", comp_name, "_", direction, ".csv")))) {
      save_basic_plots(kegg_res, out_dir, paste0("KEGG_", comp_name, "_", direction))
    }
  }

  if (do_gsea && "t" %in% colnames(deg)) {
    t_vals <- deg$t
    names(t_vals) <- deg$gene_symbol
    t_vals <- t_vals[!is.na(t_vals) & t_vals != 0]
    if (length(t_vals) >= 10) {
      id_map <- suppressMessages(bitr(names(t_vals), fromType = "SYMBOL", toType = "ENTREZID", OrgDb = org.Hs.eg.db, drop = TRUE))
      ranked <- t_vals[id_map$SYMBOL]
      names(ranked) <- id_map$ENTREZID
      ranked <- ranked[!duplicated(names(ranked))]
      ranked <- sort(ranked, decreasing = TRUE)
      for (ont in go_onts) {
        gse_go <- tryCatch({
          res <- gseGO(geneList = ranked, ont = ont, OrgDb = org.Hs.eg.db,
                       pAdjustMethod = pAdjustMethod_enrich,
                       pvalueCutoff = pvalue_cutoff_enrich, seed = TRUE)
          if (!is.null(res) && nrow(as.data.frame(res)) > 0 && simplify_go) {
            res <- tryCatch(clusterProfiler::simplify(res, cutoff = 0.7, by = "pvalue", select_fun = min),
                            error = function(e) res)
          }
          res
        }, error = function(e) { message("GSEA GO error: ", e$message); NULL })
        out_dir <- make_dir(output_go, ont, comp_name, "GSEA")
        if (write_result(gse_go, file.path(out_dir, paste0("GSEA_GO_", ont, ".csv")))) {
          save_gsea_plots(gse_go, out_dir, paste0(comp_name, "_GSEA_GO_", ont))
        }
      }
      gse_kegg <- tryCatch({
        gseKEGG(geneList = ranked, organism = "hsa",
                pAdjustMethod = pAdjustMethod_enrich,
                pvalueCutoff = pvalue_cutoff_enrich, seed = TRUE)
      }, error = function(e) { message("GSEA KEGG error: ", e$message); NULL })
      out_dir <- make_dir(output_kegg, comp_name, "GSEA")
      if (write_result(gse_kegg, file.path(out_dir, "GSEA_KEGG.csv"))) {
        save_gsea_plots(gse_kegg, out_dir, paste0(comp_name, "_GSEA_KEGG"))
      }
    }
  }
}
message("GO / KEGG enrichment completed: ", output_dir)
'''
