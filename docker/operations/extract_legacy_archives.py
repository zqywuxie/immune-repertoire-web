"""Extract data archives into the new volume, refusing path escapes and conflicts."""
from pathlib import Path
import tarfile,shutil,json
root=Path('/app/flask_app/data')
report={}
for name,relative in [('data','.'),('results','results'),('test-data','imported/test_data'),('artificial','imported/artificial_peps')]:
    destination=(root/relative).resolve();destination.mkdir(parents=True,exist_ok=True)
    count=size=0
    archive_name={'results':'results-registered','artificial':'artificial-valid'}.get(name,name)
    with tarfile.open('/archives/'+archive_name+'.tar','r|') as archive:
        for member in archive:
            target=(destination/member.name).resolve()
            if target!=destination and destination not in target.parents:raise ValueError('Unsafe archive path')
            if member.isdir():target.mkdir(parents=True,exist_ok=True);continue
            if not member.isfile():raise ValueError('Unexpected non-file archive member: '+member.name)
            source=archive.extractfile(member)
            target.parent.mkdir(parents=True,exist_ok=True)
            if target.exists():
                with target.open('rb') as existing:
                    while chunk:=source.read(1024*1024):
                        if chunk!=existing.read(len(chunk)):raise ValueError('Conflicting target: '+str(target))
                    if existing.read(1):raise ValueError('Conflicting target length')
            else:
                with target.open('xb') as output:shutil.copyfileobj(source,output,length=1024*1024)
            assert target.stat().st_size==member.size
            count+=1;size+=member.size
    report[name]={'files':count,'bytes':size};print(name,report[name],flush=True)
Path('/backup/files-staged.json').write_text(json.dumps(report,indent=2))
