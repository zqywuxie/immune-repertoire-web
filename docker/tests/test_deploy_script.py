import os, pathlib, subprocess, tempfile
script=pathlib.Path(__file__).resolve().parents[2]/'deploy.sh'
source=script.read_bytes()
subprocess.run(['bash','-n',str(script)],check=True)
for case in ['success','missing','legacy','dirty','build_failed','permissions_failed','health_failed','active_jobs']:
 with tempfile.TemporaryDirectory() as directory:
  root=pathlib.Path(directory); (root/'deploy.sh').write_bytes(source)
  if case!='missing': (root/('.env.docker' if case=='legacy' else '.env')).write_text('HTTP_PORT=18080\nSECRET_KEY=preserved-test-only\n')
  (root/'docker/app').mkdir(parents=True);(root/'docker/app/check_active_jobs.py').write_text('# preflight')
  binary=root/'bin';binary.mkdir()
  mock='''#!/bin/bash
echo "$(basename "$0") $*" >> "$CHECK_LOG"
if [[ $(basename "$0") == git ]]; then
 case "$1" in
 symbolic-ref) echo main;;
 status) [[ $CHECK_CASE != dirty ]] || echo ' M changed.py';;
 rev-parse) echo abc123;;
 pull) [[ $CHECK_CASE != pull_failed ]] || exit 1;;
 esac
else
 if [[ " $* " == *" ps --status running -q api "* && $CHECK_CASE != missing && $CHECK_CASE != legacy ]]; then echo api-container; fi
 if [[ " $* " == *" exec -T api python - "* && $CHECK_CASE == active_jobs ]]; then exit 1; fi
 if [[ " $* " == *" build "* && $CHECK_CASE == build_failed ]]; then exit 1; fi
 if [[ " $* " == *" volume-init "* && $CHECK_CASE == permissions_failed ]]; then exit 1; fi
 if [[ " $* " == *" up "* && $CHECK_CASE == health_failed ]]; then exit 1; fi
fi
exit 0
'''
  for name in ['git','docker']:
   p=binary/name;p.write_text(mock);p.chmod(0o755)
  env={**os.environ,'PATH':str(binary)+':'+os.environ['PATH'],'CHECK_CASE':case,'CHECK_LOG':str(root/'calls')}
  env.pop('IMMUNE_DEPLOY_PULLED_REVISION',None)
  result=subprocess.run(['bash',str(root/'deploy.sh')],env=env,capture_output=True,text=True)
  lines=(root/'calls').read_text().splitlines()
  pull=[i for i,line in enumerate(lines) if line.startswith('git pull ')]
  build=[i for i,line in enumerate(lines) if ' build api web' in line]
  up=[i for i,line in enumerate(lines) if ' up -d --wait ' in line]
  assert not pull, lines
  maintenance=[i for i,line in enumerate(lines) if 'deployment_maintenance enable' in line]
  released=[i for i,line in enumerate(lines) if 'deployment_maintenance disable' in line]
  if maintenance:
   assert released and released[-1] > maintenance[0], lines
  if case=='success':
   assert result.returncode==0,result.stderr
   permissions=next(i for i,line in enumerate(lines) if line.endswith("volume-init"))
   assert not pull and build[0]<permissions<up[0],lines
   assert (root/'.env').read_text()=='HTTP_PORT=18080\nSECRET_KEY=preserved-test-only\n'
   assert all('--env-file .env -f' in line for line in lines if line.startswith('docker compose ') and ' version' not in line)
  else:
   assert result.returncode!=0,case
   assert '部署完成，' not in result.stdout
   if case in ['dirty','pull_failed','legacy','missing']:assert not build and not up
   if case in ['build_failed','permissions_failed','active_jobs']:assert not up
  if case in ['legacy','missing']:
   assert not (root/'.env').exists()
   assert 'bash init-env.sh' in result.stderr
  assert not any(line.startswith('docker run ') for line in lines)
  print(case,'passed')
