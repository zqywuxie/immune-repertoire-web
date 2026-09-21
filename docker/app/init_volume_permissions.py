"""One-time ownership migration for application data volumes, run as root."""
import os
import stat
from pathlib import Path

ROOTS = (Path("/app/flask_app/data"), Path("/app/tmp"))
APP_UID = int(os.environ.get("APP_UID", "10001"))
APP_GID = int(os.environ.get("APP_GID", "10001"))
if APP_UID <= 0 or APP_GID <= 0:
    raise ValueError("应用文件必须归属非 root 用户，请设置正确的 APP_UID 和 APP_GID")


def repair_permissions(path, info):
    ownership_changed = (info.st_uid, info.st_gid) != (APP_UID, APP_GID)
    if ownership_changed:
        os.chown(path, APP_UID, APP_GID, follow_symlinks=False)
    owner_bits = stat.S_IRUSR | stat.S_IWUSR
    if stat.S_ISDIR(info.st_mode):
        owner_bits |= stat.S_IXUSR
    mode = stat.S_IMODE(info.st_mode) | owner_bits
    mode_changed = mode != stat.S_IMODE(info.st_mode)
    if mode_changed:
        os.chmod(path, mode, follow_symlinks=False)
    return int(ownership_changed or mode_changed)


def initialize_volumes():
    changed = 0
    for root in ROOTS:
        if root.is_symlink() or root.resolve() != root.absolute():
            raise ValueError(f"数据卷根目录不能是符号链接：{root}")
        root.mkdir(parents=True, exist_ok=True)
        pending = [root]
        while pending:
            directory = pending.pop()
            changed += repair_permissions(directory, directory.lstat())
            with os.scandir(directory) as entries:
                for entry in entries:
                    info = entry.stat(follow_symlinks=False)
                    if stat.S_ISDIR(info.st_mode):
                        pending.append(Path(entry.path))
                    elif stat.S_ISREG(info.st_mode):
                        changed += repair_permissions(entry.path, info)
    return changed


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("请通过数据卷初始化服务以管理员身份运行。")
    print(f"已完成 {initialize_volumes()} 个数据目录或文件的应用用户权限设置。")
