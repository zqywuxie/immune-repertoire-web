# Retry transient repository failures without accepting an incomplete runtime.
# Bioconductor redirects package downloads to mirrors. In this build environment
# R's libcurl intermittently fails during TLS redirects; external curl follows
# redirects and retries transient network errors reliably.
options(
    timeout = 600,
    download.file.method = "curl",
    download.file.extra = paste(
        "--location --retry 5 --retry-all-errors --retry-delay 2",
        "--connect-timeout 30 --max-time 600"
    )
)
required <- c("clusterProfiler", "org.Hs.eg.db", "enrichplot", "DOSE", "ComplexHeatmap", "circlize", "GSVA", "limma")
install_ncpus <- suppressWarnings(as.integer(Sys.getenv("R_INSTALL_NCPUS", "2")))
if (is.na(install_ncpus) || install_ncpus < 1L) {
    stop("R_INSTALL_NCPUS must be a positive integer")
}
install_ncpus <- min(install_ncpus, 8L)
for (attempt in seq_len(3)) {
    available <- vapply(required, requireNamespace, logical(1), quietly = TRUE)
    if (all(available)) quit(status = 0)
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
            targets <- unique(c(missing, required[!available]))
            BiocManager::install(targets, version = "3.20", ask = FALSE,
                                 update = FALSE, force = TRUE, Ncpus = install_ncpus)
        },
        error = function(error) message(conditionMessage(error))
    )
    available <- vapply(required, requireNamespace, logical(1), quietly = TRUE)
    if (all(available)) quit(status = 0)
    message("Unavailable analysis packages: ", paste(required[!available], collapse = ", "))
    if (attempt < 3) Sys.sleep(10 * attempt)
}
stop("Analysis dependency installation failed after three attempts")
