#!/usr/bin/env Rscript
suppressPackageStartupMessages({
  library(data.table)
  library(ggplot2)
  library(GSVA)
  library(AnnotationDbi)
  library(org.Hs.eg.db)
  library(GO.db)
  library(jsonlite)
})

args <- commandArgs(trailingOnly=TRUE)
arg <- function(key, default=NULL) {
  value <- args[grepl(paste0("^--", key, "="), args)]
  if (!length(value)) return(default)
  sub(paste0("^--", key, "="), "", value[[1]])
}
required <- c("input", "groups", "expression", "output", "cell-cols", "comparison-json")
missing <- required[vapply(required, function(key) is.null(arg(key)), logical(1))]
if (length(missing)) stop("Missing arguments: ", paste(missing, collapse=", "))

manifest <- data.frame(
  Module=c("Adaptive immunity", "Lymphocyte activation", "T-cell immunity",
           "B-cell immunity", "Humoral immunity", "Innate immunity",
           "Myeloid immunity", "Inflammation", "Cytokine signalling", "Complement"),
  ID=c("GO:0002250", "GO:0046649", "GO:0042110", "GO:0042113", "GO:0006959",
       "GO:0045087", "GO:0002274", "GO:0006954", "GO:0019221", "GO:0006956"),
  Label=c("Adaptive immune response", "Lymphocyte activation", "T-cell activation",
          "B-cell activation", "Humoral immune response", "Innate immune response",
          "Myeloid leukocyte activation", "Inflammatory response",
          "Cytokine-mediated signalling", "Complement activation")
)
GO_MIN_GENES <- 10L
N_PERM <- as.integer(arg("permutations", "10000"))
if (is.na(N_PERM) || N_PERM < 99L) stop("permutations must be at least 99")
comparison <- jsonlite::fromJSON(arg("comparison-json"), simplifyVector=TRUE)
if (length(comparison) != 2L || any(!nzchar(comparison)) || comparison[[1]] == comparison[[2]])
  stop("comparison must contain two distinct group names")
cells <- strsplit(arg("cell-cols"), ",", fixed=TRUE)[[1]]
if (!length(cells) || any(!nzchar(cells)) || anyDuplicated(cells)) stop("invalid cell columns")

deconv <- fread(arg("input"), check.names=FALSE, data.table=FALSE,
                colClasses=list(character="sample"))
groups <- fread(arg("groups"), check.names=FALSE, data.table=FALSE,
                colClasses=list(character=c("sample", "group")))
expression <- fread(arg("expression"), check.names=FALSE, data.table=FALSE)
if (!all(c("sample", cells) %in% names(deconv))) stop("deconvolution input is missing selected columns")
if (!all(c("sample", "group") %in% names(groups))) stop("group table requires sample and group columns")
if (ncol(expression) < 2L) stop("expression matrix requires a gene column and sample columns")

deconv$sample <- trimws(as.character(deconv$sample))
groups$sample <- trimws(as.character(groups$sample))
groups$group <- trimws(as.character(groups$group))
if (anyDuplicated(deconv$sample) || anyDuplicated(groups$sample)) stop("sample identifiers must be unique")
if (!all(deconv$sample %in% groups$sample)) stop("deconvolution samples do not all have group metadata")
group_index <- match(deconv$sample, groups$sample)
group <- factor(groups$group[group_index], levels=comparison)
keep <- !is.na(group)
deconv <- deconv[keep, , drop=FALSE]
group <- droplevels(group[keep])
if (nrow(deconv) < 10L || any(table(group) < 2L)) stop("insufficient matched samples for the selected groups")

gene_column <- names(expression)[[1]]
gene <- toupper(trimws(as.character(expression[[gene_column]])))
if (any(!nzchar(gene))) stop("expression matrix contains empty gene identifiers")
samples <- deconv$sample
expression_columns <- paste0("sample_", seq_along(samples))
if (!all(expression_columns %in% names(expression))) stop("expression matrix is missing internal sample columns")
expr <- as.matrix(expression[, expression_columns, drop=FALSE])
suppressWarnings(mode(expr) <- "numeric")
if (any(is.infinite(expr), na.rm=TRUE) || any(expr < 0, na.rm=TRUE))
  stop("expression values must be finite and non-negative")
expr[is.na(expr)] <- 0
rownames(expr) <- gene
expr <- rowsum(expr, group=rownames(expr), reorder=FALSE)
expr <- log2(expr + 1)
colnames(expr) <- samples

annotation <- AnnotationDbi::select(
  org.Hs.eg.db::org.Hs.eg.db,
  keys=manifest$ID,
  keytype="GOALL",
  columns=c("SYMBOL", "ONTOLOGYALL")
)
annotation <- annotation[!is.na(annotation$ONTOLOGYALL) & annotation$ONTOLOGYALL == "BP" &
                         !is.na(annotation$SYMBOL) & nzchar(annotation$SYMBOL), , drop=FALSE]
go_sets <- split(toupper(as.character(annotation$SYMBOL)), as.character(annotation$GOALL))
go_sets <- lapply(go_sets, unique)
coverage <- do.call(rbind, lapply(seq_len(nrow(manifest)), function(index) {
  id <- manifest$ID[[index]]
  genes <- go_sets[[id]]
  if (is.null(genes)) genes <- character()
  retained <- intersect(genes, rownames(expr))
  data.frame(
    ID=id,
    Module=manifest$Module[[index]],
    Label=manifest$Label[[index]],
    OriginalGenes=length(genes),
    RetainedGenes=length(retained),
    Coverage=if (length(genes)) length(retained) / length(genes) else NA_real_,
    Included=length(retained) >= GO_MIN_GENES,
    AnnotationSource=paste0("org.Hs.eg.db ", as.character(packageVersion("org.Hs.eg.db")), "; GOALL"),
    GenesUsed=paste(retained, collapse=";")
  )
}))
write.csv(coverage, file.path(arg("output"), "GO_sample_gene_coverage.csv"), row.names=FALSE, na="")
sets_used <- lapply(go_sets[coverage$ID[coverage$Included]], function(genes) intersect(genes, rownames(expr)))
if (!length(sets_used)) stop("none of the configured GO-BP terms has at least 10 measured genes")

score <- GSVA::gsva(
  GSVA::ssgseaParam(expr, sets_used, normalize=TRUE, minSize=GO_MIN_GENES),
  verbose=FALSE
)
scores_out <- data.frame(Pathway=rownames(score), score, check.names=FALSE)
write.csv(scores_out, file.path(arg("output"), "GO_sample_ssGSEA_scores.csv"), row.names=FALSE)
set.seed(20260813)
stats <- do.call(rbind, lapply(rownames(score), function(pathway) {
  do.call(rbind, lapply(cells, function(cell) {
    x <- as.numeric(score[pathway, ])
    y <- as.numeric(deconv[[cell]])
    valid <- is.finite(x) & is.finite(y) & !is.na(group)
    x <- x[valid]
    y <- y[valid]
    g <- droplevels(group[valid])
    rx <- rank(x, ties.method="average")
    ry <- rank(y, ties.method="average")
    ex <- residuals(lm(rx ~ g))
    ey <- residuals(lm(ry ~ g))
    rho <- suppressWarnings(cor(ex, ey))
    if (!is.finite(rho) || sd(ex) == 0 || sd(ey) == 0) {
      return(data.frame(Pathway=pathway, CellType=cell, n=length(x), rho=NA_real_,
                        p_value=NA_real_, n_permutations=N_PERM))
    }
    within_group <- split(seq_along(ey), g)
    permuted <- replicate(N_PERM, {
      permuted_y <- ey
      for (indices in within_group) permuted_y[indices] <- sample(ey[indices], length(indices), replace=FALSE)
      suppressWarnings(cor(ex, permuted_y))
    })
    p_value <- (1 + sum(abs(permuted) >= abs(rho), na.rm=TRUE)) /
      (1 + sum(is.finite(permuted)))
    data.frame(Pathway=pathway, CellType=cell, n=length(x), rho=rho,
               p_value=p_value, n_permutations=N_PERM)
  }))
}))
stats$q_value <- p.adjust(stats$p_value, method="BH")
stats$raw_significant <- is.finite(stats$p_value) & stats$p_value < 0.05
stats$evidence <- pmin(6, pmax(0.15, -log10(pmax(stats$p_value, 1e-300))))
stats$Module <- manifest$Module[match(stats$Pathway, manifest$ID)]
stats$PathwayLabel <- manifest$Label[match(stats$Pathway, manifest$ID)]
write.csv(stats, file.path(arg("output"), "GO_sample_partial_statistics.csv"), row.names=FALSE, na="")

stats$CellType <- factor(stats$CellType, levels=cells)
stats$PathwayLabel <- factor(stats$PathwayLabel,
  levels=rev(manifest$Label[manifest$ID %in% rownames(score)]))
plot <- ggplot(stats, aes(CellType, PathwayLabel)) +
  geom_tile(fill="grey98", colour="grey88", linewidth=0.3) +
  geom_point(aes(size=evidence, fill=rho, alpha=raw_significant),
             shape=21, colour="grey65", stroke=0.25) +
  geom_point(data=stats[stats$raw_significant, , drop=FALSE],
             aes(size=evidence, fill=rho), shape=21, colour="black", stroke=0.9) +
  scale_fill_gradient2(low="#3E9FC1", mid="white", high="#D84A3A",
                       midpoint=0, limits=c(-1,1), name="组别校正相关系数") +
  scale_alpha_manual(values=c(`TRUE`=1, `FALSE`=0.2), guide="none") +
  scale_size_continuous(name="显著性\n-log10(p)", limits=c(0.15,6), range=c(1,8)) +
  labs(title=paste("GO-BP ssGSEA 与浸润细胞相关", paste(comparison, collapse=" vs ")),
       x="浸润细胞类型", y="GO-BP 通路") +
  theme_minimal(base_size=12) +
  theme(panel.grid=element_blank(), axis.text.x=element_text(angle=45, hjust=1),
        plot.title=element_text(face="bold"), legend.position="right")
ggsave(file.path(arg("output"), "GO_sample_partial.png"), plot,
       width=11.4, height=7.2, units="in", dpi=150, bg="white", limitsize=FALSE)
writeLines(c(
  paste("Comparison:", paste(comparison, collapse=" vs ")),
  "GO-BP sample scores use org.Hs.eg.db GOALL annotations and GSVA ssGSEA on log2(expression + 1).",
  "Sample-level associations rank-transform each measure, regress out group, and correlate residuals.",
  paste("Permutation p-values shuffle deconvolution rank residuals within group; permutations:", N_PERM),
  "BH correction covers all tested GO-BP and cell combinations.",
  "This is exploratory internal biological concordance, not independent validation."
), file.path(arg("output"), "GO_sample_method.txt"))
