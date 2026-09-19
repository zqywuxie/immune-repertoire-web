"""Small cached runtime checks for optional scientific modules."""
from functools import lru_cache
import shutil
import subprocess

@lru_cache(maxsize=1)
def enrichment_runtime_ready():
    executable=shutil.which('Rscript')
    if not executable:
        return False
    script="p <- c('clusterProfiler','org.Hs.eg.db','enrichplot','DOSE'); quit(status=if(all(vapply(p,requireNamespace,logical(1),quietly=TRUE))) 0 else 1)"
    try:
        options = {'creationflags': getattr(subprocess,'CREATE_NO_WINDOW',0)}
        return subprocess.run([executable,'-e',script],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=15,**options).returncode==0
    except (OSError,subprocess.TimeoutExpired):
        return False
