"""Snapshot a STOPPED MySQL data volume and create an isolated working copy.

Run only after the owning MySQL container has stopped cleanly. Mount its volume
at /source read-only, an empty work volume at /work and a backup volume at /backup.
"""
import json
from pathlib import Path
import shutil
import tarfile
from datetime import datetime, timezone

source, work, backup = Path('/source'), Path('/work'), Path('/backup')
assert (source/'mysql').is_dir(), 'Not a MySQL data directory'
assert not any(work.iterdir()), 'Working volume must be empty'
archive=backup/'legacy-mysql.tar.gz'
assert not archive.exists(), 'Backup already exists; refusing overwrite'
files=[p for p in source.rglob('*') if p.is_file() and not p.is_symlink()]
with tarfile.open(archive, 'w:gz', compresslevel=1) as target:
    target.add(source, arcname='mysql-data', recursive=True)
with tarfile.open(archive, 'r:gz') as verify:
    assert sum(member.isfile() for member in verify.getmembers()) == len(files)
shutil.copytree(source,work,dirs_exist_ok=True,symlinks=True)
for original in files:
    copied=work/original.relative_to(source)
    assert copied.is_file() and copied.stat().st_size==original.stat().st_size
report={'created_at':datetime.now(timezone.utc).isoformat(),'files':len(files),
        'source_bytes':sum(p.stat().st_size for p in files),'archive_bytes':archive.stat().st_size,
        'archive':str(archive),'working_copy_verified':True}
(backup/'snapshot.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report))
