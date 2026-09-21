import argparse
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import time

def load(path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

parser = argparse.ArgumentParser(description='临时目录权限扫描基准')
parser.add_argument('--baseline', type=Path, required=True)
args = parser.parse_args()
current = load(Path(__file__).parents[1] / 'app' / 'init_volume_permissions.py')
previous = load(args.baseline)
with tempfile.TemporaryDirectory() as temporary:
    root = Path(temporary) / 'data'
    root.mkdir()
    for index in range(100):
        directory = root / str(index)
        directory.mkdir()
        for number in range(200):
            (directory / str(number)).touch()
    for module in (previous, current):
        module.ROOTS = (root,)
        module.APP_UID = os.getuid()
        module.APP_GID = os.getgid()
    measurements = {'before': [], 'after': []}
    for _ in range(3):
        for name, module in (('before', previous), ('after', current)):
            begin = time.perf_counter()
            assert module.initialize_volumes() == 0
            measurements[name].append(time.perf_counter() - begin)
    print(json.dumps({'files': 20000, 'directories': 101, 'seconds': measurements}))
