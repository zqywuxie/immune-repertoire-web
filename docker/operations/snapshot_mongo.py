from pathlib import Path
import json,shutil,tarfile
source,work,backup=Path('/source'),Path('/work'),Path('/backup')
assert (source/'WiredTiger').is_file()
assert not any(work.iterdir())
archive=backup/'legacy-mongo.tar.gz'
assert not archive.exists()
with tarfile.open(archive,'w:gz',compresslevel=1) as output:
    output.add(source,arcname='mongo-data')
shutil.copytree(source,work,dirs_exist_ok=True)
files=[p for p in source.rglob('*') if p.is_file()]
assert all((work/p.relative_to(source)).stat().st_size==p.stat().st_size for p in files)
report={'files':len(files),'source_bytes':sum(p.stat().st_size for p in files),'archive_bytes':archive.stat().st_size}
(backup/'mongo-snapshot.json').write_text(json.dumps(report,indent=2))
print(report)
