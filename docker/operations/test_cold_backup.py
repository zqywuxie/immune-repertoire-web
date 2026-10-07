import importlib.util
import io
import json
import os
from pathlib import Path
import tarfile
import zlib

import pytest


SOURCE = Path(__file__).with_name("cold_backup.py")
SPEC = importlib.util.spec_from_file_location("platform_cold_backup", SOURCE)
cold_backup = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cold_backup)


def volume_root(path):
    path.mkdir()
    for name in cold_backup.VOLUMES:
        (path / name).mkdir()
        (path / name / "marker.txt").write_text(name, encoding="utf-8")
    return path


def test_cold_backup_restores_every_compose_volume_and_environment(tmp_path):
    source = volume_root(tmp_path / "source")
    config = tmp_path / ".env"
    config.write_text("APP_UPLOAD_DIR=/srv/uploads\nAPP_RESULTS_DIR=/srv/results\n", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    cold_backup.backup(source, config, archive)

    target = volume_root(tmp_path / "target")
    for name in cold_backup.VOLUMES:
        (target / name / "marker.txt").unlink()
    restore_config = tmp_path / "restore-config"
    restore_config.mkdir()
    cold_backup.restore(target, restore_config, archive)

    manifest = json.loads(tarfile.open(archive, "r:gz").extractfile("manifest.json").read())
    assert manifest["format"] == 3
    assert manifest["volumes"] == list(cold_backup.VOLUMES)
    assert all((target / name / "marker.txt").read_text(encoding="utf-8") == name for name in cold_backup.VOLUMES)
    assert (restore_config / ".env").read_text(encoding="utf-8") == config.read_text(encoding="utf-8")
    assert (restore_config / ".env").stat().st_mode & 0o777 == 0o600


def test_corrupt_archive_is_rejected_before_any_volume_is_modified(tmp_path):
    source = volume_root(tmp_path / "source")
    config = tmp_path / ".env"
    config.write_text("SECRET_KEY=synthetic\n", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    cold_backup.backup(source, config, archive)

    corrupted = tmp_path / "corrupted.tar.gz"
    payload = bytearray(archive.read_bytes())
    payload[-8] ^= 0xFF
    corrupted.write_bytes(payload)
    target = volume_root(tmp_path / "target")
    for name in cold_backup.VOLUMES:
        (target / name / "marker.txt").unlink()
    restore_config = tmp_path / "restore-config"
    restore_config.mkdir()

    with pytest.raises((OSError, EOFError, tarfile.TarError, zlib.error)):
        cold_backup.restore(target, restore_config, corrupted)

    assert all(not any((target / name).iterdir()) for name in cold_backup.VOLUMES)
    assert not any(restore_config.iterdir())


def test_legacy_five_volume_backup_is_rejected_as_incomplete(tmp_path):
    target = volume_root(tmp_path / "target")
    for name in cold_backup.VOLUMES:
        (target / name / "marker.txt").unlink()
    restore_config = tmp_path / "restore-config"
    restore_config.mkdir()
    archive = tmp_path / "legacy.tar.gz"
    metadata = json.dumps({"format": 2, "volumes": list(cold_backup.LEGACY_VOLUMES)}).encode("utf-8")
    with tarfile.open(archive, "w:gz") as bundle:
        item = tarfile.TarInfo("manifest.json")
        item.size = len(metadata)
        bundle.addfile(item, io.BytesIO(metadata))

    with pytest.raises(ValueError, match="未包含独立上传和结果卷"):
        cold_backup.restore(target, restore_config, archive)

    assert all(not any((target / name).iterdir()) for name in cold_backup.VOLUMES)
    assert not any(restore_config.iterdir())


def test_backup_does_not_publish_links_rejected_by_restore(tmp_path):
    source = volume_root(tmp_path / "source")
    external = tmp_path / "external.txt"
    external.write_text("not a backed-up volume", encoding="utf-8")
    (source / "app_data" / "outside-link").symlink_to(external)
    config = tmp_path / ".env"
    config.write_text("SECRET_KEY=synthetic\n", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    with pytest.raises((ValueError, tarfile.FilterError)):
        cold_backup.backup(source, config, archive)
    assert not archive.exists()
    assert not archive.with_name(archive.name + ".partial").exists()
    assert external.read_text(encoding="utf-8") == "not a backed-up volume"


def test_backup_rejects_linked_config_before_publishing(tmp_path):
    source = volume_root(tmp_path / "source")
    actual = tmp_path / "actual-env"
    actual.write_text("SECRET_KEY=synthetic\n", encoding="utf-8")
    config = tmp_path / ".env"
    config.symlink_to(actual)
    archive = tmp_path / "backup.tar.gz"
    with pytest.raises(ValueError, match="配置备份必须为普通文件"):
        cold_backup.backup(source, config, archive)
    assert not archive.exists()
    assert not archive.with_name(archive.name + ".partial").exists()


def test_restore_keeps_internal_links_and_skips_mysql_runtime_socket(tmp_path):
    source = volume_root(tmp_path / "source")
    (source / "app_uploads" / "内部引用").symlink_to("marker.txt")
    (source / "mysql_data" / "mysql.sock").symlink_to("/var/run/mysqld/mysqld.sock")
    config = tmp_path / ".env"
    config.write_text("SECRET_KEY=synthetic\n", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    cold_backup.backup(source, config, archive)
    target = volume_root(tmp_path / "target")
    for name in cold_backup.VOLUMES:
        (target / name / "marker.txt").unlink()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cold_backup.restore(target, config_dir, archive)
    assert (target / "app_uploads" / "内部引用").is_symlink()
    assert (target / "app_uploads" / "内部引用").read_text(encoding="utf-8") == "app_uploads"
    assert not (target / "mysql_data" / "mysql.sock").is_symlink()


def test_restore_preserves_nanosecond_file_time_for_asset_signatures(tmp_path):
    source = volume_root(tmp_path / "source")
    asset = source / "app_uploads" / "marker.txt"
    timestamp = 1_790_983_155_444_449_151
    os.utime(asset, ns=(timestamp, timestamp))
    config = tmp_path / ".env"
    config.write_text("SECRET_KEY=synthetic\n", encoding="utf-8")
    archive = tmp_path / "backup.tar.gz"
    cold_backup.backup(source, config, archive)
    target = volume_root(tmp_path / "target")
    for name in cold_backup.VOLUMES:
        (target / name / "marker.txt").unlink()
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    cold_backup.restore(target, config_dir, archive)
    assert (target / "app_uploads" / "marker.txt").stat().st_mtime_ns == timestamp
