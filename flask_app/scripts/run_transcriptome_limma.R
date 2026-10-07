args <- commandArgs(trailingOnly = TRUE)
if (length(args) != 6) stop("Expected: expression.csv groups.csv group1 group2 output.csv quality.csv")

if (!requireNamespace("limma", quietly = TRUE)) {
  stop("Missing R package limma. Install with BiocManager::install('limma').")
}

expression_path <- args[[1]]
groups_path <- args[[2]]
group1 <- args[[3]]
group2 <- args[[4]]
output_path <- args[[5]]
quality_path <- args[[6]]

expression <- read.csv(expression_path, check.names = FALSE, stringsAsFactors = FALSE)
groups <- read.csv(groups_path, check.names = FALSE, stringsAsFactors = FALSE, colClasses = "character")
if (!all(c("sample", "group") %in% names(groups))) stop("Group table requires sample and group columns")
if (!"gene_symbol" %in% names(expression)) stop("Expression matrix requires a gene_symbol column")
if (anyDuplicated(expression$gene_symbol)) stop("Expression matrix contains duplicated gene symbols")
if (anyDuplicated(groups$sample)) stop("Group table contains duplicated sample identifiers")

sample_columns <- setdiff(names(expression), "gene_symbol")
if (!setequal(sample_columns, groups$sample)) stop("Sample columns do not match group metadata")
expression <- expression[, c("gene_symbol", groups$sample), drop = FALSE]
expr_matrix <- as.matrix(expression[, -1, drop = FALSE])
storage.mode(expr_matrix) <- "numeric"
if (any(!is.finite(expr_matrix))) stop("Expression matrix contains non-finite values")
if (any(expr_matrix < 0)) stop("TPM expression matrix contains negative values")
rownames(expr_matrix) <- expression$gene_symbol
expr_matrix <- expr_matrix[rowSums(expr_matrix) > 0, , drop = FALSE]
if (nrow(expr_matrix) == 0) stop("Expression matrix has no non-zero genes")

# Match 06.Transcriptome/01.DEG_analysis.R: TPM defaults, log2(TPM + 1),
# quantile normalization across all samples, array-quality weights, robust eBayes.
expr_matrix <- log2(expr_matrix + 1)
expr_matrix <- limma::normalizeBetweenArrays(expr_matrix, method = "quantile")
selected <- groups$group %in% c(group1, group2)
sub_groups <- groups$group[selected]
if (sum(sub_groups == group1) < 2 || sum(sub_groups == group2) < 2) {
  stop("Each comparison group requires at least two samples")
}
sub_matrix <- expr_matrix[, groups$sample[selected], drop = FALSE]
design_groups <- factor(sub_groups, levels = c(group2, group1))
design <- stats::model.matrix(~ design_groups)
weights <- tryCatch(
  limma::arrayWeights(sub_matrix, design = design),
  error = function(error) {
    warning("arrayWeights failed; using equal sample weights: ", conditionMessage(error))
    rep(1, ncol(sub_matrix))
  }
)
observation_weights <- matrix(weights, nrow = nrow(sub_matrix), ncol = ncol(sub_matrix), byrow = TRUE)
fit <- limma::lmFit(sub_matrix, design, weights = observation_weights)
fit <- limma::eBayes(fit, robust = TRUE)
result <- limma::topTable(fit, coef = 2, number = Inf, sort.by = "P")
result$gene_symbol <- rownames(result)
result <- result[, c("gene_symbol", "logFC", "AveExpr", "t", "P.Value", "adj.P.Val", "B")]
utils::write.csv(result, output_path, row.names = FALSE)
utils::write.csv(
  data.frame(sample = groups$sample[selected], group = sub_groups, sample_weight = as.numeric(weights)),
  quality_path,
  row.names = FALSE
)
