from __future__ import annotations

import sqlite3
from pathlib import Path

import persistence
import converters


ROOT = Path(__file__).resolve().parents[1]


def test_docker_and_nginx_production_contracts():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "deploy" / "nginx.conf.template").read_text(encoding="utf-8")
    assert "PAPERPLANE_ENV: production" in compose
    assert "PAPERPLANE_HOST: 0.0.0.0" in compose
    assert "restart: always" in compose
    assert "/tmp:size=2g" in compose
    assert "gzip on;" in nginx
    assert "gzip_comp_level 6;" in nginx
    assert "location /assets/" in nginx
    assert "expires 30d;" in nginx
    assert 'Cache-Control "public, no-transform"' in nginx
    assert "max-age=63072000; includeSubDomains; preload" in nginx


def test_sqlite_retention_and_native_backup(tmp_path, monkeypatch):
    database = tmp_path / "paperplane.sqlite3"
    monkeypatch.setattr(persistence, "DATABASE", database)
    persistence.init_db()
    job_id, _ = persistence.create_job("compress", user_id=None, ttl=3600)
    persistence.update_job(job_id, status="completed")
    with sqlite3.connect(database) as connection:
        connection.execute("UPDATE jobs SET created_at = ? WHERE id = ?", (0, job_id))
        connection.commit()

    deleted = persistence.delete_expired_jobs(ttl_seconds=1)
    assert job_id in deleted
    compacted = persistence.compact_database()
    assert "freelist_before" in compacted

    from scripts.backup_db import backup_database

    backup = backup_database(tmp_path / "backups")
    assert backup.exists()
    with sqlite3.connect(backup) as connection:
        assert connection.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0


def test_deployment_and_ssl_scripts_are_idempotent_contracts():
    deploy = (ROOT / "scripts" / "deploy_production.py").read_text(encoding="utf-8")
    ssl_script = (ROOT / "scripts" / "provision_ssl.sh").read_text(encoding="utf-8")
    assert "--dry-run" in deploy
    assert "docker" in deploy
    assert "sitemap.xml" in deploy
    assert "/api/operations" in deploy
    assert "DOCX" in deploy
    assert "0 3 1 * *" in ssl_script
    assert "--renew-only" in ssl_script
    assert "certbot/certbot" in ssl_script
    assert "docker compose" in ssl_script


def test_linux_libreoffice_discovery_ignores_windows_host_override(monkeypatch):
    monkeypatch.setattr(converters.os, "name", "posix")
    monkeypatch.setitem(converters.os.environ, "LIBREOFFICE_EXECUTABLE", r"C:\\Program Files\\LibreOffice\\program\\soffice.exe")
    monkeypatch.setattr(converters.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)
    monkeypatch.setattr(converters.os.path, "isfile", lambda path: path == "/usr/bin/soffice")
    assert converters.find_libreoffice_executable() == "/usr/bin/soffice"
