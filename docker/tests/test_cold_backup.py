import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tarfile
import pytest

spec=importlib.util.spec_from_file_location('cold_backup',Path(__file__).parents[1]/'operations'/'cold_backup.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def make_volumes(path):
    path.mkdir()
    for name in module.VOLUMES:(path/name).mkdir()
    return path


def test_five_volumes_config_and_ownership_round_trip(tmp_path):
    source=make_volumes(tmp_path/'source');target=make_volumes(tmp_path/'target')
    for index,name in enumerate(module.VOLUMES):
        file=source/name/'数据.bin';file.write_bytes(bytes(range(256))*20)
        os.chown(file,10001+index,10001+index)
    (source/'app_data'/'内部链接').symlink_to('数据.bin')
    (source/'mysql_data'/'mysql.sock').symlink_to('/var/run/mysqld/mysqld.sock')
    config=tmp_path/'source.env';config.write_text('SECRET_KEY=synthetic-only\n',encoding='utf-8')
    archive=tmp_path/'backup.tar.gz'
    module.backup(source,config,archive)
    assert stat.S_IMODE(archive.stat().st_mode)==0o600
    with tarfile.open(archive) as bundle:
        assert 'volumes/mysql_data/mysql.sock' not in bundle.getnames()
    destination=tmp_path/'config';destination.mkdir()
    module.restore(target,destination,archive)
    for index,name in enumerate(module.VOLUMES):
        restored=target/name/'数据.bin'
        assert restored.read_bytes()==(source/name/'数据.bin').read_bytes()
        assert restored.stat().st_uid==10001+index
    assert (target/'app_data'/'内部链接').is_symlink()
    assert (target/'app_data'/'内部链接').read_bytes()==(source/'app_data'/'数据.bin').read_bytes()
    assert (destination/'.env').read_bytes()==config.read_bytes()
    assert stat.S_IMODE((destination/'.env').stat().st_mode)==0o600
    with pytest.raises(ValueError,match='拒绝覆盖'):module.restore(target,destination,archive)
    with pytest.raises(ValueError,match='拒绝覆盖'):module.backup(source,config,archive)


def test_rejects_escaping_archive_before_writing_volumes(tmp_path):
    target=make_volumes(tmp_path/'target');config=tmp_path/'config';config.mkdir()
    archive=tmp_path/'invalid.tar.gz'
    with tarfile.open(archive,'w:gz') as bundle:
        payload=json.dumps({'volumes':list(module.VOLUMES)}).encode()
        member=tarfile.TarInfo('manifest.json');member.size=len(payload);bundle.addfile(member,io.BytesIO(payload))
        member=tarfile.TarInfo('config/.env');member.size=3;bundle.addfile(member,io.BytesIO(b'env'))
        member=tarfile.TarInfo('volumes/app_data/../../outside');member.size=3;bundle.addfile(member,io.BytesIO(b'bad'))
    with pytest.raises(ValueError,match='非法'):module.restore(target,config,archive)
    assert all(not any((target/name).iterdir()) for name in module.VOLUMES)
    assert not any(config.iterdir())


def test_rejects_missing_volume_mount(tmp_path):
    root=tmp_path/'volumes';root.mkdir()
    with pytest.raises(ValueError,match='挂载'):module.check_roots(root)


def test_legacy_config_name_restores_to_current_env(tmp_path):
    source=make_volumes(tmp_path/'source');target=make_volumes(tmp_path/'target')
    config=tmp_path/'env';config.write_text('HTTP_PORT=19999\n')
    archive=tmp_path/'new.tar.gz';legacy=tmp_path/'old.tar.gz'
    module.backup(source,config,archive)
    with tarfile.open(archive,'r:gz') as original, tarfile.open(legacy,'w:gz') as out:
        for member in original:
            data=original.extractfile(member) if member.isfile() else None
            if member.name=='config/.env': member.name='config/.env.docker'
            out.addfile(member,data)
    destination=tmp_path/'config';destination.mkdir()
    module.restore(target,destination,legacy)
    assert (destination/'.env').read_text()=='HTTP_PORT=19999\n'
