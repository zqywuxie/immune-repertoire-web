#!/usr/bin/env Rscript
## Standalone B-panel: group-wise deconvolution score distributions.

file_arg <- commandArgs()[grepl("^--file=", commandArgs())]
script_dir <- if (length(file_arg)) dirname(normalizePath(sub("^--file=", "", file_arg[1]))) else "."
source(file.path(script_dir, "plot_deconv_helpers.R"))
source(file.path(script_dir, "..", "common", "configuration", "config.R"), encoding="UTF-8")
raw_args <- commandArgs(trailingOnly=TRUE)
config_hit <- raw_args[grepl("^--config(=|$)", raw_args)]
config_arg <- if (length(config_hit) && grepl("=", config_hit[1])) sub("^--config=", "", config_hit[1]) else ""
config_bundle <- load_analysis_config(config_arg)
analysis_config <- config_bundle$config
config_path <- config_bundle$path
analysis_paths <- analysis_config$paths %||% list()
immune_config <- analysis_config$immune_infiltration %||% list()
selected_profile <- get_config_profile(analysis_config, parse_cli()$profile %||% "")
metadata <- read_group_metadata(analysis_config, config_path, parse_cli()$profile %||% "")
deconv_input <- if (!is.null(analysis_paths$deconvolution)) resolve_config_path(analysis_paths$deconvolution, config_path) else ""
deconv_root <- if (!is.null(analysis_paths$output_root)) file.path(resolve_config_path(analysis_paths$output_root, config_path), "07.immuneInfiltration", "01.deconv_figure") else file.path(script_dir, "..", "..", "results", "07.immuneInfiltration", "01.deconv_figure")

args <- parse_cli(list(
  input=deconv_input, output=file.path(deconv_root, "03.group_comparison"), `sample-col`=immune_config$sample_column %||% "sample",
  `group-col`=immune_config$group_column %||% "category", `group-order`=paste(parse_config_values(attr(metadata, "group_order")), collapse=","),
  `cell-cols`=paste(parse_config_values(immune_config$cell_columns), collapse=","), `cell-order`="", `split-cell`="auto", dpi="600"))
if (isTRUE(args$help)) {
  print_usage("B-panel arguments: --input --output --sample-col --group-col --group-order --cell-cols --cell-order --split-cell --dpi")
  quit(save="no", status=0)
}

input <- cli_value(args, "input")
out <- cli_value(args, "output")
sample_col <- cli_value(args, "sample-col", "sample")
group_col <- cli_value(args, "group-col", "category")
group_order <- cli_value(args, "group-order", "")
dpi <- as.numeric(cli_value(args, "dpi", "600"))
df <- read_table(input)
df <- attach_metadata_groups(df, sample_col, group_col, analysis_config, config_path, args$profile %||% "")
if (!sample_col %in% names(df)) stop("Sample column not found: ", sample_col)
cells <- resolve_columns(df, cli_value(args, "cell-cols", ""),
                         exclude=c(sample_col, group_col, "P-value", "Correlation", "RMSE"))
df <- as_numeric_features(df, cells)
df <- group_factor(df, group_col, group_order)
requested_order <- comma_cols(cli_value(args, "cell-order", ""))
if (length(requested_order)) {
  if (!all(requested_order %in% cells)) stop("--cell-order contains unknown cell columns")
  cells <- c(requested_order, setdiff(cells, requested_order))
}
groups <- levels(df$.__group__)
dir.create(out, recursive=TRUE, showWarnings=FALSE)

long <- data.table::melt(data.table::as.data.table(data.frame(sample=df[[sample_col]],
                                    Group=df$.__group__, df[cells], check.names=FALSE)),
                         id.vars=c("sample", "Group"),
                         variable.name="CellType", value.name="Score")
long$CellType <- factor(long$CellType, levels=cells)
long$Group <- factor(long$Group, levels=groups)

## Explicit comparisons, or all pairs of observed groups.
pair_groups <- resolve_group_comparisons(immune_config$comparisons, groups)
pair_stats <- do.call(rbind, lapply(cells, function(ct) {
  do.call(rbind, lapply(pair_groups, function(pair) {
    z <- long[as.character(long$CellType) == ct & as.character(long$Group) %in% pair, ]
    p <- tryCatch({
      if (sum(as.character(z$Group) == pair[1]) < 2 ||
          sum(as.character(z$Group) == pair[2]) < 2) NA_real_
      else wilcox.test(Score ~ Group, data=z, exact=FALSE)$p.value
    }, error=function(e) NA_real_)
    data.frame(CellType=ct, Group1=pair[1], Group2=pair[2],
               Comparison=paste(pair, collapse=" vs "), p_value=p,
               display=!is.na(p) & p < 0.05,
               label=ifelse(!is.na(p) & p < 0.05,
                            ifelse(p <= 0.001, "***", ifelse(p <= 0.01, "**", "*")), NA),
               stringsAsFactors=FALSE)
  }))
})); rownames(pair_stats) <- NULL
pair_stats$q_value <- p.adjust(pair_stats$p_value, method="BH")
write.csv(pair_stats, file.path(out, "panel_B_pairwise_stats.csv"), row.names=FALSE)

make_brackets <- function(stats, data, cells_local) {
  s <- stats[stats$display & stats$CellType %in% cells_local, , drop=FALSE]
  if (!nrow(s)) {
    for (column in c("x_center", "x_start", "x_end", "level", "y", "y_tip"))
      s[[column]] <- numeric()
    return(s)
  }
  score <- data$Score[is.finite(data$Score)]
  span <- diff(range(score)); if (!is.finite(span) || span <= 0) span <- 0.05
  y_top <- max(score, na.rm=TRUE)
  gap <- max(span * 0.065, 0.012)
  s$x_center <- match(s$CellType, cells_local)
  s$x_start <- s$x_center + 0.78 * ((match(s$Group1, groups) - 0.5) / length(groups) - 0.5)
  s$x_end <- s$x_center + 0.78 * ((match(s$Group2, groups) - 0.5) / length(groups) - 0.5)
  s$level <- match(s$Comparison, vapply(pair_groups, paste, character(1), collapse=" vs "))
  s$y <- y_top + gap * (s$level + 0.20)
  s$y_tip <- s$y - gap * 0.55
  s
}

make_panel <- function(data, stats, cells_local, title, y_label=TRUE) {
  d <- data[as.character(data$CellType) %in% cells_local, , drop=FALSE]
  d$CellType <- factor(as.character(d$CellType), levels=cells_local)
  br <- make_brackets(stats, d, cells_local)
  score <- d$Score[is.finite(d$Score)]
  span <- diff(range(score)); if (!is.finite(span) || span <= 0) span <- 0.05
  y0 <- min(score, na.rm=TRUE) - span * 0.04
  y1 <- max(c(score, if (nrow(br)) br$y else -Inf), na.rm=TRUE) + max(span*0.05, 0.008)
  p <- ggplot(d, aes(x=CellType, y=Score, fill=Group)) +
    geom_boxplot(position=position_dodge(width=0.78), width=0.68,
                 outlier.shape=NA, linewidth=0.32, alpha=0.80) +
    geom_jitter(aes(colour=Group), position=position_jitterdodge(
      jitter.width=0.12, dodge.width=0.78), size=0.45, alpha=0.45) +
    geom_segment(data=br, aes(x=x_start, xend=x_end, y=y, yend=y),
                 inherit.aes=FALSE, linewidth=0.5, colour="black") +
    geom_segment(data=br, aes(x=x_start, xend=x_start, y=y_tip, yend=y),
                 inherit.aes=FALSE, linewidth=0.5, colour="black") +
    geom_segment(data=br, aes(x=x_end, xend=x_end, y=y_tip, yend=y),
                 inherit.aes=FALSE, linewidth=0.5, colour="black") +
    geom_text(data=br, aes(x=(x_start+x_end)/2, y=y, label=label),
              inherit.aes=FALSE, vjust=-0.45, size=3.0,
              family="sans", fontface="bold") +
    scale_x_discrete(limits=cells_local, labels=gsub("_", " ", cells_local), drop=FALSE) +
    scale_fill_manual(values=group_palette(groups), breaks=groups,
                      labels=group_labels(groups)) +
    scale_colour_manual(values=group_palette(groups), breaks=groups,
                        labels=group_labels(groups)) +
    scale_y_continuous(expand=c(0, 0)) +
    coord_cartesian(ylim=c(y0, y1), clip="off") +
    labs(title=title, x=NULL, y=if (y_label) "免疫浸润原始分数" else NULL,
         fill=NULL, colour=NULL) + theme_deconv +
    theme(axis.text.x=element_text(angle=55, hjust=1, vjust=1,
                                   size=11.5, face="bold"),
          axis.title.y=element_text(size=14, face="bold"),
          plot.title=element_text(size=15, face="bold", hjust=0.5),
          legend.position="top", legend.text=element_text(size=11.5, face="bold"))
  p
}

## Complete common-scale summary.
br_all <- make_brackets(pair_stats, long, cells)
p_all <- make_panel(long, pair_stats, cells, NULL, TRUE)
save_plot(p_all, file.path(out, "panel_B_boxplot_summary.png"),
          width=11.69, height=8.27, dpi=dpi)

## Optional split-scale summary. Auto mode isolates the highest-median cell only
## when it is clearly separated from the runner-up; raw values are unchanged.
split_arg <- cli_value(args, "split-cell", "auto")
split_cell <- if (identical(split_arg, "auto")) {
  med <- tapply(long$Score, long$CellType, median, na.rm=TRUE)
  so <- sort(med, decreasing=TRUE)
  if (length(so) >= 2 && is.finite(so[1]) && so[1] > 1.5 * max(so[2], .Machine$double.eps)) names(so)[1] else ""
} else if (split_arg %in% cells) split_arg else ""
if (nzchar(split_cell)) {
  low_cells <- setdiff(cells, split_cell)
  p_low <- make_panel(long, pair_stats, low_cells, "Other cell types", TRUE)
  p_high <- make_panel(long, pair_stats, split_cell, paste0(split_cell, " (zoom)"), FALSE)
  p_split <- p_low + p_high + patchwork::plot_layout(widths=c(5, 1.9), guides="collect") &
    theme(legend.position="top")
  save_plot(p_split, file.path(out, "panel_B_boxplot_summary_split_scale.png"),
            width=11.69, height=8.27, dpi=dpi)
}

writeLines(c(
  paste0("Input: ", normalizePath(input, winslash="/", mustWork=FALSE)),
  paste0("Sample column: ", sample_col, "; group column: ", group_col),
  paste0("Cell columns (", length(cells), "): ", paste(cells, collapse=", ")),
  "Boxplots use raw deconvolution scores; stars encode unadjusted Wilcoxon P values.",
  "BH-FDR is retained in panel_B_pairwise_stats.csv.",
  if (nzchar(split_cell)) paste0("Split-scale panel isolates: ", split_cell) else "No split-scale panel was triggered."
), file.path(out, "panel_B_interpretation.txt"))
message("B panel complete: ", normalizePath(out, winslash="/"))
