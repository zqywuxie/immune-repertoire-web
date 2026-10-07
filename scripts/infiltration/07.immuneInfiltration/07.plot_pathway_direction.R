################################################################################
## Deconvolution panel D
## D1: GO-BP GSEA vs deconvolution group-direction concordance
## D2: Hallmark ssGSEA vs deconvolution sample-level partial Spearman
################################################################################

suppressPackageStartupMessages({
  library(data.table)
  library(dplyr)
  library(ggplot2)
})

## Command-line configuration layer. The D1/D1-Sample/D2 implementations
## below remain the original plotting/statistical code.
D_ARGS <- commandArgs(trailingOnly=TRUE)
darg <- function(key, default=NULL) {
  hit <- D_ARGS[grepl(paste0("^--", key, "="), D_ARGS)]
  if (!length(hit)) return(default)
  sub(paste0("^--", key, "="), "", hit[1])
}
darg_csv <- function(key, default=NULL) {
  z <- darg(key, default)
  if (is.null(z) || !nzchar(z)) return(default)
  trimws(strsplit(z, ",", fixed=TRUE)[[1]])
}
script_arg <- commandArgs()[grepl("^--file=", commandArgs())]
SCRIPT_DIR <- if (length(script_arg)) dirname(normalizePath(sub("^--file=", "", script_arg[1]))) else getwd()
PROJECT_ROOT <- normalizePath(file.path(SCRIPT_DIR, ".."), winslash="/", mustWork=FALSE)
source(file.path(SCRIPT_DIR, "..", "common", "configuration", "config.R"), encoding="UTF-8")

CONFIG_BUNDLE <- load_analysis_config(darg("config", ""))
ANALYSIS_CONFIG <- CONFIG_BUNDLE$config
CONFIG_PATH <- CONFIG_BUNDLE$path
ANALYSIS_PATHS <- ANALYSIS_CONFIG$paths %||% list()
IMMUNE_CONFIG <- ANALYSIS_CONFIG$immune_infiltration %||% list()
TRANSCRIPTOME_CONFIG <- ANALYSIS_CONFIG$transcriptome %||% list()
metadata <- read_group_metadata(ANALYSIS_CONFIG, CONFIG_PATH, darg("profile", ""))
GROUP_LEVELS <- attr(metadata, "group_order")
configured_comparisons <- resolve_group_comparisons(IMMUNE_CONFIG$comparisons %||%
                                                     TRANSCRIPTOME_CONFIG$comparisons, GROUP_LEVELS)
if (!is.null(darg("comparison"))) {
  configured_comparisons <- resolve_group_comparisons(list(strsplit(darg("comparison"), ":", fixed=TRUE)[[1]]), GROUP_LEVELS)
}
configured_pair <- configured_comparisons[[1]]
configured_comparison_name <- paste(configured_pair, collapse="_vs_")

set.seed(2026)
ROOT <- darg("root", PROJECT_ROOT)
OUT <- darg("output", file.path(
  if (!is.null(ANALYSIS_PATHS$transcriptome_results)) resolve_config_path(ANALYSIS_PATHS$transcriptome_results, CONFIG_PATH)
  else file.path(SCRIPT_DIR, "..", "..", "results", "06.Transcriptome"),
  "..", "07.immuneInfiltration", "01.deconv_figure", "05.pathway_concordance"
))
dir.create(file.path(OUT, "panel_D1_GO"), recursive=TRUE, showWarnings=FALSE)
dir.create(file.path(OUT, "panel_D1_GO_sample"), recursive=TRUE, showWarnings=FALSE)
dir.create(file.path(OUT, "panel_D2_Hallmark"), recursive=TRUE, showWarnings=FALSE)

DECONV_FILE <- darg(
  "input",
  if (!is.null(ANALYSIS_PATHS$deconvolution)) resolve_config_path(ANALYSIS_PATHS$deconvolution, CONFIG_PATH) else ""
)
EXPR_FILE <- darg(
  "expression",
  if (!is.null(ANALYSIS_PATHS$transcriptome_expression)) resolve_config_path(ANALYSIS_PATHS$transcriptome_expression, CONFIG_PATH) else ""
)
GO_FILE <- darg(
  "go-gsea",
  if (!is.null(ANALYSIS_PATHS$transcriptome_results)) {
    file.path(
      resolve_config_path(ANALYSIS_PATHS$transcriptome_results, CONFIG_PATH),
      "02.GO", "BP", configured_comparison_name, "GSEA", "GSEA_GO_BP.csv"
    )
  } else {
    file.path(ROOT, "transcriptome", "enrichment_results", "02.GO", "BP",
              configured_comparison_name, "GSEA", "GSEA_GO_BP.csv")
  }
)
HALLMARK_FILE <- darg("hallmark", if (!is.null(ANALYSIS_PATHS$hallmark_database)) {
  resolve_config_path(ANALYSIS_PATHS$hallmark_database, CONFIG_PATH)
} else "")
SAMPLE_COL <- darg("sample-col", IMMUNE_CONFIG$sample_column %||% "sample")
GROUP_COL <- darg("group-col", IMMUNE_CONFIG$group_column %||% "category")
GENE_COL <- darg("gene-col", TRANSCRIPTOME_CONFIG$gene_column %||% "Gene")

GROUP_LEVELS <- attr(metadata, "group_order")
GROUP_LEVELS <- parse_config_values(GROUP_LEVELS)
if (!is.null(darg("group-order"))) GROUP_LEVELS <- darg_csv("group-order")
CELL_ORDER <- c(
  "NK_cells", "endothelial_cells", "fibroblasts", "macrophages",
  "memory_B_cells", "memory_CD4_T_cells", "memory_CD8_T_cells", "monocytes",
  "myeloid_dendritic_cells", "naive_B_cells", "naive_CD4_T_cells",
  "naive_CD8_T_cells", "neutrophils", "regulatory_T_cells"
)
if (!is.null(darg("cell-cols"))) CELL_ORDER <- darg_csv("cell-cols")
CELL_LABEL <- c(
  NK_cells="NK", endothelial_cells="Endothelial", fibroblasts="Fibroblast",
  macrophages="Macrophage", memory_B_cells="Memory B",
  memory_CD4_T_cells="Memory CD4 T", memory_CD8_T_cells="Memory CD8 T",
  monocytes="Monocyte", myeloid_dendritic_cells="Myeloid DC",
  naive_B_cells="Naive B", naive_CD4_T_cells="Naive CD4 T",
  naive_CD8_T_cells="Naive CD8 T", neutrophils="Neutrophil",
  regulatory_T_cells="Treg"
)
missing_cell_labels <- setdiff(CELL_ORDER, names(CELL_LABEL))
if (length(missing_cell_labels))
  CELL_LABEL[missing_cell_labels] <- gsub("_", " ", missing_cell_labels)

theme_d <- theme_classic(base_size=13, base_family="sans") +
  theme(
    axis.line=element_line(linewidth=0.45, colour="black"),
    axis.ticks=element_line(linewidth=0.45, colour="black"),
    axis.text=element_text(size=12, colour="black", face="bold"),
    axis.title=element_text(size=15, face="bold"),
    plot.title=element_text(size=17, face="bold", hjust=0.5),
    plot.subtitle=element_text(size=10.5, face="italic", hjust=0.5),
    legend.title=element_text(size=12, face="bold"),
    legend.text=element_text(size=11.5, face="bold"),
    legend.key=element_blank(),
    panel.grid=element_blank()
  )

save_plot <- function(p, path_no_ext, width, height) {
  path_no_ext <- file.path(dirname(path_no_ext), "figure", basename(path_no_ext))
  dir.create(dirname(path_no_ext), recursive=TRUE, showWarnings=FALSE)
  ggsave(bg = "white", paste0(path_no_ext, ".png"), p, width=width, height=height,
         units="in", dpi=150, limitsize=FALSE)
}

## D1-Sample uses the same Bioconductor GO annotation source as
## transcriptome/GO_enrichment.R.  GOALL propagates descendant annotations to
## broad parent terms; SYMBOL keeps the identifier type aligned with Gene.
GO_REQUIRED_PACKAGES <- c("AnnotationDbi", "org.Hs.eg.db", "GO.db")
GO_MIN_GENES <- 10L
build_go_bp_sets <- function(go_ids) {
  missing <- GO_REQUIRED_PACKAGES[
    !vapply(GO_REQUIRED_PACKAGES, requireNamespace, logical(1), quietly=TRUE)
  ]
  if (length(missing)) {
    stop(
      "D1-Sample requires Bioconductor packages: ", paste(missing, collapse=", "),
      ". Install with: BiocManager::install(c('org.Hs.eg.db','GO.db','AnnotationDbi'))",
      call.=FALSE
    )
  }
  ann <- AnnotationDbi::select(
    org.Hs.eg.db::org.Hs.eg.db,
    keys=unique(go_ids), keytype="GOALL",
    columns=c("SYMBOL", "ONTOLOGYALL")
  )
  ann <- ann[ann$ONTOLOGYALL == "BP" & !is.na(ann$SYMBOL), , drop=FALSE]
  out <- split(toupper(as.character(ann$SYMBOL)), as.character(ann$GOALL))
  out <- lapply(out, unique)
  setNames(lapply(go_ids, function(id) out[[id]] %||% character()), go_ids)
}
`%||%` <- function(x, y) if (is.null(x)) y else x

deconv <- fread(DECONV_FILE, check.names=FALSE, colClasses=list(character=c("sample", "Mixture"))) |> as.data.frame(check.names=FALSE)
if (SAMPLE_COL %in% names(deconv) && SAMPLE_COL != "sample")
  names(deconv)[names(deconv) == SAMPLE_COL] <- "sample"
if (!"sample" %in% names(deconv) && "Mixture" %in% names(deconv))
  names(deconv)[names(deconv) == "Mixture"] <- "sample"
if (!"sample" %in% names(deconv)) stop("Deconvolution input is missing sample identifiers.")
ids <- as.character(deconv$sample)
prefix <- IMMUNE_CONFIG$sample_prefix %||% ""
if (nzchar(prefix)) ids <- ifelse(startsWith(ids, prefix), substring(ids, nchar(prefix)+1L), ids)
keep <- !ids %in% (attr(metadata, "excluded_samples") %||% character())
deconv <- deconv[keep, , drop=FALSE]
deconv$category <- factor(metadata_groups(ids[keep], metadata), levels=GROUP_LEVELS)
stopifnot(!anyDuplicated(deconv$sample))
if (is.null(darg("cell-cols"))) {
  requested_cells <- parse_config_values(IMMUNE_CONFIG$cell_columns)
  if (length(requested_cells)) CELL_ORDER <- requested_cells else {
    candidates <- setdiff(names(deconv), c("sample", "category", GROUP_COL, "P-value", "Correlation", "RMSE"))
    CELL_ORDER <- candidates[vapply(deconv[candidates], is.numeric, logical(1))]
  }
}
if (length(setdiff(CELL_ORDER, names(deconv)))) stop("Requested cell columns are absent.")
CELL_LABEL[setdiff(CELL_ORDER, names(CELL_LABEL))] <- gsub("_", " ", setdiff(CELL_ORDER, names(CELL_LABEL)))
for (ct in CELL_ORDER) {
  deconv[[ct]] <- suppressWarnings(as.numeric(deconv[[ct]]))
  deconv[[ct]][is.na(deconv[[ct]])] <- 0
}

observed_groups <- intersect(GROUP_LEVELS, unique(as.character(deconv$category)))
requested_pairs <- if (!is.null(darg("comparison"))) {
  list(strsplit(darg("comparison"), ":", fixed=TRUE)[[1]])
} else IMMUNE_CONFIG$comparisons %||% TRANSCRIPTOME_CONFIG$comparisons
configured_comparisons <- resolve_group_comparisons(requested_pairs, observed_groups)
configured_pair <- configured_comparisons[[1]]
configured_comparison_name <- paste(configured_pair, collapse="_vs_")
if (is.null(darg("go-gsea")))
  GO_FILE <- file.path(dirname(dirname(dirname(GO_FILE))), configured_comparison_name, "GSEA", "GSEA_GO_BP.csv")
if (length(configured_comparisons) > 1L) {
  forwarded <- D_ARGS[!grepl("^--output=", D_ARGS)]
  for (pair in configured_comparisons) {
    pair_out <- file.path(OUT, paste(pair, collapse="_vs_"))
    status <- system2(file.path(R.home("bin"), "Rscript"),
      shQuote(c(file.path(SCRIPT_DIR, "05.plot_deconv_pathway_concordance.R"), forwarded,
                paste0("--comparison=", paste(pair, collapse=":")), paste0("--output=", pair_out))))
    if (status != 0L) stop("Pathway comparison failed: ", paste(pair, collapse=" vs "))
  }
  quit(save="no", status=0)
}
wilcox_effect <- function(x, group, g1=configured_pair[1], g2=configured_pair[2]) {
  keep <- is.finite(x) & !is.na(group) & as.character(group) %in% c(g1, g2)
  x <- x[keep]; group <- factor(as.character(group[keep]), levels=c(g1, g2))
  x1 <- x[group == g1]; x2 <- x[group == g2]
  p <- if (length(x1) >= 2 && length(x2) >= 2)
    suppressWarnings(wilcox.test(x1, x2, exact=FALSE)$p.value) else NA_real_
  p_up <- if (length(x1) >= 2 && length(x2) >= 2)
    suppressWarnings(wilcox.test(x1, x2, alternative="greater", exact=FALSE)$p.value) else NA_real_
  p_down <- if (length(x1) >= 2 && length(x2) >= 2)
    suppressWarnings(wilcox.test(x1, x2, alternative="less", exact=FALSE)$p.value) else NA_real_
  data.frame(effect=median(x1, na.rm=TRUE)-median(x2, na.rm=TRUE),
             p_value=p, p_up=p_up, p_down=p_down,
             n_g1=length(x1), n_g2=length(x2))
}

## --------------------------- D1: GO-BP -------------------------------------
GO_MANIFEST <- data.frame(
  Module=c("Adaptive immunity", "淋巴细胞活化", "T-cell immunity",
           "B-cell immunity", "Humoral immunity", "Innate immunity",
           "Myeloid immunity", "Inflammation", "Cytokine signalling", "Complement"),
  ID=c("GO:0002250", "GO:0046649", "GO:0042110", "GO:0042113", "GO:0006959",
       "GO:0045087", "GO:0002274", "GO:0006954", "GO:0019221", "GO:0006956"),
  Label=c("适应性免疫应答", "淋巴细胞活化", "T 细胞活化",
          "B 细胞活化", "体液免疫应答", "先天免疫应答",
          "髓系白细胞活化", "炎症反应",
          "细胞因子介导的信号传导", "补体活化")
)

if (file.exists(GO_FILE)) {
go <- fread(GO_FILE, check.names=FALSE) |> as.data.frame(check.names=FALSE)
go_sel <- GO_MANIFEST |>
  left_join(go[, c("ID", "Description", "setSize", "NES", "pvalue", "p.adjust", "qvalue")],
            by="ID")
if (any(!is.finite(go_sel$NES))) stop("One or more configured GO terms are absent")
write.csv(go_sel, file.path(OUT, "panel_D1_GO", "D1_GO_pathway_manifest.csv"),
          row.names=FALSE)

cell_effect <- bind_rows(lapply(CELL_ORDER, function(ct) {
  z <- wilcox_effect(deconv[[ct]], deconv$category)
  data.frame(CellType=ct, z, check.names=FALSE)
})) |>
  mutate(q_value=p.adjust(p_value, method="BH"))
write.csv(cell_effect, file.path(OUT, "panel_D1_GO", "D1_cell_group_statistics.csv"),
          row.names=FALSE)

d1 <- expand.grid(ID=GO_MANIFEST$ID, CellType=CELL_ORDER, stringsAsFactors=FALSE) |>
  left_join(go_sel[, c("ID", "Module", "Label", "NES", "pvalue", "p.adjust")], by="ID") |>
  rename(pathway_p=pvalue, pathway_q=p.adjust) |>
  left_join(cell_effect, by="CellType") |>
  rename(cell_effect=effect, cell_p=p_value, cell_q=q_value) |>
  mutate(
    concordance=ifelse(NES == 0 | cell_effect == 0, "Neutral", ifelse(sign(NES)==sign(cell_effect), "Concordant", "Discordant")),
    ## clusterProfiler::gseGO() uses the fgsea backend here. Its pvalue is
    ## already the directional enrichment p-value associated with the sign of
    ## NES; do not divide it by two a second time. A pathway contributes
    ## evidence only in the direction indicated by NES.
    pathway_p_up=ifelse(NES > 0, pathway_p, 1),
    pathway_p_down=ifelse(NES < 0, pathway_p, 1),
    p_both_up=pmax(pathway_p_up, p_up),
    p_both_down=pmax(pathway_p_down, p_down),
    p_opposite_pathway_up=pmax(pathway_p_up, p_down),
    p_opposite_pathway_down=pmax(pathway_p_down, p_up),
    p_concordant=pmin(1, 2*pmin(p_both_up, p_both_down)),
    p_discordant=pmin(1, 2*pmin(p_opposite_pathway_up, p_opposite_pathway_down)),
    joint_p=ifelse(concordance == "Neutral", 1, ifelse(concordance == "Concordant", p_concordant, p_discordant)),
    joint_q=p.adjust(joint_p, method="BH"),
    joint_raw_significant=is.finite(joint_p) & joint_p < 0.05,
    evidence=pmin(6, pmax(0.15, -log10(pmax(joint_p, 1e-300))))
  )
d1$Group1 <- configured_pair[1]
d1$Group2 <- configured_pair[2]
write.csv(d1, file.path(OUT, "panel_D1_GO", "D1_GO_cell_full_statistics.csv"),
          row.names=FALSE)

d1$CellLabel <- factor(d1$CellType, levels=CELL_ORDER, labels=CELL_LABEL[CELL_ORDER])
d1$PathwayLabel <- factor(d1$Label, levels=rev(GO_MANIFEST$Label))
p_d1 <- ggplot(d1, aes(CellLabel, PathwayLabel)) +
  geom_tile(fill="grey98", colour="grey88", linewidth=0.30) +
  geom_point(aes(size=evidence, fill=concordance, alpha=joint_raw_significant),
             shape=21, colour="grey65", stroke=0.25) +
  geom_point(data=dplyr::filter(d1, joint_raw_significant),
             aes(size=evidence, fill=concordance, alpha=joint_raw_significant),
             shape=21, colour="black", stroke=0.95) +
  scale_fill_manual(values=c(Concordant="#D84A3A", Discordant="#2563EB", Neutral="#94A3B8"),
                    labels=c(Concordant="方向一致", Discordant="方向相反", Neutral="无方向差异"), name=NULL) +
  scale_alpha_manual(values=c(`TRUE`=1, `FALSE`=0.20), guide="none") +
  scale_size_continuous(name="联合证据\n-log10(联合 p 值)",
                        limits=c(0.15,6), range=c(1.0,8.2),
                        breaks=c(1.3,2,3,6),
                        labels=c("*","**","***","***")) +
  labs(title="GO-BP 通路与浸润方向比较",
       x="免疫细胞类型", y="GO 生物过程") +
  theme_d +
  theme(axis.text.x=element_text(angle=45, hjust=1, size=11.5),
        axis.text.y=element_text(size=11.5),
        legend.position="right", plot.margin=margin(5,5,4,5))
save_plot(p_d1, file.path(OUT, "panel_D1_GO", "panel_D1_GO_cell_concordance"),
          11.4, 7.2)


} else { stop("完整 GO-BP GSEA 来源不存在。") }
