"""One-time ownership migration for application data volumes, run as root."""
import os
import stat
from pathlib import Path

ROOTS = (Path("/app/flask_app/data"), Path("/app/tmp"))
APP_UID = int(os.environ.get("APP_UID", "10001"))
APP_GID = int(os.environ.get("APP_GID", "10001"))
if APP_UID <= 0 or APP_GID <= 0:
    raise ValueError("应用文件必须归属非 root 用户，请设置正确的 APP_UID 和 APP_GID")


def initialize_volumes():
    changed = 0
    for root in ROOTS:
        if root.is_symlink() or root.resolve() != root.absolute():
            raise ValueError(f"数据卷根目录不能是符号链接：{root}")
        root.mkdir(parents=True, exist_ok=True)
        for directory, dirs, files in os.walk(root, followlinks=False):
            dirs[:] = [name for name in dirs if not (Path(directory) / name).is_symlink()]
            for path in [Path(directory), *(Path(directory) / name for name in files)]:
                info = path.lstat()
                if stat.S_ISLNK(info.st_mode):
                    continue
                if not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
                    continue
                os.chown(path, APP_UID, APP_GID, follow_symlinks=False)
                owner_bits = stat.S_IRUSR | stat.S_IWUSR | (stat.S_IXUSR if path.is_dir() else 0)
                os.chmod(path, stat.S_IMODE(info.st_mode) | owner_bits, follow_symlinks=False)
                changed += 1
    return changed


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("请通过数据卷初始化服务以管理员身份运行。")
    print(f"已完成 {initialize_volumes()} 个数据目录或文件的应用用户权限设置。")
