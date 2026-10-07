"""Capture the worker environment actually used to execute a task."""
import hashlib
import platform
import subprocess
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


PYTHON_PACKAGES = (
    'numpy', 'pandas', 'scipy', 'scikit-learn', 'umap-learn', 'matplotlib',
    'sonnia', 'tensorflow', 'rq', 'xgboost', 'statsmodels',
    'scikit-posthocs', 'xlrd', 'openpyxl', 'biopython',
)
MAX_REFERENCE_HASH_BYTES = 128 * 1024 * 1024


@lru_cache(maxsize=32)
def _reference_sha256(path: str, size: int, mtime_ns: int, ctime_ns: int, device: int, inode: int) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def reference_file_provenance(path):
    """Fingerprint one known reference file without walking its directory."""
    source = Path(path)
    try:
        if not source.is_file():
            return {'available': False, 'fingerprint_status': 'missing_or_not_a_file'}
        resolved = source.resolve()
        stat = resolved.stat()
    except OSError as error:
        return {
            'available': False,
            'fingerprint_status': type(error).__name__,
        }
    details = {
        'available': True,
        'path': str(resolved),
        'size_bytes': stat.st_size,
        'modified_ns': stat.st_mtime_ns,
    }
    if stat.st_size > MAX_REFERENCE_HASH_BYTES:
        details['fingerprint_status'] = 'size_limit_exceeded'
        return details
    try:
        details['sha256'] = _reference_sha256(
            str(resolved), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns,
            stat.st_dev, stat.st_ino,
        )
        details['fingerprint_status'] = 'sha256'
    except OSError as error:
        details['fingerprint_status'] = type(error).__name__
    return details


def _r_runtime_provenance():
    script = r'''packages <- c("clusterProfiler", "org.Hs.eg.db", "enrichplot", "DOSE",
  "ComplexHeatmap", "circlize", "GSVA", "AnnotationDbi", "GO.db", "limma",
  "data.table", "ggplot2", "patchwork", "jsonlite")
writeLines(paste("R", as.character(getRversion()), sep="|"))
if (requireNamespace("BiocManager", quietly=TRUE))
  writeLines(paste("BIOC", as.character(BiocManager::version()), sep="|"))
for (name in packages) if (length(find.package(name, quiet=TRUE)))
  writeLines(paste("PKG", name, as.character(utils::packageVersion(name)), sep="|"))
'''
    try:
        completed = subprocess.run(
            ['Rscript', '-e', script], check=True, capture_output=True,
            text=True, timeout=30,
        )
    except FileNotFoundError:
        return {'available': False, 'reason': 'Rscript unavailable'}
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        return {'available': False, 'reason': type(error).__name__}

    r_info = {'available': True, 'packages': {}}
    for line in completed.stdout.splitlines():
        fields = line.strip().split('|', 2)
        if len(fields) == 2 and fields[0] in {'R', 'BIOC'}:
            r_info['version' if fields[0] == 'R' else 'bioconductor'] = fields[1]
        elif len(fields) == 3 and fields[0] == 'PKG':
            r_info['packages'][fields[1]] = fields[2]
    return r_info

@lru_cache(maxsize=1)
def runtime_provenance():
    packages = {}
    for name in PYTHON_PACKAGES:
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    return {
        'python': platform.python_version(),
        'system': platform.system(),
        'architecture': platform.machine(),
        'packages': packages,
        'r': _r_runtime_provenance(),
        'pgen_seed': 42,
        'pgen_processes': 1,
    }
