"""Inventory local code/cache size without traversing external data junctions."""
import argparse
import json
import os
from pathlib import Path
import shutil
import stat
import time

CACHES = {'__pycache__', '.pytest_cache', '.ruff_cache', '.mypy_cache', '.vite'}
PROTECTED = {'.git', 'node_modules', '.venv', 'venv', 'data', 'test_data', '_reference', '.dev-runtime'}

def linked(path):
    info = path.lstat()
    return path.is_symlink() or bool(getattr(info, 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)

def inventory(root, clean=False, days=7):
    root = Path(root).resolve(strict=True)
    if not (root/'flask_app').is_dir() or not (root/'frontend').is_dir():
        raise ValueError('Root must be the immune repertoire project directory')
    report = {'root':str(root), 'code_bytes':0, 'cache_bytes':0, 'removed_bytes':0, 'removed':[], 'protected':[], 'errors':[]}
    cutoff = time.time() - days * 86400
    def cache_files(path):
        files=[]
        for current, dirs, names in os.walk(path, followlinks=False):
            directory=Path(current)
            for name in list(dirs):
                if linked(directory/name):
                    raise ValueError('Cache contains a junction; skipped')
            for name in names:
                file=directory/name
                if linked(file): raise ValueError('Cache contains a link; skipped')
                files.append(file)
        return files
    def visit(folder):
        try:
            for path in folder.iterdir():
                try:
                    if linked(path):
                        report['protected'].append(str(path));continue
                    if path.is_dir():
                        if path.name in CACHES or path.name.startswith('pytest-cache-files-'):
                            files=cache_files(path)
                            size=sum(file.stat().st_size for file in files)
                            report['cache_bytes']+=size
                            newest=max([path.stat().st_mtime]+[file.stat().st_mtime for file in files])
                            if clean and newest < cutoff:
                                resolved=path.resolve(strict=True)
                                if root not in resolved.parents or linked(path): raise ValueError('Cache outside project')
                                shutil.rmtree(resolved)
                                report['removed_bytes']+=size;report['removed'].append(str(resolved))
                        elif path.name in PROTECTED:
                            report['protected'].append(str(path))
                        else: visit(path)
                    elif path.is_file():report['code_bytes']+=path.stat().st_size
                except (OSError,ValueError) as error:report['errors'].append({'path':str(path),'error':str(error)})
        except OSError as error:report['errors'].append({'path':str(folder),'error':str(error)})
    visit(root)
    return report

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root',default=Path(__file__).resolve().parents[1])
    parser.add_argument('--clean-caches',action='store_true')
    parser.add_argument('--older-than-days',type=int,default=7)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.older_than_days<1:parser.error('Keep at least one day of recent caches')
    report=inventory(args.root,args.clean_caches,args.older_than_days)
    if args.output:args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({key:report[key] for key in ['root','code_bytes','cache_bytes','removed_bytes']},ensure_ascii=False))
    print(f"Protected entries: {len(report['protected'])}; inaccessible/skipped: {len(report['errors'])}; removed caches: {len(report['removed'])}")
