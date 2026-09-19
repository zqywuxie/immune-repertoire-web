# Retry transient repository failures without accepting an incomplete runtime.
options(timeout = 600)
required <- c("clusterProfiler", "org.Hs.eg.db", "enrichplot", "DOSE")
for (attempt in seq_len(3)) {
    message(sprintf("Analysis dependency installation attempt %d/3", attempt))
    tryCatch(
        {
            # Binary installation can leave a transitive dependency absent after
            # a failed download. Recompute the complete runtime dependency set.
            catalog <- available.packages(repos = BiocManager::repositories(version = "3.20"))
            dependencies <- unique(unlist(tools::package_dependencies(
                required, db = catalog, which = c("Depends", "Imports", "LinkingTo"),
                recursive = TRUE), use.names = FALSE))
            missing <- setdiff(dependencies, rownames(installed.packages()))
            targets <- unique(c(missing, required))
            BiocManager::install(targets, version = "3.20", ask = FALSE,
                                 update = FALSE, force = TRUE)
        },
        error = function(error) message(conditionMessage(error))
    )
    available <- vapply(required, requireNamespace, logical(1), quietly = TRUE)
    if (all(available)) quit(status = 0)
    message("Unavailable analysis packages: ", paste(required[!available], collapse = ", "))
    if (attempt < 3) Sys.sleep(10 * attempt)
}
stop("Analysis dependency installation failed after three attempts")
