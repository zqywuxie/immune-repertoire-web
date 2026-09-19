"""Capture the worker environment actually used to execute a task."""
import platform
from functools import lru_cache
from importlib.metadata import PackageNotFoundError, version

@lru_cache(maxsize=1)
def runtime_provenance():
    packages = {}
    for name in ('numpy', 'pandas', 'scipy', 'scikit-learn', 'umap-learn',
                 'matplotlib', 'sonnia', 'tensorflow', 'rq'):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            pass
    return {'python': platform.python_version(), 'system': platform.system(),
            'packages': packages, 'pgen_seed': 42, 'pgen_processes': 1}
