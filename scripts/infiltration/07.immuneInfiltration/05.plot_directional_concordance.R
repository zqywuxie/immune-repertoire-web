# C2 group-direction entry extracted from the original consistency core.
################################################################################
## Deconvolution consistency core：原始 C1/C2 一致性分析实现
##
## 本文件由 plot_deconv_consistency.R 调用；A、B、D 已拆分到各自模块。
## C1 使用 raw deconv score 做细胞间 Spearman；C2 使用 subclass 与 cell type
## 的方向一致性，并在提供真实 sample_manifest 时生成样本级 partial Spearman。
##
## C图解析：每个细胞格代表两个细胞类型在当前样本中的共同变化。
##   rho>0表示同步升高/降低，rho<0表示一个升高时另一个倾向降低；
##   这不是因果关系，也不是细胞间直接抑制。C图另输出原始P值和BH-FDR。
##   若改用relative score，负相关还可能来自组成数据的总和约束。
################################################################################

suppressPackageStartupMessages({
  library(data.table)
  library(dplyr)
  library(ggplot2)
  library(reshape2)
  library(patchwork)
  library(ComplexHeatmap)
  library(circlize)
  library(grid)
})

## Command-line overrides are deliberately kept at the configuration boundary.
## The panel implementations below are the original A/B/C code; wrappers may
## change input paths/field names without replacing the C1/C2 plotting logic.
CLI_ARGS <- commandArgs(trailingOnly=TRUE)
cli_value <- function(key, default=NULL) {
  hit <- CLI_ARGS[grepl(paste0("^--", key, "="), CLI_ARGS)]
  if (!length(hit)) return(default)
  sub(paste0("^--", key, "="), "", hit[1])
}
cli_csv <- function(key, default=NULL) {
  z <- cli_value(key, default)
  if (is.null(z) || !nzchar(z)) return(default)
  trimws(strsplit(z, ",", fixed=TRUE)[[1]])
}
SCRIPT_ARG <- commandArgs()[grepl("^--file=", commandArgs())]
SCRIPT_DIR <- if (length(SCRIPT_ARG)) dirname(normalizePath(sub("^--file=", "", SCRIPT_ARG[1]))) else getwd()
PROJECT_ROOT <- normalizePath(file.path(SCRIPT_DIR, ".."), winslash="/", mustWork=FALSE)
source(file.path(SCRIPT_DIR, "..", "common", "configuration", "config.R"), encoding="UTF-8")

## ============================ CONFIG =======================================
CONFIG_BUNDLE <- load_analysis_config(cli_value("config", ""))
ANALYSIS_CONFIG <- CONFIG_BUNDLE$config
CONFIG_PATH <- CONFIG_BUNDLE$path
ANALYSIS_PATHS <- ANALYSIS_CONFIG$paths %||% list()
IMMUNE_CONFIG <- ANALYSIS_CONFIG$immune_infiltration %||% list()
SELECTED_PROFILE <- get_config_profile(
  ANALYSIS_CONFIG, cli_value("profile", ANALYSIS_CONFIG$default_profile %||% "default")
)
PROFILE_INPUT_KEY <- SELECTED_PROFILE$input_path_key %||% "datapoint_input"
PROFILE_INPUT <- ANALYSIS_PATHS[[PROFILE_INPUT_KEY]] %||% ""
CFG <- list(
  relative_file = "",
  absolute_file = "",
  subclass_file = if (nzchar(PROFILE_INPUT)) resolve_config_path(PROFILE_INPUT, CONFIG_PATH) else "",
  sample_manifest_file = resolve_config_path(ANALYSIS_PATHS$sample_manifest %||% "", CONFIG_PATH),
  sample_col = "sample",
  group_col = "category",
  subclass_sample_col = SELECTED_PROFILE$sample_column %||% "sample",
  subclass_group_col = SELECTED_PROFILE$group_column %||% "group",
  expression_file = if (!is.null(ANALYSIS_PATHS$transcriptome_expression)) resolve_config_path(ANALYSIS_PATHS$transcriptome_expression, CONFIG_PATH) else "",
  gene_col = "Gene",
  output_dir = file.path(
    if (!is.null(ANALYSIS_PATHS$output_root)) resolve_config_path(ANALYSIS_PATHS$output_root, CONFIG_PATH)
    else file.path(SCRIPT_DIR, "..", "..", "results"),
    "07.immuneInfiltration", "01.deconv_figure", "05.directional_concordance"
  ),
  group_levels = character(),
  box_scale = "relative",       # deconv scores are relative estimates
  box_break = c(0.95, 1.60),
  corr_scale = "relative",      # match the deconv relative input
  c_cluster_method = "ward.D2", # C图按1-Spearman rho进行对称层次聚类
  seed = 2026,
  fig_dpi = 150,
  a4_width = 8.27,
  a4_height = 11.69,
  ## C2 and supplementary C panels use A4 landscape; C1 is a dedicated square.
  c_width = 11.69,
  c_height = 8.27,
  c1_width = 8.0,
  c1_height = 8.0
)

## Generic input interface.  Supplying --input uses the same deconv table for
## relative/absolute panels, which is appropriate for the current relative
## DCTD output.  Omitting arguments retains the original project defaults.
if (is.null(cli_value("input")) && !is.null(ANALYSIS_PATHS$deconvolution)) {
  CFG$relative_file <- resolve_config_path(ANALYSIS_PATHS$deconvolution, CONFIG_PATH)
}
if (!nzchar(CFG$subclass_file)) stop("Missing configured path: selected profile input_path_key")
if (is.null(cli_value("sample-col")) && !is.null(IMMUNE_CONFIG$sample_column)) CFG$sample_col <- IMMUNE_CONFIG$sample_column
if (is.null(cli_value("group-col")) && !is.null(IMMUNE_CONFIG$group_column)) CFG$group_col <- IMMUNE_CONFIG$group_column
if (is.null(cli_value("group-order")) && length(IMMUNE_CONFIG$group_order %||% character())) CFG$group_levels <- parse_config_values(IMMUNE_CONFIG$group_order)
if (!is.null(cli_value("input"))) {
  CFG$relative_file <- cli_value("input")
}
if (!is.null(cli_value("relative"))) CFG$relative_file <- cli_value("relative")
if (!is.null(cli_value("absolute"))) CFG$absolute_file <- cli_value("absolute")
if (!is.null(cli_value("subclass"))) CFG$subclass_file <- cli_value("subclass")
if (!is.null(cli_value("sample-manifest"))) CFG$sample_manifest_file <- cli_value("sample-manifest")
if (!is.null(cli_value("output"))) CFG$output_dir <- cli_value("output")
if (!is.null(cli_value("sample-col"))) CFG$sample_col <- cli_value("sample-col")
if (!is.null(cli_value("group-col"))) CFG$group_col <- cli_value("group-col")
if (!is.null(cli_value("subclass-sample-col"))) CFG$subclass_sample_col <- cli_value("subclass-sample-col")
if (!is.null(cli_value("subclass-group-col"))) CFG$subclass_group_col <- cli_value("subclass-group-col")
if (!is.null(cli_value("group-order"))) CFG$group_levels <- cli_csv("group-order")
PANEL_ONLY <- "C"
metadata <- read_group_metadata(ANALYSIS_CONFIG, CONFIG_PATH, cli_value("profile", ""))
if (!length(CFG$group_levels)) CFG$group_levels <- attr(metadata, "group_order")
if (!nzchar(CFG$relative_file)) stop("Missing input: configure inputs.deconvolution or --input.")


D_DISPLAY_Q <- 0.05
D_DISPLAY_ABS_RHO <- 0.40
GROUP_LABELS <- setNames(CFG$group_levels, CFG$group_levels)
GROUP_SHORT <- GROUP_LABELS
## A-panel group strip colours: restrained, colour-blind-friendly accents.
## These colours identify clinical groups only; cell-type colours remain separate.
GROUP_PALETTE <- character()
configured_labels <- config_value(ANALYSIS_CONFIG, "groups", "labels")
if (length(configured_labels)) {
  configured_labels <- unlist(configured_labels, use.names=TRUE)
  GROUP_LABELS[names(configured_labels)] <- as.character(configured_labels)
}
missing_group_labels <- setdiff(CFG$group_levels, names(GROUP_LABELS))
if (length(missing_group_labels)) {
  GROUP_LABELS[missing_group_labels] <- missing_group_labels
}
GROUP_LABELS <- GROUP_LABELS[CFG$group_levels]
GROUP_SHORT <- setNames(
  ifelse(nchar(CFG$group_levels) > 8, substr(CFG$group_levels, 1, 8), CFG$group_levels),
  CFG$group_levels
)
GROUP_PALETTE <- setNames(
  rep(c("#4C78A8", "#D98C45", "#59A14F", "#8E79B8", "#8D9CC4"), length.out=length(CFG$group_levels)),
  CFG$group_levels
)

## 稳定的生物学顺序，保证A/B/C/D图例和字段顺序一致。
CELL_ORDER <- c("NK_cells","endothelial_cells","fibroblasts","macrophages",
  "memory_B_cells","memory_CD4_T_cells","memory_CD8_T_cells","monocytes",
  "myeloid_dendritic_cells","naive_B_cells","naive_CD4_T_cells",
  "naive_CD8_T_cells","neutrophils","regulatory_T_cells")
if (is.null(cli_value("cell-cols")) && length(IMMUNE_CONFIG$cell_columns %||% character())) {
  CELL_ORDER <- parse_config_values(IMMUNE_CONFIG$cell_columns)
}
if (!is.null(cli_value("cell-cols"))) CELL_ORDER <- cli_csv("cell-cols")

## D图按免疫大类使用对应marker；每个D小图只展示与该大类相关的基因。
## 这些是预先限定的候选marker，不是根据当前P值再反向挑选。
D_GENE_SETS <- list(
  "B cells" = c("TCL1A", "PAX5", "CD74", "CD79A", "CD79B", "CD37",
                "CD27", "CD38", "TNFRSF13B"),
  "T cells" = c("CD3D", "CD3E", "CD4", "CD8A", "CD8B", "LCK", "TCF7",
                "LEF1", "IL7R", "LTB", "ICOS", "PDCD1", "TOX", "TNFRSF4",
                "GZMK", "GZMB"),
  "NK cells" = c("NKG7", "GNLY", "GZMA", "GZMK", "GZMB", "GZMH", "GZMM"),
  "Myeloid cells" = c("LYZ", "S100A8", "S100A9", "S100A12", "TYROBP",
                      "FCER1G", "CTSS", "LGALS3", "CSF1R", "SPI1", "IRF8",
                      "FCER1A", "CLEC10A", "ITGAX", "CD74"),
  "Granulocytes" = c("S100A8", "S100A9", "S100A12", "CSF3R", "TYROBP", "FCER1G")
)

## 用于B/D分面。分组只改变版式，不合并或重算细胞得分。
CELL_GROUPS <- list(
  "NK cells" = c("NK_cells"),
  "Stromal cells" = c("endothelial_cells","fibroblasts"),
  "Myeloid cells" = c("macrophages","monocytes","myeloid_dendritic_cells"),
  "B cells" = c("memory_B_cells","naive_B_cells"),
  "T cells" = c("memory_CD4_T_cells","memory_CD8_T_cells","naive_CD4_T_cells","naive_CD8_T_cells","regulatory_T_cells"),
  "Granulocytes" = c("neutrophils")
)
D_CELLS <- CELL_ORDER

## 22个亚型在C图中使用较短标签，统计文件仍保留完整字段名。
CELL_SHORT <- setNames(gsub("_", " ", CELL_ORDER), CELL_ORDER)
C2_CELL_SHORT <- c(
  NK_cells="NK", endothelial_cells="Endothelial", fibroblasts="Fibroblast",
  macrophages="Macrophage", memory_B_cells="Memory B",
  memory_CD4_T_cells="Memory CD4 T", memory_CD8_T_cells="Memory CD8 T",
  monocytes="Monocyte", myeloid_dendritic_cells="Myeloid DC",
  naive_B_cells="Naive B", naive_CD4_T_cells="Naive CD4 T",
  naive_CD8_T_cells="Naive CD8 T", neutrophils="Neutrophil",
  regulatory_T_cells="Treg"
)
## ============================================================================

set.seed(CFG$seed)
dir.create(CFG$output_dir, recursive=TRUE, showWarnings=FALSE)
## 结果按Panel归档，便于单独取图、放入主文或补充材料。
PANEL_DIRS <- c(C2="panel_C2")
for (d in unname(PANEL_DIRS))
  dir.create(file.path(CFG$output_dir, d), recursive=TRUE, showWarnings=FALSE)
op <- function(x) {
  panel <- if (grepl("^panel_A_", x)) "A" else
           if (grepl("^panel_B_", x)) "B" else
           if (grepl("^panel_C1_", x)) "C1" else
           if (grepl("^panel_C2_", x)) "C2" else
           if (grepl("^panel_C_", x)) "C" else
           if (grepl("^panel_D_", x)) "D" else NA_character_
  directory <- if (!is.na(panel)) file.path(CFG$output_dir, unname(PANEL_DIRS[panel])) else CFG$output_dir
  directory <- file.path(directory, if (grepl("\\.png$", x, ignore.case=TRUE)) "figure" else "file")
  dir.create(directory, recursive=TRUE, showWarnings=FALSE)
  file.path(directory, x)
}

## Windows R graphics may not have Arial registered for the PDF device; use the
## device-independent sans family so the script runs reproducibly on all hosts.
theme_pub <- theme_classic(base_size=13, base_family="sans") +
  theme(
    axis.line=element_line(linewidth=0.45, colour="black"),
    axis.ticks=element_line(linewidth=0.45, colour="black"),
    panel.grid=element_blank(),
    axis.title=element_text(size=15, face="bold"),
    axis.text=element_text(size=11.5, face="bold", colour="black"),
    legend.title=element_text(size=12, face="bold"),
    legend.text=element_text(size=11.5, face="bold"),
    strip.text=element_text(size=15, face="bold"),
    plot.title=element_text(size=17, face="bold"),
    plot.margin=margin(7, 7, 16, 7)
  )

save_gg <- function(p, stem, width, height) {
  ggsave(bg = "white", op(paste0(stem, ".png")), p, width=width, height=height,
         units="in", dpi=CFG$fig_dpi, limitsize=FALSE)
}

read_result <- function(file) {
  x <- as.data.frame(fread(file, check.names=FALSE, keepLeadingZeros=TRUE), check.names=FALSE)
  names(x) <- trimws(names(x))
  if (CFG$sample_col %in% names(x) && CFG$sample_col != "sample")
    names(x)[names(x) == CFG$sample_col] <- "sample"
  ## CIBERSORTx absolute output uses an underscore for this one LM22 label;
  ## harmonize it with the relative file before joining/plotting.
  if ("B_cells_naive" %in% names(x) && !"B cells naive" %in% names(x))
    names(x)[names(x) == "B_cells_naive"] <- "B cells naive"
  if (!"sample" %in% names(x)) {
    if ("Mixture" %in% names(x)) names(x)[names(x) == "Mixture"] <- "sample"
    else stop("结果文件缺少 sample/Mixture 列: ", file)
  }
  ids <- as.character(x$sample)
  prefix <- IMMUNE_CONFIG$sample_prefix %||% ""
  if (nzchar(prefix)) ids <- ifelse(startsWith(ids, prefix), substring(ids, nchar(prefix) + 1L), ids)
  keep <- !ids %in% (attr(metadata, "excluded_samples") %||% character())
  x <- x[keep, , drop=FALSE]
  x$Group <- metadata_groups(ids[keep], metadata)
  x$Group <- factor(x$Group, levels=CFG$group_levels)
  if (anyNA(x$Group)) stop("Observed metadata groups are outside the configured group order.")
  x
}

relative <- read_result(CFG$relative_file)
absolute <- if (nzchar(CFG$absolute_file)) read_result(CFG$absolute_file) else NULL
if (CFG$corr_scale == "absolute" && is.null(absolute)) stop("Absolute correlations require a separate --absolute input.")
if (!length(IMMUNE_CONFIG$cell_columns) && is.null(cli_value("cell-cols"))) {
  candidates <- setdiff(names(relative), c("sample", "Group", CFG$group_col, "category", "P-value", "Correlation", "RMSE"))
  numeric_cells <- candidates[vapply(relative[candidates], is.numeric, logical(1))]
  CELL_ORDER <- c(intersect(CELL_ORDER, numeric_cells), setdiff(numeric_cells, CELL_ORDER))
}
CELL_SHORT <- setNames(gsub("_", " ", CELL_ORDER), CELL_ORDER)
unknown_labels <- setdiff(CELL_ORDER, names(C2_CELL_SHORT))
C2_CELL_SHORT[unknown_labels] <- CELL_SHORT[unknown_labels]
cell_cols <- intersect(CELL_ORDER, names(relative))
if (!is.null(absolute)) cell_cols <- intersect(cell_cols, names(absolute))
if (length(cell_cols) < 1L) stop("至少需要一个细胞类型。")
for (ct in cell_cols) {
  relative[[ct]][is.na(relative[[ct]])] <- 0
  if (!is.null(absolute)) absolute[[ct]][is.na(absolute[[ct]])] <- 0
}
missing_cells <- setdiff(CELL_ORDER, cell_cols)
if (length(missing_cells)) message("未找到的细胞类型: ", paste(missing_cells, collapse=", "))
cell_order <- CELL_ORDER[CELL_ORDER %in% cell_cols]
cell_group_map <- setNames(rep(names(CELL_GROUPS), lengths(CELL_GROUPS)),
                           unlist(CELL_GROUPS, use.names=FALSE))
cell_group_map <- cell_group_map[cell_order]

## 样本ID和分组一致性检查。
if (!is.null(absolute)) {
common_samples <- intersect(relative$sample, absolute$sample)
if (length(common_samples) != nrow(relative) || length(common_samples) != nrow(absolute))
  stop("relative与absolute样本ID不完全一致，拒绝继续绘图")
relative <- relative[match(common_samples, relative$sample), ]
absolute <- absolute[match(common_samples, absolute$sample), ]
if (any(as.character(relative$Group) != as.character(absolute$Group)))
  stop("relative与absolute的Group标签不一致")
}


## No sample-level manifest currently links the profile table to the deconvolution table.
## Therefore C2 deliberately compares group-level effects, not paired
## sample-level correlations.
subclass_source <- tryCatch(
  as.data.frame(data.table::fread(CFG$subclass_file, check.names=FALSE, keepLeadingZeros=TRUE),
                check.names=FALSE),
  error=function(e) NULL
)
if (!is.null(subclass_source)) {
  if (CFG$subclass_sample_col %in% names(subclass_source) &&
      CFG$subclass_sample_col != "sample")
    names(subclass_source)[names(subclass_source) == CFG$subclass_sample_col] <- "sample"
  if (CFG$subclass_group_col %in% names(subclass_source) &&
      CFG$subclass_group_col != "Symptoms")
    names(subclass_source)[names(subclass_source) == CFG$subclass_group_col] <- "Symptoms"
}
## Match the established subclass order in Profile/Box.py.
## This order is retained in the C2 heatmap y-axis and exported statistics.
subclass_candidates <- c("IGHM", "IGHD", "IGHA1", "IGHA2", "IGHG3",
                         "IGHG4", "IGHGP", "IGHE")
subclass_labels <- c(IGHA1="IgA1", IGHA2="IgA2", IGHD="IgD", IGHE="IgE",
                     IGHG3="IgG3", IGHG4="IgG4", IGHGP="IgGP", IGHM="IgM")

safe_wilcox <- function(x, g, g1, g2) {
  keep <- is.finite(x) & !is.na(g) & as.character(g) %in% c(g1, g2)
  x <- x[keep]; g <- droplevels(factor(as.character(g[keep]), levels=c(g1, g2)))
  if (length(x) < 4 || sum(g == g1) < 2 || sum(g == g2) < 2) return(NA_real_)
  tryCatch(suppressWarnings(wilcox.test(x ~ g, exact=FALSE)$p.value),
           error=function(e) NA_real_)
}

directional_wilcox <- function(x, g, g1, g2) {
  keep <- is.finite(x) & !is.na(g) & as.character(g) %in% c(g1, g2)
  x <- x[keep]
  g <- factor(as.character(g[keep]), levels=c(g1, g2))
  x1 <- x[g == g1]; x2 <- x[g == g2]
  if (length(x1) < 2 || length(x2) < 2) {
    return(data.frame(p_two_sided=NA_real_, p_up=NA_real_, p_down=NA_real_))
  }
  data.frame(
    p_two_sided=suppressWarnings(wilcox.test(x1, x2, exact=FALSE)$p.value),
    p_up=suppressWarnings(wilcox.test(x1, x2, alternative="greater", exact=FALSE)$p.value),
    p_down=suppressWarnings(wilcox.test(x1, x2, alternative="less", exact=FALSE)$p.value)
  )
}

group_effect <- function(df, value_col, group_col, g1, g2) {
  x <- suppressWarnings(as.numeric(df[[value_col]]))
  g <- as.character(df[[group_col]])
  keep <- is.finite(x) & !is.na(g) & g %in% c(g1, g2)
  x1 <- x[keep & g == g1]; x2 <- x[keep & g == g2]
  data.frame(effect=if (length(x1) && length(x2)) median(x1, na.rm=TRUE) - median(x2, na.rm=TRUE) else NA_real_,
             p_value=safe_wilcox(x, g, g1, g2),
             n_g1=length(x1), n_g2=length(x2), stringsAsFactors=FALSE)
}

if (!is.null(subclass_source) && "Symptoms" %in% names(subclass_source)) {
  ## Match Profile_new/Box.py: missing numeric subclass observations are
  ## treated as zero (compatibility mode), so C2 and the subclass Box plots
  ## test the same values. The policy is recorded for auditability.
  subclass_numeric <- setdiff(names(subclass_source),
                              c("sample", "Symptoms", "Group"))
  for (nm in subclass_numeric) {
    if (is.numeric(subclass_source[[nm]]) || is.character(subclass_source[[nm]])) {
      vv <- suppressWarnings(as.numeric(subclass_source[[nm]]))
      vv[is.na(vv)] <- 0
      subclass_source[[nm]] <- vv
    }
  }
  subclass_source$Group <- as.character(subclass_source$Symptoms)
  subclass_source$Group <- factor(subclass_source$Group,
                                   levels=CFG$group_levels)
  ## Use explicit indexing rather than intersect() so the configured order
  ## cannot be replaced by the source CSV column order.
  subclass_available <- subclass_candidates[subclass_candidates %in% names(subclass_source)]
  subclass_coverage <- sapply(subclass_available, function(x)
    mean(is.finite(suppressWarnings(as.numeric(subclass_source[[x]])))))
  subclass_cols <- names(subclass_coverage[subclass_coverage >= 0.80])
  if (!length(subclass_cols)) subclass_cols <- subclass_available
  write.csv(data.frame(Subclass=subclass_available,
                       Label=unname(subclass_labels[subclass_available]),
                       Coverage=as.numeric(subclass_coverage[subclass_available]),
                       Included=subclass_available %in% subclass_cols),
            op("panel_C2_subclass_coverage.csv"), row.names=FALSE)

  make_c2_plot <- function(g1, g2, suffix, title_text) {
    g1_deconv <- g1
    g2_deconv <- g2
    cell_stats <- bind_rows(lapply(cell_order, function(ct) {
      z <- group_effect(relative, ct, "Group", g1_deconv, g2_deconv)
      dz <- directional_wilcox(relative[[ct]], relative$Group, g1_deconv, g2_deconv)
      data.frame(CellType=ct, effect=z$effect, p_value=z$p_value,
                 p_up=dz$p_up, p_down=dz$p_down,
                 n_g1=z$n_g1, n_g2=z$n_g2, stringsAsFactors=FALSE)
    }))
    ## In the combined ABC run, retain the original B-derived BH family.  In
    ## C-only mode B is intentionally skipped, so reproduce the same
    ## per-comparison cell-level adjustment locally rather than changing the
    ## C2 plotting/statistical logic.
    if (exists("pair_stats", inherits=FALSE)) {
      cell_stats$q_value <- pair_stats$q_value[match(
        paste(cell_stats$CellType, g2_deconv),
        paste(as.character(pair_stats$CellType), pair_stats$Group2))]
    } else {
      cell_stats$q_value <- p.adjust(cell_stats$p_value, method="BH")
    }
    subclass_stats <- bind_rows(lapply(subclass_cols, function(sc) {
      z <- group_effect(subclass_source, sc, "Group", g1, g2)
      dz <- directional_wilcox(subclass_source[[sc]], subclass_source$Group, g1, g2)
      data.frame(Subclass=sc, effect=z$effect, p_value=z$p_value,
                 p_up=dz$p_up, p_down=dz$p_down,
                 n_g1=z$n_g1, n_g2=z$n_g2, stringsAsFactors=FALSE)
    }))
    subclass_stats$q_value <- p.adjust(subclass_stats$p_value, method="BH")
    ## Compact C2 display: one matrix; colour encodes direction and a white
    ## outlined dot encodes joint raw-p evidence from both modalities.
    ordered_cells <- cell_order
    c2 <- expand.grid(Subclass=subclass_cols, CellType=ordered_cells,
                      stringsAsFactors=FALSE) %>%
      left_join(cell_stats, by="CellType", suffix=c("_cell", "")) %>%
      rename(cell_effect=effect, cell_p=p_value, cell_p_up=p_up,
             cell_p_down=p_down, cell_q=q_value,
             cell_n_g1=n_g1, cell_n_g2=n_g2) %>%
      left_join(subclass_stats, by="Subclass", suffix=c("", "_subclass")) %>%
      rename(subclass_effect=effect, subclass_p=p_value, subclass_p_up=p_up,
             subclass_p_down=p_down, subclass_q=q_value,
             subclass_n_g1=n_g1, subclass_n_g2=n_g2) %>%
      mutate(cell_sign=sign(cell_effect), subclass_sign=sign(subclass_effect),
             p_both_up=pmax(cell_p_up, subclass_p_up),
             p_both_down=pmax(cell_p_down, subclass_p_down),
             p_opposite_cell_up=pmax(cell_p_up, subclass_p_down),
             p_opposite_cell_down=pmax(cell_p_down, subclass_p_up),
             p_concordant=pmin(1, 2 * pmin(p_both_up, p_both_down)),
             p_discordant=pmin(1, 2 * pmin(p_opposite_cell_up, p_opposite_cell_down)),
             joint_p=ifelse(cell_sign == subclass_sign, p_concordant, p_discordant),
             evidence=is.finite(joint_p) & joint_p < 0.05,
             evidence_score=ifelse(is.finite(joint_p),
                                   pmin(6, pmax(0.15, -log10(pmax(joint_p, 1e-300)))),
                                   NA_real_),
             concordance=ifelse(!is.finite(cell_sign) | !is.finite(subclass_sign) | cell_sign == 0 | subclass_sign == 0,
                                "No estimable effect",
                                ifelse(cell_sign == subclass_sign,
                                       "Concordant", "Discordant")),
             direction=ifelse(evidence & cell_sign > 0 & subclass_sign > 0, "↑ / ↑",
                         ifelse(evidence & cell_sign < 0 & subclass_sign < 0, "↓ / ↓",
                         ifelse(evidence, "↑ / ↓", ""))))
    c2$Group1 <- g1
    c2$Group2 <- g2
    c2$directional_q <- p.adjust(c2$joint_p, method="BH")
    write.csv(c2, op(paste0("panel_C2_", suffix, "_stats.csv")), row.names=FALSE)
    c2$Subclass <- factor(c2$Subclass, levels=rev(subclass_cols),
                          labels=rev(unname(subclass_labels[subclass_cols])))
    c2$CellType <- factor(c2$CellType, levels=ordered_cells,
                          labels=unname(C2_CELL_SHORT[ordered_cells]))
    p <- ggplot(c2, aes(x=CellType, y=Subclass)) +
      geom_tile(fill="grey98", colour="grey88", linewidth=0.35,
                height=0.92, width=0.92) +
      geom_point(aes(size=evidence_score, fill=concordance, alpha=evidence),
                 shape=21, colour="grey65", stroke=0.25) +
      geom_point(data=dplyr::filter(c2, evidence),
                 aes(size=evidence_score, fill=concordance, alpha=evidence),
                 shape=21, colour="black", stroke=0.95) +
      scale_fill_manual(values=c("Concordant"="#D84A3A",
                                 "Discordant"="#4C78A8",
                                 "No estimable effect"="grey88"),
                        breaks=c("Concordant", "Discordant", "No estimable effect"),
                        labels=c("方向一致", "方向相反", "无法估计"),
                        drop=FALSE) +
      scale_alpha_manual(values=c(`TRUE`=1, `FALSE`=0.22), guide="none") +
      scale_size_continuous(name="方向联合证据\n-log10(联合 p 值)",
                            limits=c(0.15, 6), range=c(1.0, 8.0),
                            breaks=c(1.3, 2, 3, 6),
                            labels=c("*", "**", "***", "***")) +
      scale_x_discrete(drop=FALSE) +
      scale_y_discrete(drop=FALSE, expand=expansion(add=c(0.2, 0.3))) +
      labs(title=title_text,
           x="浸润细胞类型", y="免疫球蛋白亚类", fill=NULL) +
      theme_pub +
      theme(axis.text.x=element_text(angle=45, hjust=1, vjust=1, size=11.5, face="bold"),
            axis.text.y=element_text(size=11.5, face="bold"),
            axis.title.x=element_text(size=15, face="bold"),
            axis.title.y=element_text(size=15, face="bold"),
            plot.title=element_text(size=17, face="bold", hjust=0.5),
            legend.position="right", legend.title=element_text(size=12, face="bold"),
            legend.text=element_text(size=11.5, face="bold"),
            plot.margin=margin(4, 5, 3, 4))
    save_gg(p, paste0("panel_C2_", suffix, "_subclass_deconv"),
            11.4, 7.2)
    writeLines(c(
      paste0("C2 comparison: ", g1, " vs ", g2),
      "This panel compares group effects, not sample-level correlations.",
      "Effects are median differences within each modality; subclass and cell-type Wilcoxon tests are calculated separately.",
      "The compact matrix uses one cell-type order for all columns.",
      "Tile colour shows directional concordance (red=concordant, blue=discordant).",
      "点大小对应方向联合 p 值；联合检验沿用原始单侧 Wilcoxon 组合公式。",
      "方向联合 p 值小于 0.05 时强调显示；BH 校正结果见 directional_q。"
    ), op(paste0("panel_C2_", suffix, "_interpretation.txt")))
  }
  comparison_groups <- intersect(CFG$group_levels, intersect(unique(as.character(relative$Group)),
                                                            unique(as.character(subclass_source$Group))))
  pairs <- resolve_group_comparisons(IMMUNE_CONFIG$comparisons, comparison_groups)
  if (length(subclass_cols)) for (pair in pairs) {
    suffix <- paste0("comparison_", match(pair[1], comparison_groups), "_", match(pair[2], comparison_groups))
    make_c2_plot(pair[1], pair[2], suffix, paste("亚类与细胞的组间变化方向：", paste(pair, collapse=" 与 ")))
  }


} else { stop("缺少可用的亚类指标与分组。") }
