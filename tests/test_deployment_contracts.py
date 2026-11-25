from __future__ import annotations

import json
import re
import sqlite3
import os
import subprocess
import sys
from pathlib import Path

import persistence
import converters


ROOT = Path(__file__).resolve().parents[1]


def test_deployment_guide_retention_and_health_example_match_runtime_contract():
    guide = (ROOT / "docs" / "DEPLOYMENT.md").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    ttl_match = re.search(r"^PAPERPLANE_JOB_TTL_SECONDS=(\d+)$", env_example, re.MULTILINE)
    health_match = re.search(r"# Expected JSON output:\s*# (\{[^\r\n]+\})", guide)
    assert ttl_match and health_match
    default_ttl_hours = int(ttl_match.group(1)) // 3600
    health_example = json.loads(health_match.group(1))
    assert health_example["job_ttl_hours"] == default_ttl_hours
    assert set(health_example) == {
        "status", "service", "version", "auth_required", "workers",
        "max_file_size_mb", "job_ttl_hours",
    }
    assert "PAPERPLANE_JOB_TTL_SECONDS=7200" in guide
    assert "PAPERPLANE_JOB_TTL_SECONDS=86400" not in guide


def test_docker_and_nginx_production_contracts():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "deploy" / "nginx.conf.template").read_text(encoding="utf-8")
    env_example = (ROOT / ".env.example").read_text(encoding="utf-8")
    assert "PAPERPLANE_ENV: production" in compose
    assert "PAPERPLANE_ALLOW_TEST_PAYMENTS=false" in env_example
    assert 'PAPERPLANE_ALLOW_TEST_PAYMENTS: "${PAPERPLANE_ALLOW_TEST_PAYMENTS:-false}"' in compose
    assert "PAPERPLANE_HOST: 0.0.0.0" in compose
    assert "restart: always" in compose
    assert "/tmp:size=2g" in compose
    assert "gzip on;" in nginx
    assert "gzip_comp_level 6;" in nginx
    # The HTTP body includes multipart framing in addition to the maximum PDF.
    assert "client_max_body_size 512m;" in nginx
    assert "location /assets/" in nginx
    assert "expires 30d;" in nginx
    assert 'Cache-Control "public, no-transform"' in nginx
    assert "max-age=63072000; includeSubDomains; preload" in nginx


def test_container_entrypoint_prepares_root_mounted_data_then_drops_to_nonroot():
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    entrypoint = (ROOT / "scripts" / "container_entrypoint.py").read_text(encoding="utf-8")
    assert 'ENTRYPOINT ["python", "scripts/container_entrypoint.py"]' in dockerfile
    assert "USER root" in dockerfile and 'useradd -m -u 1001' in dockerfile
    assert "followlinks=False" in entrypoint and "follow_symlinks=False" in entrypoint
    assert "_validate_mount_path" in entrypoint and "PROTECTED_ROOTS" in entrypoint
    assert "os.setgid(gid)" in entrypoint and "os.setuid(uid)" in entrypoint
    assert "os.execvp(command[0], command)" in entrypoint
    assert "PAPERPLANE_DATA_DIR" in entrypoint and "PAPERPLANE_BACKUP_DIR" in entrypoint


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


def test_parallel_worker_database_initialization_is_serialized(tmp_path):
    data_dir = tmp_path / "cold-start-data"
    data_dir.mkdir()
    environment = os.environ.copy()
    environment.update({
        "PAPERPLANE_SKIP_DOTENV": "1",
        "PAPERPLANE_ENV": "development",
        "PAPERPLANE_DATA_DIR": str(data_dir),
    })
    initializer = "import persistence; persistence.init_db(); print('initialized')"
    processes = [
        subprocess.Popen(
            [sys.executable, "-c", initializer],
            cwd=ROOT,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for _ in range(6)
    ]
    outcomes = [process.communicate(timeout=60) + (process.returncode,) for process in processes]
    assert all(code == 0 and "initialized" in stdout for stdout, stderr, code in outcomes), outcomes

    with sqlite3.connect(data_dir / "paperplane.sqlite3") as connection:
        table_names = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"users", "jobs", "user_feedbacks", "admin_sessions"} <= table_names


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


def test_github_deployment_waits_for_tests_and_pins_ssh_host_key():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    test_requirements = (ROOT / "requirements-test.txt").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "  verify:" in workflow
    assert "python -m pip install -r requirements-test.txt" in workflow
    assert "python -m pytest -q" in workflow
    assert "  deploy:\n    needs: verify" in workflow
    assert workflow.count("persist-credentials: false") == 2
    assert "appleboy/ssh-action@0ff4204d59e8e51228ff73bce53f80d53301dee2" in workflow
    assert "ORACLE_HOST_FINGERPRINT repository secret" in workflow
    assert "fingerprint: ${{ secrets.ORACLE_HOST_FINGERPRINT }}" in workflow
    assert "-r requirements.txt" in test_requirements
    assert "pytest" in test_requirements and "httpx2" in test_requirements


def test_deployment_dry_run_never_claims_live_signoff(tmp_path, monkeypatch, capsys):
    import json
    import sys
    import scripts.deploy_production as deploy

    monkeypatch.setattr(deploy, "REPORTS", tmp_path)
    monkeypatch.setattr(deploy, "effective_env", lambda: {
        "PAPERPLANE_ENV": "production",
        "PAPERPLANE_SESSION_SECRET": "s" * 48,
        "JWT_SECRET": "j" * 48,
        "PAPERPLANE_DOMAIN": "localhost",
    })
    monkeypatch.setattr(deploy, "docker_available", lambda: False)
    monkeypatch.setattr(deploy, "check_ports", lambda: ["port 80: available", "port 443: available"])
    monkeypatch.setattr(sys, "argv", ["deploy_production.py", "--dry-run"])

    assert deploy.main() == 0
    output = capsys.readouterr().out
    report = json.loads((tmp_path / "deployment_last_run.json").read_text(encoding="utf-8"))

    assert report["status"] == "preflight_passed"
    assert "DEPLOYMENT PREFLIGHT: PASS (dry-run only; deployment was not executed)" in output
    assert "PRODUCTION DEPLOYMENT AND SMOKE TESTS: PASS" not in output
    assert "Verified live URL:" not in output


def test_linux_libreoffice_discovery_ignores_windows_host_override(monkeypatch):
    monkeypatch.setattr(converters.os, "name", "posix")
    monkeypatch.setitem(converters.os.environ, "LIBREOFFICE_EXECUTABLE", r"C:\\Program Files\\LibreOffice\\program\\soffice.exe")
    monkeypatch.setattr(converters.shutil, "which", lambda name: "/usr/bin/soffice" if name == "soffice" else None)
    monkeypatch.setattr(converters.os.path, "isfile", lambda path: path == "/usr/bin/soffice")
    assert converters.find_libreoffice_executable() == "/usr/bin/soffice"


def test_paperplane_sqlite_and_backups_use_separate_named_persistent_volumes():
    compose = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")
    assert "PAPERPLANE_DATA_DIR: /data" in compose
    assert "- paperplane_data:/data" in compose
    assert "- paperplane_data:/data" in compose
    assert "- paperplane_backups:/backups" in compose
    assert "name: ${PAPERPLANE_DATA_VOLUME_NAME:-paperplane-pdf_paperplane_data}" in compose
    assert "name: ${PAPERPLANE_BACKUP_VOLUME_NAME:-paperplane-pdf_paperplane_backups}" in compose
    assert "PAPERPLANE_BACKUP_DIR: /backups" in compose
