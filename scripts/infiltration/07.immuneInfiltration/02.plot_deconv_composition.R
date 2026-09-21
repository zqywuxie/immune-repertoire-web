#!/usr/bin/env Rscript
## Standalone A-panel: immune-infiltrating cell composition.
## Example:
## Rscript 02.plot_deconv_composition.R --input=deconv.csv --sample-col=sample \
##   --group-col=category --cell-cols=NK_cells,endothelial_cells,...

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
  input=deconv_input, output=file.path(deconv_root, "02.composition"), `sample-col`=immune_config$sample_column %||% "sample",
  `group-col`=immune_config$group_column %||% "category", `group-order`=paste(parse_config_values(attr(metadata, "group_order")), collapse=","),
  `cell-cols`=paste(parse_config_values(immune_config$cell_columns), collapse=","), epsilon="1e-6", dpi="600"))
if (isTRUE(args$help)) {
  print_usage("A-panel arguments: --input --output --sample-col --group-col --group-order --cell-cols --epsilon --dpi")
  quit(save="no", status=0)
}

input <- cli_value(args, "input")
out <- cli_value(args, "output")
sample_col <- cli_value(args, "sample-col", "sample")
group_col <- cli_value(args, "group-col", "category")
group_order <- cli_value(args, "group-order", "")
epsilon <- as.numeric(cli_value(args, "epsilon", "1e-6"))
dpi <- as.numeric(cli_value(args, "dpi", "600"))

df <- read_table(input)
df <- attach_metadata_groups(df, sample_col, group_col, analysis_config, config_path, args$profile %||% "")
if (!sample_col %in% names(df)) stop("Sample column not found: ", sample_col)
cells <- resolve_columns(df, cli_value(args, "cell-cols", ""),
                         exclude=c(sample_col, group_col, "P-value", "Correlation", "RMSE"))
df <- as_numeric_features(df, cells)
df <- group_factor(df, group_col, group_order)
if (anyDuplicated(df[[sample_col]])) stop("Sample IDs must be unique")

## Group first, then descending values across the supplied cell columns.
ord <- do.call(order, c(list(df$.__group__),
                        lapply(df[cells], function(z) -z),
                        list(as.character(df[[sample_col]]))))
df <- df[ord, , drop=FALSE]
df$.__x__ <- seq_len(nrow(df))

tr <- global_shift_close(df, cells, epsilon=epsilon)
closed <- as.data.frame(tr$closed, check.names=FALSE)
names(closed) <- cells
raw_out <- as.data.frame(tr$raw, check.names=FALSE)
names(raw_out) <- paste0("raw_", cells)
trans_out <- as.data.frame(tr$closed, check.names=FALSE)
names(trans_out) <- paste0("fraction_", cells)
export <- cbind(data.frame(
  X=df$.__x__, sample=df[[sample_col]], group=as.character(df$.__group__),
  raw_min=apply(tr$raw, 1, min, na.rm=TRUE),
  global_shift_min=rep(tr$global_min, nrow(df)),
  positive_epsilon=rep(tr$epsilon, nrow(df)),
  shifted_sum=tr$shifted_sum, closure_sum=tr$closure_sum,
  check.names=FALSE), raw_out, trans_out)
dir.create(out, recursive=TRUE, showWarnings=FALSE)
write.csv(export, file.path(out, "panel_A_shift_normalized_matrix.csv"), row.names=FALSE)
write.csv(data.frame(order=seq_len(nrow(df)), sample=df[[sample_col]],
                     group=as.character(df$.__group__)),
          file.path(out, "panel_A_sample_order.csv"), row.names=FALSE)

long <- data.table::melt(data.table::as.data.table(data.frame(X=df$.__x__, closed,
                                                              check.names=FALSE)),
                         id.vars="X", variable.name="CellType", value.name="Fraction")
long$CellType <- factor(long$CellType, levels=cells)
groups <- levels(df$.__group__)
g_n <- table(df$.__group__)
g_end <- cumsum(as.numeric(g_n)); g_start <- c(1, head(g_end, -1) + 1)
g_tab <- data.frame(Group=groups, n=as.numeric(g_n), start=g_start, end=g_end,
                    center=(g_start + g_end)/2,
                    fill=unname(group_palette(groups)), stringsAsFactors=FALSE)
strip_gap <- 0.025; strip_height <- 0.06
g_tab$y_top <- -strip_gap; g_tab$y_bottom <- g_tab$y_top - strip_height
g_tab$y_center <- (g_tab$y_top + g_tab$y_bottom)/2
strip_layers <- lapply(seq_len(nrow(g_tab)), function(i)
  annotate("rect", xmin=g_tab$start[i]-0.5, xmax=g_tab$end[i]+0.5,
           ymin=g_tab$y_bottom[i], ymax=g_tab$y_top[i],
           fill=g_tab$fill[i], colour=NA))

p <- ggplot(long, aes(x=X, y=Fraction, fill=CellType)) +
  geom_col(width=0.94, colour=NA) +
  geom_vline(xintercept=head(g_tab$end, -1)+0.5, linewidth=0.35, colour="grey25") +
  strip_layers +
  geom_text(data=g_tab, aes(x=center, y=y_center,
                            label=paste0(gsub("_", "-", Group), " (n=", n, ")")),
            inherit.aes=FALSE, size=3.0, colour="white", fontface="bold") +
  scale_x_continuous(limits=c(0.5, nrow(df)+0.5), breaks=NULL, expand=c(0, 0)) +
  scale_y_continuous(limits=c(min(g_tab$y_bottom)-0.025, 1.035),
                     labels=scales::label_number(accuracy=0.01), expand=c(0, 0)) +
  scale_fill_manual(values=cell_palette(cells),
                    labels=gsub("_", " ", cells), drop=FALSE) +
  coord_cartesian(clip="off") +
  labs(x=NULL, y="免疫细胞组成（变换后）", fill=NULL) +
  theme_deconv +
  theme(axis.text.x=element_blank(), axis.ticks.x=element_blank(),
        legend.position="right", legend.key.height=grid::unit(0.34, "cm"))

save_plot(p, file.path(out, "panel_A_shift_normalized_stacked.png"),
          width=11.69, height=8.27, dpi=dpi)
writeLines(c(
  "Global minimum shift + positive epsilon + row-wise closure.",
  paste0("Input: ", normalizePath(input, winslash="/", mustWork=FALSE)),
  paste0("Sample column: ", sample_col, "; group column: ", group_col),
  paste0("Cell columns (", length(cells), "): ", paste(cells, collapse=", ")),
  paste0("Global minimum: ", format(tr$global_min, digits=12),
         "; epsilon: ", format(tr$epsilon, scientific=TRUE)),
  "The transformed values are for display; raw values are retained in the CSV export."
), file.path(out, "panel_A_interpretation.txt"))
message("A panel complete: ", normalizePath(out, winslash="/"))
