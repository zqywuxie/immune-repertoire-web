import os, pathlib, subprocess, tempfile
script=pathlib.Path(__file__).resolve().parents[2]/'deploy.sh'
source=script.read_bytes()
subprocess.run(['bash','-n',str(script)],check=True)
for case in ['success','dirty','pull_failed','build_failed','health_failed']:
 with tempfile.TemporaryDirectory() as directory:
  root=pathlib.Path(directory); (root/'deploy.sh').write_bytes(source)
  (root/'.env.docker').write_text('')
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
 if [[ " $* " == *" build "* && $CHECK_CASE == build_failed ]]; then exit 1; fi
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
  if case=='success':
   assert result.returncode==0,result.stderr
   assert len(pull)==1 and pull[0]<build[0]<up[0],lines
  else:
   assert result.returncode!=0,case
   assert '部署完成，' not in result.stdout
   if case in ['dirty','pull_failed']:assert not build and not up
   if case=='build_failed':assert not up
  print(case,'passed')
