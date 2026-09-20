"""Linux ownership migration preserves data and ignores linked external targets."""
import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest

spec = importlib.util.spec_from_file_location("volume_permissions", Path(__file__).parents[1] / "app" / "init_volume_permissions.py")
permissions = importlib.util.module_from_spec(spec)
spec.loader.exec_module(permissions)


@pytest.mark.parametrize("uid,gid", [(10001,10001),(12345,23456)])
def test_existing_data_becomes_writable_without_touching_link_targets(tmp_path, monkeypatch, uid, gid):
    monkeypatch.setattr(permissions,'APP_UID',uid)
    monkeypatch.setattr(permissions,'APP_GID',gid)
    # A separate process uses the same UID as the production application image.
    tmp_path.chmod(0o755)
    for parent in tmp_path.parents:
        if str(parent).startswith('/tmp/pytest'): parent.chmod(0o755)
    root=tmp_path/'data';root.mkdir()
    file=root/'existing.csv';file.write_text('sample,value\n001,2\n');file.chmod(0o400)
    outside=tmp_path/'outside';outside.mkdir();(outside/'preserved').write_text('keep')
    (root/'external').symlink_to(outside, target_is_directory=True)
    (root/'external-file').symlink_to(outside/'preserved')
    original=(outside/'preserved').stat()
    monkeypatch.setattr(permissions,'ROOTS',(root,))
    assert permissions.initialize_volumes()==2
    assert permissions.initialize_volumes()==0
    assert file.read_text()=='sample,value\n001,2\n'
    assert file.stat().st_uid==uid
    assert (outside/'preserved').stat().st_uid==original.st_uid
    assert outside.stat().st_uid==os.getuid()
    code="""
import os,sys
from pathlib import Path
os.setgid(int(sys.argv[3]));os.setuid(int(sys.argv[2]))
root=Path(sys.argv[1]);assert os.geteuid()!=0
with (root/'existing.csv').open('a') as file:file.write('002,3\\n')
(root/'new-result.csv').write_text('result')
"""
    subprocess.run([sys.executable,'-c',code,str(root),str(uid),str(gid)],check=True)
    assert (root/'new-result.csv').stat().st_uid==uid
    assert (root/'new-result.csv').stat().st_gid==gid


def test_linked_volume_root_is_rejected(tmp_path,monkeypatch):
    target=tmp_path/'target';target.mkdir()
    link=tmp_path/'link';link.symlink_to(target,target_is_directory=True)
    monkeypatch.setattr(permissions,'ROOTS',(link,))
    with pytest.raises(ValueError,match='符号链接'):
        permissions.initialize_volumes()
