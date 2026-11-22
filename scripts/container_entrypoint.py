"""Prepare mounted data ownership, then run the application as paperplane."""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import sys

APP_USER = "paperplane"
MARKER_NAME = ".paperplane-owner-1001-v1"
PROTECTED_ROOTS = tuple(Path(value) for value in (
    "/", "/app", "/usr", "/etc", "/bin", "/sbin", "/lib", "/lib64",
    "/var", "/tmp", "/home", "/root", "/proc", "/sys", "/dev",
))


def _validate_mount_path(path: Path) -> Path:
    if not path.is_absolute():
        raise ValueError(f"Persistent data path must be absolute: {path}")
    resolved = path.resolve()
    if any(resolved == protected or resolved in protected.parents for protected in PROTECTED_ROOTS):
        raise ValueError(f"Refusing to change ownership of protected system path: {resolved}")
    return resolved


def _chown_tree_without_following_symlinks(root: Path, uid: int, gid: int) -> None:
    root.mkdir(parents=True, exist_ok=True)
    for current, child_names, file_names in os.walk(root, topdown=True, followlinks=False):
        current_path = Path(current)
        safe_children = []
        for name in child_names:
            child = current_path / name
            if child.is_symlink():
                continue
            os.chown(child, uid, gid, follow_symlinks=False)
            safe_children.append(name)
        child_names[:] = safe_children
        for name in file_names:
            child = current_path / name
            if not child.is_symlink():
                os.chown(child, uid, gid, follow_symlinks=False)
        os.chown(current_path, uid, gid, follow_symlinks=False)


def _prepare_mount(path: Path, uid: int, gid: int) -> None:
    path.mkdir(parents=True, exist_ok=True)
    marker = path / MARKER_NAME
    if marker.is_file():
        os.chown(path, uid, gid, follow_symlinks=False)
        return
    _chown_tree_without_following_symlinks(path, uid, gid)
    marker.touch(mode=0o600, exist_ok=True)
    os.chown(marker, uid, gid, follow_symlinks=False)


def main() -> None:
    command = sys.argv[1:] or [sys.executable, "app.py"]
    account = pwd.getpwnam(APP_USER)
    uid, gid = account.pw_uid, account.pw_gid

    data_dir = _validate_mount_path(Path(os.getenv("PAPERPLANE_DATA_DIR", "/data")))
    backup_dir = _validate_mount_path(Path(os.getenv("PAPERPLANE_BACKUP_DIR", "/backups")))
    mount_paths = [data_dir]
    if backup_dir != data_dir and backup_dir.exists():
        mount_paths.append(backup_dir)

    if os.geteuid() == 0:
        for mount_path in mount_paths:
            _prepare_mount(mount_path, uid, gid)
        os.initgroups(APP_USER, gid)
        os.setgid(gid)
        os.setuid(uid)
    else:
        for mount_path in mount_paths:
            mount_path.mkdir(parents=True, exist_ok=True)
            if not os.access(mount_path, os.W_OK | os.X_OK):
                raise PermissionError(
                    f"{mount_path} is not writable by UID {os.geteuid()}; "
                    "the container entrypoint must start with permission to prepare mounted volumes."
                )

    os.execvp(command[0], command)


if __name__ == "__main__":
    main()
