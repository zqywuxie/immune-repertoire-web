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


GO_GSEA_EXPORT_POLICY = "full_before_display_filter_and_simplification"
GO_ORA_EXPORT_POLICY = "full_before_rawP_or_FDR_display_filter"


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
        expression_path: str = "",
        deg_directory: Optional[str] = None,
        differential_metadata: Optional[Dict[str, Any]] = None,
        group_prefix: str = "tpm_",
        comparisons: Optional[Sequence[Sequence[str]]] = None,
        selected_expression_groups=None,
        selected_expression_samples=None,
        pvalue_threshold: float = 0.05,
        logfc_cutoff: float = 1.0,
        enrich_pvalue_cutoff: float = 0.05,
        p_adjust_method: str = "BH",
        show_category: int = 10,
        simplify_go: bool = False,
        do_gsea: bool = True,
        output_name: Optional[str] = None,
        progress_callback=None,
    ) -> GoKeggEnrichmentReport:
        expression_file = Path(expression_path)
        if not deg_directory and (not expression_file.exists() or not expression_file.is_file()):
            raise FileNotFoundError(f"Expression matrix not found: {expression_path}")

        rscript = shutil.which("Rscript")
        if not rscript:
            raise RuntimeError("Rscript is not available. Install R and Bioconductor packages: clusterProfiler, org.Hs.eg.db, enrichplot, DOSE.")

        self.output_parent.mkdir(parents=True, exist_ok=True)
        from flask_app.services.project_storage_paths import allocate_result_dir
        job_id, output_base = allocate_result_dir(self.output_parent, "go-kegg-enrichment")

        if deg_directory:
            from flask_app.services.path_access_service import PathAccessService
            source_root = PathAccessService.validate_read_path(deg_directory)
            copied = self._copy_deg_inputs(source_root, output_base / "DEG", do_gsea=do_gsea)
            source_metadata = dict(differential_metadata or {})
            source_metadata.update(input_mode="deg", reused_differential_results=True,
                                   source_deg_directory=str(source_root), source_deg_files=copied)
            if progress_callback:
                progress_callback(30, "GO/KEGG", "已复用差异表达结果，保留上游筛选标记与统计值")
        else:
            if progress_callback:
                progress_callback(5, "GO/KEGG", "生成差异表达和火山图")

            volcano_report = VolcanoService(output_parent=self.output_parent).generate_expression_report(
                expression_path=str(expression_file),
                group_prefix=group_prefix,
                comparisons=comparisons,
                selected_expression_groups=selected_expression_groups, selected_expression_samples=selected_expression_samples,
                pvalue_threshold=pvalue_threshold,
                logfc_cutoff=logfc_cutoff,
                output_base=output_base,
                job_id=job_id,
                progress_callback=lambda progress, stage, detail, meta=None: (
                    progress_callback(5 + float(progress or 0) * 0.25, stage, detail, meta)
                    if progress_callback else None
                ),
            )

            source_metadata = volcano_report.metadata

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
            str(p_adjust_method or "BH"),
            str(int(show_category or 10)),
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
            error_report = enrichment_dir / "analysis_errors.txt"
            if error_report.is_file():
                failure_detail = error_report.read_text(encoding="utf-8", errors="replace").strip()
            else:
                failure_detail = "\n".join(completed.stderr.strip().splitlines()[-12:])
            if "None of the keys entered are valid keys for 'SYMBOL'" in completed.stderr:
                failure_detail = "差异表达结果中没有可映射的人类基因符号。当前富集使用人类注释，请检查 gene_symbol 列是否为标准基因符号（例如 TP53、CD3D）；其他编号需先转换。"
            elif "Too few background genes mapped to ENTREZID" in completed.stderr:
                failure_detail = "可映射的人类背景基因不足 10 个，无法执行富集。请检查基因符号，并使用完整差异表达结果作为背景。"
            raise RuntimeError(
                "GO/KEGG 富集计算失败。"
                + (f"\n{failure_detail}" if failure_detail else "")
                + f"\n详细日志：{log_path}"
            )

        png_paths = [str(path) for path in sorted(output_base.rglob("*.png"))]
        pdf_paths: List[str] = []
        csv_paths = [str(path) for path in sorted(output_base.rglob("*.csv"))]

        zip_path = output_base / "go_kegg_enrichment_results.zip"

        metadata = {
            **source_metadata,
            "job_id": job_id,
            "module": "go-kegg-enrichment",
            "output_name": output_name or "基因功能与通路富集",
            "show_significance_filter": False,
            "analysis_notes": [
                "复用差异表达结果，沿用来源比较、实际样本范围与筛选标记。" if deg_directory else "按所选表达样本计算差异，再执行功能与通路富集。",
                "差异基因按完整来源表的 significant 标记纳入，分别分析升高、降低和合并集合。",
                f"GO 使用 BP（生物过程）本体；富集校正方法为 {p_adjust_method}，展示阈值为 {enrich_pvalue_cutoff}。",
                "结果表保留完整条目，展示条目数与冗余条目合并仅作用于图表。",
                "已启用 GSEA，按完整差异表的 t 统计量排序。" if do_gsea else "本次未运行 GSEA。",
            ],
            "generated_at": datetime.now().isoformat(),
            "enrich_pvalue_cutoff": enrich_pvalue_cutoff,
            "p_adjust_method": p_adjust_method,
            "go_ontologies": ["BP"],
            "ora_directions": ["Up", "Down", "Both"],
            "ora_export_policy": "complete_clusterProfiler_results_before_display_filter",
            "show_category": show_category,
            "simplify_go": simplify_go,
            "do_gsea": do_gsea,
            "full_go_gsea_tables": [
                path.relative_to(output_base).as_posix()
                for path in sorted(enrichment_dir.rglob("GSEA_GO_*_full.csv"))
            ],
            "go_gsea_export_policy": GO_GSEA_EXPORT_POLICY,
            "go_ora_export_policy": GO_ORA_EXPORT_POLICY,
            "output_counts": {
                "png": len(png_paths),
                "pdf": 0,
                "csv": len(csv_paths),
            },
        }
        (output_base / "go_kegg_enrichment_metadata.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for path in sorted(output_base.rglob("*")):
                if path.is_file() and path.name != zip_path.name:
                    zf.write(path, path.relative_to(output_base).as_posix())

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

    @staticmethod
    def inspect_differential_input(source_root: Path, *, do_gsea: bool) -> List[Path]:
        """Validate full DEG input headers without copying or recalculating results."""
        import pandas as pd
        if not source_root.is_dir():
            raise ValueError("请选择差异表达结果目录。")
        files = [path for path in sorted(source_root.rglob('DEG_*.csv'))
                 if 'significant' not in path.name.lower() and path.is_file()]
        if not files:
            raise ValueError("所选结果没有完整差异表达表，不能仅使用显著基因子集。")
        required = {'gene_symbol', 'significant'} | ({'t'} if do_gsea else set())
        for path in files:
            if not path.resolve().is_relative_to(source_root.resolve()):
                raise ValueError("差异表达文件不在来源结果目录内。")
            if not required.issubset(set(pd.read_csv(path, nrows=0).columns)):
                raise ValueError("差异表达表缺少基因、筛选标记或所需排序统计量，请检查来源分析。")
        return files

    @staticmethod
    def _copy_deg_inputs(source_root: Path, destination: Path, *, do_gsea: bool) -> List[str]:
        """Snapshot full differential tables; never recompute their significance flags."""
        copied = []
        for path in GoKeggEnrichmentService.inspect_differential_input(source_root, do_gsea=do_gsea):
            relative = path.relative_to(source_root)
            target = destination / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            copied.append(relative.as_posix())
        return copied

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
run_go_ora_full <- function(entrez_genes, background_genes, ontology, adjust_method) {
  enrichGO(
    gene = entrez_genes, universe = background_genes, OrgDb = org.Hs.eg.db,
    ont = ontology, pAdjustMethod = adjust_method,
    pvalueCutoff = 1, qvalueCutoff = 1, readable = TRUE
  )
}
# Export before display filtering or GO simplification so fixed downstream
# pathways retain their original NES and probability estimates.
export_full_gsea <- function(res, path, cutoff) {
  if (is.null(res)) return(res)
  write_result(res, path)
  dat <- res@result
  keep <- !is.na(dat$pvalue) & !is.na(dat$p.adjust) &
    dat$pvalue <= cutoff & dat$p.adjust <= cutoff
  res@result <- dat[keep, , drop=FALSE]
  res@params$pvalueCutoff <- cutoff
  res
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
  nshow <- min(showCategory_num, nrow(dat))
  p1 <- dotplot(res, showCategory = nshow, font.size = 10) +
    ggtitle(label) + theme(plot.title = element_text(hjust = 0.5, face = "bold"))
  ggsave(file.path(out_dir, paste0("dotplot_", safe_name(label), ".png")), p1,
         width = 10, height = max(6, nshow * 0.32), dpi = 300, bg = "white")
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

analysis_errors <- character()
record_analysis_error <- function(label, error) {
  text <- paste0(label, ": ", conditionMessage(error))
  analysis_errors <<- c(analysis_errors, text)
  message(text)
  NULL
}
        # Match 06.Transcriptome/02.GO_enrichment.R, whose current scope is BP.
        go_onts <- c("BP")
for (deg_file in deg_files) {
  deg <- read.csv(deg_file, check.names = FALSE)
  comp_name <- sub("^DEG_", "", tools::file_path_sans_ext(basename(deg_file)))
  message("Processing ", comp_name)
    for (direction in c("Up", "Down", "Both")) {
    selected_directions <- if (identical(direction, "Both")) c("Up", "Down") else direction
    genes <- deg$gene_symbol[deg$significant %in% selected_directions]
    if (length(genes) < 5) {
      message("Skip ", comp_name, " ", direction, ": less than 5 significant genes")
      next
    }
    id_map <- suppressMessages(bitr(genes, fromType = "SYMBOL", toType = "ENTREZID", OrgDb = org.Hs.eg.db, drop = TRUE))
    entrez <- id_map$ENTREZID
    if (length(entrez) < 5) next
    for (ont in go_onts) {
      go_res <- tryCatch({
        run_go_ora_full(entrez, bg_entrez, ont, pAdjustMethod_enrich)
      }, error = function(e) record_analysis_error("GO", e))
      out_dir <- make_dir(output_go, ont, comp_name, "ORA", direction)
      full_path <- file.path(out_dir, paste0(comp_name, "_", direction, "_GO_", ont, ".csv"))
      if (write_result(go_res, full_path)) {
        plot_data <- as.data.frame(go_res)
        for (stat_column in c("pvalue", "p.adjust")) {
          plot_res <- go_res
          keep <- !is.na(plot_data[[stat_column]]) & plot_data[[stat_column]] <= pvalue_cutoff_enrich
          plot_res@result <- plot_data[keep, , drop = FALSE]
          if (nrow(plot_res@result) > 0 && simplify_go) {
            plot_res <- tryCatch(
              clusterProfiler::simplify(plot_res, cutoff = 0.7, by = "pvalue", select_fun = min),
              error = function(e) plot_res
            )
          }
          stat_tag <- if (identical(stat_column, "p.adjust")) "FDR" else "rawP"
          save_basic_plots(plot_res, out_dir, paste0(comp_name, "_", direction, "_GO_", ont, "_", stat_tag))
        }
      }
    }
    kegg_res <- tryCatch({
      enrichKEGG(gene = entrez, universe = bg_entrez, organism = "hsa",
                 pAdjustMethod = pAdjustMethod_enrich,
                 pvalueCutoff = pvalue_cutoff_enrich)
    }, error = function(e) record_analysis_error("KEGG", e))
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
                       pvalueCutoff = 1, seed = 20240101, nPermSimple = 100000)
          res <- export_full_gsea(res,
            file.path(make_dir(output_go, ont, comp_name, "GSEA"),
                      paste0("GSEA_GO_", ont, "_full.csv")), pvalue_cutoff_enrich)
          if (!is.null(res) && nrow(as.data.frame(res)) > 0 && simplify_go) {
            res <- tryCatch(clusterProfiler::simplify(res, cutoff = 0.7, by = "pvalue", select_fun = min),
                            error = function(e) res)
          }
          res
        }, error = function(e) record_analysis_error("GSEA GO", e))
        out_dir <- make_dir(output_go, ont, comp_name, "GSEA")
        if (write_result(gse_go, file.path(out_dir, paste0("GSEA_GO_", ont, ".csv")))) {
          save_gsea_plots(gse_go, out_dir, paste0(comp_name, "_GSEA_GO_", ont))
        }
      }
      gse_kegg <- tryCatch({
        gseKEGG(geneList = ranked, organism = "hsa",
                pAdjustMethod = pAdjustMethod_enrich,
                pvalueCutoff = pvalue_cutoff_enrich,
                seed = 20240101, nPermSimple = 100000)
      }, error = function(e) record_analysis_error("GSEA KEGG", e))
      out_dir <- make_dir(output_kegg, comp_name, "GSEA")
      if (write_result(gse_kegg, file.path(out_dir, "GSEA_KEGG.csv"))) {
        save_gsea_plots(gse_kegg, out_dir, paste0(comp_name, "_GSEA_KEGG"))
      }
    }
  }
}
if (length(analysis_errors)) {
  writeLines(analysis_errors, file.path(output_dir, "analysis_errors.txt"))
  stop("富集分析未完整完成：", paste(unique(analysis_errors), collapse = "; "))
}
message("GO / KEGG enrichment completed: ", output_dir)
'''
