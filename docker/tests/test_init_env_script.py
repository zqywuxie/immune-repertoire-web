import os
import pathlib
import subprocess
import tempfile

script = pathlib.Path(__file__).resolve().parents[2] / 'init-env.sh'
subprocess.run(['bash', '-n', str(script)], check=True)
for case in ['existing', 'legacy', 'new', 'dirty', 'pull_failed']:
    with tempfile.TemporaryDirectory() as directory:
        root = pathlib.Path(directory)
        (root / 'init-env.sh').write_bytes(script.read_bytes())
        original = 'HTTP_PORT=18080\nSECRET_KEY=preserved-test-only\n'
        if case != 'new':
            (root / ('.env.docker' if case == 'legacy' else '.env')).write_text(original)
        binary = root / 'bin'; binary.mkdir()
        mock = r'''#!/bin/bash
echo "$(basename "$0") $*" >> "$CHECK_LOG"
if [[ $(basename "$0") == git ]]; then
 case "$1" in
 symbolic-ref) echo main;;
 status) [[ $CHECK_CASE != dirty ]] || echo ' M changed.py';;
 rev-parse) echo abc123;;
 pull) [[ $CHECK_CASE != pull_failed ]] || exit 1;;
 esac
else
 if [[ "$1" == run ]]; then printf 'generated=test-only\n' > "$CHECK_ROOT/.env"; fi
fi
exit 0
'''
        for name in ['git', 'docker']:
            path = binary / name; path.write_text(mock); path.chmod(0o755)
        env = {**os.environ, 'PATH':str(binary)+':'+os.environ['PATH'], 'CHECK_CASE':case, 'CHECK_LOG':str(root/'calls'), 'CHECK_ROOT':str(root)}
        env.pop('IMMUNE_INIT_PULLED_REVISION', None)
        result = subprocess.run(['bash', str(root/'init-env.sh')],env=env,capture_output=True,text=True)
        calls = (root/'calls').read_text().splitlines()
        pulls = [i for i, line in enumerate(calls) if line.startswith('git pull ')]
        assert not any(' build ' in line or ' up ' in line for line in calls)
        if case in ['dirty','pull_failed']:
            assert result.returncode != 0
            assert not any(line.startswith('docker ') for line in calls)
            assert (root/'.env').read_text() == original
        else:
            assert result.returncode == 0, result.stderr
            assert len(pulls) == 1
            if case in ['existing','legacy']:
                assert (root/'.env').read_text() == original
                assert not any(line.startswith('docker ') for line in calls)
            else:
                generated = next(i for i,line in enumerate(calls) if line.startswith('docker run '))
                assert pulls[0] < generated
        print(case, 'passed')
