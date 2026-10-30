"""Hot-backup and retention daemon for Paperplane's SQLite WAL database."""

from __future__ import annotations

import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timezone
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import persistence  # noqa: E402
from config import DATA_DIR  # noqa: E402


def _env_int(name: str, default: int) -> int:
    try:
        return max(1, int(os.getenv(name, str(default))))
    except ValueError:
        return default


def prune_backups(backup_dir: Path, retention_days: int) -> int:
    cutoff = time.time() - (retention_days * 24 * 60 * 60)
    removed = 0
    for backup in backup_dir.glob("paperplane_backup_*.sqlite3"):
        try:
            if backup.stat().st_mtime < cutoff:
                backup.unlink()
                removed += 1
        except OSError:
            continue
    return removed


def backup_database(backup_dir: Path | None = None) -> Path:
    """Create an atomic, non-blocking SQLite native backup from the live WAL DB."""
    target_dir = backup_dir or (DATA_DIR / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_file = target_dir / f"paperplane_backup_{timestamp}.sqlite3"
    temporary_file = target_dir / f".{backup_file.name}.{os.getpid()}.tmp"

    try:
        with closing(persistence.connect()) as src:
            with closing(sqlite3.connect(temporary_file)) as dst:
                src.backup(dst)
                dst.commit()
        os.replace(temporary_file, backup_file)
        try:
            backup_file.chmod(0o600)
        except OSError:
            pass
        return backup_file
    finally:
        if temporary_file.exists():
            temporary_file.unlink(missing_ok=True)


def run_once(retention_days: int) -> Path:
    backup_dir = DATA_DIR / "backups"
    backup_file = backup_database(backup_dir)
    removed = prune_backups(backup_dir, retention_days)
    print(
        f"backup_created={backup_file} retained_days={retention_days} "
        f"old_backups_removed={removed}",
        flush=True,
    )
    return backup_file


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--daemon", action="store_true", help="Repeat on a fixed interval.")
    parser.add_argument("--interval", type=int, default=_env_int("PAPERPLANE_BACKUP_INTERVAL_SECONDS", 86400))
    parser.add_argument("--retention-days", type=int, default=_env_int("PAPERPLANE_BACKUP_RETENTION_DAYS", 14))
    args = parser.parse_args()

    while True:
        try:
            run_once(max(1, args.retention_days))
        except Exception as exc:  # pragma: no cover - daemon safety path
            print(f"backup_failed={exc}", file=sys.stderr, flush=True)
            if not args.daemon:
                return 1
        if not args.daemon:
            return 0
        time.sleep(max(60, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
