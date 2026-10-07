# Platform C1 entry: extracted from original consistency core through the C1 report.
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
    "07.immuneInfiltration", "01.deconv_figure", "04.consistency"
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
CFG$corr_scale <- cli_value("score-type", "other")
if (!CFG$corr_scale %in% c("relative", "absolute", "other")) stop("Invalid score type")
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
PANEL_DIRS <- c(C="panel_C", C1="panel_C1")
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
if (length(cell_cols) < 2L) stop("At least two numeric cell-type columns are required.")
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

## ------------------------------- Panel C -----------------------------------
## 计算Spearman rho、原始P值和BH-FDR。C图默认absolute，见CFG$corr_scale。
corr_source <- if (CFG$corr_scale == "absolute") absolute else relative
corr_cells <- cell_order
## 保存未校正的pooled Spearman，作为补充分析。
cm_pooled <- cor(as.matrix(corr_source[, corr_cells, drop=FALSE]),
                 method="spearman", use="pairwise.complete.obs")

## 主图：group-adjusted partial Spearman。
## 对每种细胞分数先秩转换，再回归Group；残差间Pearson相关等价于
## 对Group进行调整的rank-residual partial Spearman。
group_c <- droplevels(corr_source$Group)
resid_c <- sapply(corr_cells, function(ct) {
  rv <- rank(corr_source[[ct]], ties.method="average", na.last="keep")
  residuals(lm(rv ~ group_c, na.action=na.exclude))
})
colnames(resid_c) <- corr_cells
cm <- cor(resid_c, method="pearson", use="pairwise.complete.obs")
pm <- matrix(NA_real_, nrow=length(corr_cells), ncol=length(corr_cells),
             dimnames=list(corr_cells, corr_cells))
for (i in seq_along(corr_cells)) for (j in seq_along(corr_cells)) {
  pm[i, j] <- suppressWarnings(cor.test(resid_c[, i], resid_c[, j],
                                         method="pearson")$p.value)
}
offdiag <- upper.tri(pm)
qm <- pm
qm[offdiag] <- p.adjust(pm[offdiag], method="BH")
qm[lower.tri(qm)] <- t(qm)[lower.tri(qm)]

c_stats <- expand.grid(Cell1=corr_cells, Cell2=corr_cells, stringsAsFactors=FALSE)
c_stats$rho <- as.vector(cm)
c_stats$p_value <- as.vector(pm)
c_stats$q_value <- as.vector(qm)
c_stats <- c_stats[c_stats$Cell1 != c_stats$Cell2, ]
write.csv(c_stats, op("panel_C_correlation_stats.csv"), row.names=FALSE)
write.csv(cm, op("panel_C_correlation_matrix.csv"))
write.csv(cm_pooled, op("supplement_C_pooled_spearman_matrix.csv"))

pm_pooled <- matrix(NA_real_, nrow=length(corr_cells), ncol=length(corr_cells),
                    dimnames=list(corr_cells, corr_cells))
for (i in seq_along(corr_cells)) for (j in seq_along(corr_cells)) {
  pm_pooled[i, j] <- suppressWarnings(cor.test(
    corr_source[[corr_cells[i]]], corr_source[[corr_cells[j]]],
    method="spearman", exact=FALSE)$p.value)
}
qm_pooled <- pm_pooled
qm_pooled[upper.tri(qm_pooled)] <- p.adjust(pm_pooled[upper.tri(pm_pooled)], method="BH")
qm_pooled[lower.tri(qm_pooled)] <- t(qm_pooled)[lower.tri(qm_pooled)]
pooled_stats <- expand.grid(Cell1=corr_cells, Cell2=corr_cells, stringsAsFactors=FALSE)
pooled_stats$rho <- as.vector(cm_pooled)
pooled_stats$p_value <- as.vector(pm_pooled)
pooled_stats$q_value <- as.vector(qm_pooled)
pooled_stats <- pooled_stats[pooled_stats$Cell1 != pooled_stats$Cell2, ]
write.csv(pooled_stats, op("supplement_C_pooled_spearman_stats.csv"), row.names=FALSE)

pos_col <- "#D84A3A"; neg_col <- "#4C78A8"
col_fun <- circlize::colorRamp2(c(-1, 0, 1), c(neg_col, "white", pos_col))
short_labels <- C2_CELL_SHORT[corr_cells]

## 对称相关矩阵必须让行、列共用同一棵树，否则上下三角将失去镜像对应。
## 这里聚类的是跨样本共同变化模式，不代表细胞发育谱系或因果关系。
make_c_hclust <- function(cmat) {
  d <- 1 - cmat
  d[!is.finite(d)] <- 1
  d[d < 0] <- 0
  diag(d) <- 0
  stats::hclust(stats::as.dist(d), method=CFG$c_cluster_method)
}

c_hc <- make_c_hclust(cm)
write.csv(data.frame(
  order=seq_along(c_hc$order),
  CellType=rownames(cm)[c_hc$order],
  DisplayLabel=unname(CELL_SHORT[rownames(cm)[c_hc$order]])
), op("panel_C_cluster_order.csv"), row.names=FALSE)
ht <- ComplexHeatmap::Heatmap(
  cm, name="Partial Spearman rho", col=col_fun,
  ## Fix the matrix body to a square so each cell has equal width and height.
  width=grid::unit(15.5, "cm"), height=grid::unit(15.5, "cm"),
  cluster_rows=c_hc, cluster_columns=c_hc,
  show_row_dend=FALSE, show_column_dend=FALSE,
  show_row_names=TRUE, row_names_side="left", row_labels=short_labels,
  row_names_max_width=grid::unit(3.0, "cm"),
  show_column_names=TRUE, column_labels=short_labels,
  column_names_rot=55, rect_gp=grid::gpar(type="none"),
  column_title="组别校正后的细胞共同变化",
  column_title_side="top",
  column_title_gp=grid::gpar(fontsize=17, fontface="bold"),
  cell_fun=function(j, i, x, y, w, h, fill) {
    r <- cm[i, j]
    ## i/j是原矩阵索引；三角形位置必须按聚类后的叶序判断。
    plot_i <- match(i, c_hc$order)
    plot_j <- match(j, c_hc$order)
    grid::grid.rect(x=x, y=y, width=w, height=h,
                    gp=grid::gpar(fill="white", col="grey92", lwd=0.25))
    if (plot_i == plot_j) {
      grid::grid.rect(x=x, y=y, width=w, height=h,
                      gp=grid::gpar(fill=pos_col, col="white", lwd=0.25))
    } else if (plot_i < plot_j) {
      ## 上三角：只显示颜色，不显示rho数值。
      grid::grid.rect(x=x, y=y, width=w, height=h,
                      gp=grid::gpar(fill=col_fun(r), col="white", lwd=0.25))
    } else {
      ## 下三角：扇形角度表示|rho|，红/蓝表示正/负方向。
      grid::pushViewport(grid::viewport(x=x, y=y, width=w, height=h,
                                        just=c("center", "center")))
      radius <- 0.37
      grid::grid.circle(x=0.5, y=0.5, r=grid::unit(radius, "npc"),
                        gp=grid::gpar(fill="white", col="grey78", lwd=0.3))
      if (is.finite(r) && abs(r) > 0) {
        ## 均从12点钟起：红色正相关向右顺时针，蓝色负相关向左逆时针。
        theta <- if (r >= 0) {
          seq(pi/2, pi/2 - 2*pi*abs(r), length.out=80)
        } else {
          seq(pi/2, pi/2 + 2*pi*abs(r), length.out=80)
        }
        grid::grid.polygon(x=c(0.5, 0.5 + radius*cos(theta)),
                           y=c(0.5, 0.5 + radius*sin(theta)),
                           default.units="npc",
                           gp=grid::gpar(fill=ifelse(r >= 0, pos_col, neg_col), col=NA))
        grid::grid.circle(x=0.5, y=0.5, r=grid::unit(radius, "npc"),
                          gp=grid::gpar(fill=NA, col="grey78", lwd=0.3))
      }
      grid::popViewport()
    }
  },
  row_names_gp=grid::gpar(fontsize=11.5, fontface="bold"),
  column_names_gp=grid::gpar(fontsize=11.5, fontface="bold"),
  ## 参考文献式窄竖直色条：顶部为正相关、底部为负相关，刻度每0.2显示。
  heatmap_legend_param=list(title="", at=seq(-1, 1, by=0.2),
                            labels=format(seq(-1, 1, by=0.2), trim=TRUE),
                            legend_height=grid::unit(6.2, "cm"),
                            legend_width=grid::unit(0.34, "cm"),
                            border="grey55",
                            labels_gp=grid::gpar(fontsize=11.5, fontface="bold"))
)

png(op("panel_C1_deconv_cell_consistency.png"), width=CFG$c1_width, height=CFG$c1_height,
    units="in", res=CFG$fig_dpi)
ComplexHeatmap::draw(ht, heatmap_legend_side="right",
                     padding=grid::unit(c(1, 1, 1, 1), "mm"))
dev.off()

writeLines(c(
  "组别校正后的细胞共同变化",
  paste0("Included deconvolution samples: ", nrow(corr_source), "."),
  "Each cell type is rank-transformed and clinical Group is regressed out.",
  "The displayed matrix is Pearson correlation of the group-adjusted rank residuals.",
  "This is an internal co-variation analysis, not an external accuracy validation.",
  "相对比例的相关性还可能受到组成约束影响；本分析不代表外部准确性验证。"
), op("panel_C1_interpretation.txt"))
