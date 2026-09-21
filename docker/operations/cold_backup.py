"""Cold backup/restore of all platform volumes. Stop writers before using this tool."""
import argparse
import io
import json
import os
from pathlib import Path
import tarfile
from datetime import datetime, timezone

VOLUMES = ("app_data", "app_tmp", "mysql_data", "mongo_data", "redis_data")


def check_roots(root):
    for name in VOLUMES:
        path = root / name
        if path.is_symlink() or not path.is_dir() or path.resolve().parent != root.resolve():
            raise ValueError(f"需要独立的数据卷挂载：{name}")


def backup_member(member):
    # The MySQL image recreates this runtime socket link when starting.
    # Preserve ordinary files and retain the restore filter for all other links.
    if member.name == "volumes/mysql_data/mysql.sock" and member.issym():
        return None
    return member


def backup(root, config, archive):
    check_roots(root)
    if not config.is_file(): raise ValueError("缺少部署配置文件")
    if archive.exists(): raise ValueError("备份文件已存在，拒绝覆盖")
    partial = archive.with_name(archive.name + ".partial")
    created = False
    try:
        descriptor = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(descriptor, "wb") as stream:
            with tarfile.open(fileobj=stream, mode="w:gz", compresslevel=1, dereference=False) as bundle:
                for name in VOLUMES:
                    bundle.add(root / name, arcname="volumes/" + name, filter=backup_member)
                bundle.add(config, arcname="config/.env")
                metadata = json.dumps({"format": 2, "created_at": datetime.now(timezone.utc).isoformat(), "volumes": list(VOLUMES), "requires_stopped_services": True}, ensure_ascii=False).encode("utf-8")
                info=tarfile.TarInfo("manifest.json"); info.size=len(metadata); info.mode=0o600
                bundle.addfile(info, io.BytesIO(metadata))
        # Read every member to catch truncated compression streams before exposing the backup.
        with tarfile.open(partial, "r:gz") as bundle:
            for member in bundle:
                if member.isfile():
                    with bundle.extractfile(member) as source:
                        while source.read(1024 * 1024): pass
        # A hard link publishes without overwriting a concurrently created backup.
        os.link(partial, archive)
        partial.unlink()
    except BaseException:
        if created: partial.unlink(missing_ok=True)
        raise


def restore(root, config_dir, archive):
    check_roots(root)
    if any(any((root / name).iterdir()) for name in VOLUMES):
        raise ValueError("恢复目标卷必须为空，拒绝覆盖现有数据")
    if not config_dir.is_dir() or config_dir.is_symlink() or any(config_dir.iterdir()):
        raise ValueError("恢复配置目录必须存在且为空")
    with tarfile.open(archive, "r:gz") as bundle:
        members=bundle.getmembers()
        manifest=bundle.extractfile("manifest.json")
        if manifest is None or json.load(manifest).get("volumes") != list(VOLUMES):
            raise ValueError("备份清单不完整")
        config_members = [member.name for member in members if member.name in {"config/.env", "config/.env.docker"}]
        if len(config_members) != 1:
            raise ValueError("备份必须包含唯一的部署配置")
        config_member = config_members[0]
        seen=set()
        for member in members:
            path=Path(member.name)
            if path.is_absolute() or ".." in path.parts or member.name in seen:
                raise ValueError("备份包含非法或重复路径")
            seen.add(member.name)
            if member.name == "manifest.json": continue
            if member.name == config_member:
                if not member.isfile(): raise ValueError("配置备份必须为普通文件")
                continue
            if len(path.parts)<2 or path.parts[0]!="volumes" or path.parts[1] not in VOLUMES:
                raise ValueError("备份包含未知数据卷")
            # Validate link/device entries before any destination is modified.
            candidate=tarfile.TarInfo(path.relative_to('volumes').as_posix())
            candidate.type=member.type;candidate.linkname=member.linkname;candidate.mode=member.mode
            if member.islnk():
                link=Path(member.linkname)
                if link.is_absolute() or len(link.parts)<2 or link.parts[0]!='volumes': raise ValueError("非法硬链接")
                candidate.linkname=link.relative_to('volumes').as_posix()
            tarfile.data_filter(candidate, str(root))
        if config_member not in seen or any('volumes/'+name not in seen for name in VOLUMES):
            raise ValueError("备份缺少数据卷或部署配置")
        for member in members:
            if not member.name.startswith('volumes/'): continue
            member.name=member.name[len('volumes/'):]
            if member.islnk(): member.linkname=member.linkname[len('volumes/'):]
            # tarfile's data filter rejects escaping links; root restore preserves ownership explicitly.
            safe=tarfile.data_filter(member, str(root))
            if safe is not None:
                safe.uid=member.uid;safe.gid=member.gid;safe.uname='';safe.gname=''
                bundle.extract(safe, path=root, filter=lambda entry, destination: entry)
        target=config_dir/'.env'
        descriptor=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
        with os.fdopen(descriptor,'wb') as output, bundle.extractfile(config_member) as source:
            while chunk:=source.read(1024*1024): output.write(chunk)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['backup','restore'])
    parser.add_argument('--archive',required=True,type=Path)
    args=parser.parse_args()
    if args.action=='backup': backup(Path('/volumes'),Path('/config/.env'),args.archive)
    else: restore(Path('/volumes'),Path('/config'),args.archive)
    print('备份已验证' if args.action=='backup' else '数据卷和配置已恢复；请完成服务启动验证')
