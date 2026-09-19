"""Check actual imports, including optional scientific runtime APIs."""
import argparse
import importlib
import subprocess

parser = argparse.ArgumentParser()
parser.add_argument('--full', action='store_true')
args = parser.parse_args()
for name in ['flask', 'pandas', 'numpy', 'scipy', 'sklearn', 'umap', 'pptx', 'fitz', 'redis', 'rq', 'statsmodels', 'scikit_posthocs']:
    importlib.import_module(name)
    print(name + ': OK', flush=True)
if args.full:
    from sonnia.processing import Processing
    from sonnia.sonnia import SoNNia
    subprocess.run(['Rscript', '-e', 'stopifnot(all(vapply(c("clusterProfiler","org.Hs.eg.db","enrichplot","DOSE"),requireNamespace,logical(1),quietly=TRUE)))'], check=True)
    print('SoNNia and R/Bioconductor: OK')
