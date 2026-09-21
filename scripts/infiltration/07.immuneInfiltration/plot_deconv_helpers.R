## Shared helpers for the standalone deconv A-C plotting scripts.
## All inputs are supplied through --key=value command-line arguments.

suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(patchwork)
})

parse_cli <- function(defaults=list()) {
  a <- commandArgs(trailingOnly=TRUE)
  out <- defaults
  i <- 1L
  while (i <= length(a)) {
    token <- a[[i]]
    if (grepl("^--[^=]+=", token)) {
      kv <- strsplit(sub("^--", "", token), "=", fixed=TRUE)[[1]]
      key <- kv[[1]]; value <- paste(kv[-1], collapse="=")
      out[[key]] <- value
    } else if (grepl("^--", token) && i < length(a) && !grepl("^--", a[[i+1]])) {
      out[[sub("^--", "", token)]] <- a[[i+1]]
      i <- i + 1L
    } else if (grepl("^--", token)) {
      out[[sub("^--", "", token)]] <- TRUE
    }
    i <- i + 1L
  }
  out
}

cli_value <- function(args, key, default=NULL) {
  if (!is.null(args[[key]])) as.character(args[[key]]) else default
}

comma_cols <- function(x) {
  if (is.null(x) || !nzchar(x)) character() else trimws(strsplit(x, ",", fixed=TRUE)[[1]])
}

read_table <- function(path) {
  if (is.null(path) || !nzchar(path) || !file.exists(path))
    stop("Input file not found: ", path)
  as.data.frame(data.table::fread(path, check.names=FALSE, keepLeadingZeros=TRUE), check.names=FALSE)
}

resolve_columns <- function(df, requested, exclude=character()) {
  cols <- comma_cols(requested)
  if (length(cols)) {
    missing <- setdiff(cols, names(df))
    if (length(missing)) stop("Requested columns not found: ", paste(missing, collapse=", "))
    return(cols)
  }
  candidate <- setdiff(names(df), exclude)
  numeric <- candidate[vapply(df[candidate], function(z) {
    zz <- suppressWarnings(as.numeric(as.character(z)))
    sum(is.finite(zz)) >= max(2, floor(0.8 * length(zz)))
  }, logical(1))]
  if (!length(numeric)) stop("No numeric feature columns detected; pass --cell-cols or --subclass-cols")
  numeric
}

as_numeric_features <- function(df, cols) {
  for (nm in cols) {
    z <- suppressWarnings(as.numeric(as.character(df[[nm]])))
    if (sum(is.finite(z)) < 2) stop("Feature column is not numeric: ", nm)
    df[[nm]] <- z
    df[[nm]][is.na(df[[nm]])] <- 0
  }
  df
}

group_factor <- function(df, group_col, group_order=NULL) {
  if (!group_col %in% names(df)) stop("Group column not found: ", group_col)
  g <- as.character(df[[group_col]])
  if (is.null(group_order) || !nzchar(group_order)) group_order <- unique(g)
  else group_order <- comma_cols(group_order)
  df$.__group__ <- droplevels(factor(g, levels=group_order))
  if (any(is.na(df$.__group__))) stop("Some samples have groups outside --group-order")
  df
}

save_plot <- function(p, png_path, pdf_path = NULL, width=11.69, height=8.27, dpi=600) {
  png_path <- file.path(dirname(png_path), "figure", basename(png_path))
  dir.create(dirname(png_path), recursive=TRUE, showWarnings=FALSE)
  ggsave(bg = "white", png_path, p, width=width, height=height, units="in", dpi=dpi, limitsize=FALSE)
}

theme_deconv <- theme_classic(base_size=13, base_family="sans") +
  theme(axis.line=element_line(linewidth=0.45, colour="black"),
        axis.ticks=element_line(linewidth=0.45, colour="black"),
        panel.grid=element_blank(),
        axis.title=element_text(size=15, face="bold"),
        axis.text=element_text(size=11.5, face="bold", colour="black"),
        legend.title=element_text(size=12, face="bold"),
        legend.text=element_text(size=11.5, face="bold"),
        plot.title=element_text(size=16, face="bold", hjust=0.5),
        plot.margin=margin(7, 7, 14, 7))

group_labels <- function(levels) {
  levels
}

attach_metadata_groups <- function(df, sample_col, group_col, config, config_path, profile = "") {
  metadata <- read_group_metadata(config, config_path, profile)
  if (!sample_col %in% names(df)) {
    if ("Mixture" %in% names(df)) names(df)[names(df) == "Mixture"] <- sample_col
    else stop("Sample column not found: ", sample_col)
  }
  prefix <- config$immune_infiltration$sample_prefix %||% ""
  ids <- as.character(df[[sample_col]])
  if (nzchar(prefix)) ids <- ifelse(startsWith(ids, prefix), substring(ids, nchar(prefix) + 1L), ids)
  keep <- !ids %in% (attr(metadata, "excluded_samples") %||% character())
  df <- df[keep, , drop = FALSE]
  df[[group_col]] <- metadata_groups(ids[keep], metadata)
  df
}

group_palette <- function(levels) {
  base <- c("#4C78A8", "#D98C45", "#59A14F", "#9C755F", "#B07AA1", "#8D9CC4")
  setNames(rep(base, length.out=length(levels)), levels)
}

cell_palette <- function(cells) {
  ## Keep standalone A exactly aligned with the canonical ABC palette.
  base <- c("#4C78A8", "#9C755F", "#BAB0AC", "#E15759", "#F28E2B",
            "#59A14F", "#8D9CC4", "#EDC948", "#B07AA1", "#FF9DA7",
            "#AF7AA1", "#1F77B4", "#D62728", "#2CA02C")
  setNames(rep(base, length.out=length(cells)), cells)
}

global_shift_close <- function(df, cols, epsilon=1e-6) {
  x <- as.matrix(df[, cols, drop=FALSE]); storage.mode(x) <- "numeric"
  finite <- x[is.finite(x)]
  if (!length(finite)) stop("No finite values available for A-panel transformation")
  global_min <- min(finite)
  shifted <- x - global_min + epsilon
  shifted[!is.finite(shifted) | shifted <= 0] <- epsilon
  sums <- rowSums(shifted)
  closed <- shifted / sums
  colnames(closed) <- cols
  list(raw=x, shifted=shifted, closed=closed, global_min=global_min,
       epsilon=epsilon, shifted_sum=sums, closure_sum=rowSums(closed))
}

rank_residual_partial <- function(df, cells, group) {
  residual <- sapply(cells, function(ct) {
    rv <- rank(df[[ct]], ties.method="average", na.last="keep")
    residuals(lm(rv ~ group, na.action=na.exclude))
  })
  colnames(residual) <- cells
  cm <- cor(residual, method="pearson", use="pairwise.complete.obs")
  pm <- matrix(NA_real_, nrow=length(cells), ncol=length(cells),
               dimnames=list(cells, cells))
  for (i in seq_along(cells)) for (j in seq_along(cells)) {
    ok <- is.finite(residual[, i]) & is.finite(residual[, j])
    if (sum(ok) >= 4 && length(unique(residual[ok, i])) > 1 &&
        length(unique(residual[ok, j])) > 1)
      pm[i, j] <- suppressWarnings(cor.test(residual[ok, i], residual[ok, j],
                                             method="pearson")$p.value)
  }
  qm <- pm
  upper <- upper.tri(pm)
  qm[upper] <- p.adjust(pm[upper], method="BH")
  qm[lower.tri(qm)] <- t(qm)[lower.tri(qm)]
  list(residual=residual, rho=cm, p=pm, q=qm)
}

cluster_order <- function(cm, method="ward.D2") {
  d <- 1 - cm; d[!is.finite(d)] <- 1; d[d < 0] <- 0; diag(d) <- 0
  stats::hclust(stats::as.dist(d), method=method)$order
}

print_usage <- function(text) {
  cat(text, "\n", file=stderr())
  invisible(NULL)
}
