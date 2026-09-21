## Shared JSON paths and explicit sample/group metadata for R entrypoints.

`%||%` <- function(x, y) if (is.null(x) || length(x) == 0L || isTRUE(anyNA(x))) y else x

script_dir_from_args <- function() {
  args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", args, value = TRUE)
  if (length(file_arg)) return(dirname(normalizePath(sub("^--file=", "", file_arg[1]))))
  normalizePath(getwd(), mustWork = FALSE)
}

load_analysis_config <- function(config_path = "") {
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    stop("The R configuration loader requires the 'jsonlite' package.")
  }
  if (is.null(config_path) || !nzchar(config_path)) {
    script_dir <- script_dir_from_args()
    candidates <- character()
    current_dir <- script_dir
    for (i in 0:4) {
      candidates <- c(candidates, normalizePath(file.path(current_dir, "0.config", "analysis.json"), mustWork = FALSE))
      current_dir <- dirname(current_dir)
    }
    existing <- candidates[file.exists(candidates)]
    if (!length(existing)) return(list(config = list(), path = ""))
    config_path <- existing[[1]]
  }
  config_path <- path.expand(config_path)
  if (!file.exists(config_path)) stop("Configuration file not found: ", config_path)
  config <- jsonlite::read_json(config_path, simplifyVector = FALSE)
  if (!is.null(config$datasets)) {
    stop("Multi-Datapoint project: first run 0.config/03.run_datasets.py, then pass --config results/0.config/resolved_configs/<dataset_id>.json")
  }
  paths <- config$paths %||% list()
  paths <- modifyList(paths, config$inputs %||% list())
  paths <- modifyList(paths, config$references %||% list())
  output_root <- config$outputs$root %||% paths$output_root %||% "../../results"
  generated <- list(
    output_root = output_root,
    pep_input = file.path(output_root, "0.config", "01.prepare_pep", "pep_data"),
    pep_datapoint_input = file.path(output_root, "0.config", "01.prepare_pep", "datapoint.csv"),
    topclone_input = file.path(output_root, "03.UCDR3", "2.topclone", "0.CDR3_trace", "topclone.csv"),
    pep_shared_output = file.path(output_root, "03.UCDR3", "1.Pep", "2.Pep_shared", "Pep_shared"),
    pep_category_input = file.path(output_root, "03.UCDR3", "1.Pep", "3.add_cate_shared"),
    pep_category_output = file.path(output_root, "03.UCDR3", "1.Pep", "3.add_cate_shared"),
    pep_usage_output = file.path(output_root, "03.UCDR3", "1.Pep", "2.Pep_shared", "usage"),
    pep_arranged_output = file.path(output_root, "03.UCDR3", "1.Pep", "6.Pep_statistication", "CDR3_arranged"),
    pep_usage_cate_output = file.path(output_root, "03.UCDR3", "1.Pep", "4.add_cate_usage"),
    pep_heatmap_output = file.path(output_root, "03.UCDR3", "1.Pep", "5.Heat_map_Thread"),
    pep_proportion_output = file.path(output_root, "03.UCDR3", "1.Pep", "6.Pep_statistication", "CDR3_proportion"),
    pep_alignment_output = file.path(output_root, "03.UCDR3", "1.Pep", "10.Alignment_shared"),
    db_ratio_input = file.path(output_root, "04.DB", "specify_ratio"),
    gene_usage_cate_input = file.path(output_root, "03.UCDR3", "1.Pep", "4.add_cate_usage"),
    gene_vj_output = file.path(output_root, "0.config", "02.concaten"),
    gene_vj_input = file.path(output_root, "0.config", "02.concaten", "df_1Vusage_all.csv"),
    gene_vj_matrix_input = file.path(output_root, "0.config", "02.concaten", "df_1VJusage_all.csv"),
    transcriptome_results = file.path(output_root, "06.Transcriptome")
  )
  config$paths <- modifyList(paths, generated)
  list(config = config, path = normalizePath(config_path))
}

config_value <- function(config, ..., default = NULL) {
  keys <- list(...)
  value <- config
  for (key in keys) {
    if (!is.list(value) || is.null(value[[key]])) return(default)
    value <- value[[key]]
  }
  value
}

resolve_config_path <- function(value, config_path = "") {
  if (is.null(value) || !nzchar(as.character(value))) return("")
  value <- path.expand(as.character(value))
  if (grepl("^[A-Za-z]:[/\\\\]", value) || startsWith(value, "/")) return(normalizePath(value, mustWork = FALSE))
  base <- if (nzchar(config_path)) dirname(config_path) else script_dir_from_args()
  normalizePath(file.path(base, value), mustWork = FALSE)
}

require_config_path <- function(paths, key, config_path = "") {
  value <- paths[[key]]
  if (is.null(value) || !nzchar(as.character(value))) {
    stop("Missing configured path: paths.", key)
  }
  resolve_config_path(value, config_path)
}

parse_config_values <- function(value) {
  if (is.null(value) || length(value) == 0L) return(character())
  if (length(value) > 1L) return(trimws(as.character(value)))
  values <- trimws(unlist(strsplit(as.character(value), ",", fixed = TRUE)))
  values[nzchar(values)]
}

get_config_profile <- function(config, profile = "") {
  chosen <- if (nzchar(profile)) profile else config$default_profile %||% "default"
  profiles <- config$datapoint_profiles %||% list()
  selected <- if (length(profiles)) profiles[[chosen]] %||% list() else config$datapoint %||% list()
  selected$name <- chosen
  selected
}

read_group_metadata <- function(config, config_path, profile = "") {
  selected <- get_config_profile(config, profile)
  path <- require_config_path(config$paths, selected$input_path_key %||% "datapoint_input", config_path)
  raw <- read.csv(path, check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character")
  sc <- selected$sample_column %||% "sample"
  gc <- selected$group_column %||% "group"
  if (!all(c(sc, gc) %in% names(raw))) stop("Datapoint requires columns: ", sc, ", ", gc)
  metadata <- data.frame(sample = trimws(as.character(raw[[sc]])),
                         group = trimws(as.character(raw[[gc]])))
  if (anyNA(metadata) || any(!nzchar(metadata$sample)) || any(!nzchar(metadata$group)))
    stop("Datapoint sample/group must not be missing.")
  if (anyDuplicated(metadata$sample)) stop("Datapoint sample IDs must be unique.")
  excluded <- parse_config_values(selected$excluded_groups)
  excluded_samples <- metadata$sample[metadata$group %in% excluded]
  metadata <- metadata[!metadata$group %in% excluded, , drop = FALSE]
  attr(metadata, "excluded_samples") <- excluded_samples
  observed <- unique(metadata$group)
  order <- parse_config_values(selected$group_order)
  attr(metadata, "group_order") <- c(intersect(order, observed), setdiff(observed, order))
  metadata
}

metadata_groups <- function(samples, metadata, prefix = "") {
  ids <- as.character(samples)
  if (nzchar(prefix)) ids <- ifelse(startsWith(ids, prefix), substring(ids, nchar(prefix) + 1L), ids)
  index <- match(ids, metadata$sample)
  if (anyNA(index)) stop("Samples missing from selected datapoint: ", paste(head(ids[is.na(index)], 8), collapse = ", "),
                        ". Configure sample IDs/prefix explicitly; groups are not inferred from names.")
  metadata$group[index]
}

resolve_group_comparisons <- function(comparisons, groups) {
  groups <- unique(as.character(groups))
  if (length(groups) < 2L) stop("At least two observed groups are required.")
  if (!length(comparisons)) return(combn(groups, 2L, simplify = FALSE))
  pairs <- lapply(comparisons, function(x) trimws(as.character(unlist(x))))
  if (any(vapply(pairs, function(x) length(x) != 2L || length(unique(x)) != 2L ||
                 any(!x %in% groups), logical(1)))) stop("Invalid comparison: use two distinct observed groups.")
  pairs
}
