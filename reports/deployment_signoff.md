# Production Deployment Sign-off

Date: October 25, 2026

## Implementation status

| Area | Status | Evidence |
| --- | --- | --- |
| Windows/Linux LibreOffice discovery | PASS | `converters.find_libreoffice_executable()` prioritizes POSIX PATH and `/usr/bin` and ignores Windows drive-letter overrides on POSIX. |
| Docker production environment | PASS | `docker-compose.yml` enforces `PAPERPLANE_ENV=production`, `PAPERPLANE_HOST=0.0.0.0`, `restart: always`, and `/tmp` tmpfs. |
| Nginx compression and caching | PASS | Gzip level 6, text/JSON/JS/SVG MIME types, 30-day `/assets/` caching, and security headers are in `deploy/nginx.conf.template`. |
| SSL automation | PASS | `scripts/provision_ssl.sh` validates DNS, provisions Certbot webroot certificates, copies them into `deploy/certs/`, installs `0 3 1 * *` renewal, and gracefully reloads Nginx. |
| SQLite WAL backup | PASS | `scripts/backup_db.py` uses SQLite's native `Connection.backup()` API and atomic replacement; `paperplane-backup` runs every 24 hours in Compose. |
| Cleanup and compaction | PASS | Completed/failed job retention and `PRAGMA incremental_vacuum` run from the 24-hour cleanup worker. |
| One-click deployment | PASS | `scripts/deploy_production.py` and `scripts/deploy_production.sh` validate, build, launch, and smoke-test the production flow. |

## Verification results

- `python -m pytest -q`: **170 passed, 1 warning**
- `python scripts/preflight_test.py`: **36/36 checks passed**
- `pytest tests/test_web_seo.py -q`: **10 passed, 1 warning**
- `python scripts/deploy_production.py --dry-run`: **PASS**
- `docker compose -f docker-compose.yml config --quiet`: **PASS**
- Python syntax checks for changed Python modules: **PASS**
- `bash -n scripts/provision_ssl.sh`: **PASS**
- `bash -n scripts/deploy_production.sh`: **PASS**

## Nginx validation and benchmark gate

The requested Docker-based Nginx syntax check was attempted with:

```text
docker run --rm ... nginx:1.27-alpine nginx -t
```

It could not execute in this Windows workspace because Docker Desktop's Linux
engine was not running (`dockerDesktopLinuxEngine` named pipe unavailable). Nginx
is not installed locally, so no genuine Nginx throughput/FCP benchmark was
claimed. The deployment dry-run still rendered the production template and
verified the command that will run `nginx -t` on the deployment host.

The authoritative Nginx benchmark must be run after Docker Engine is started on
the production host. Recommended command:

```bash
docker run --rm --add-host paperplane:127.0.0.1 \
  -v "$PWD/deploy/nginx.conf:/etc/nginx/conf.d/default.conf:ro" \
  -v "$PWD/deploy/certs:/etc/nginx/certs:ro" \
  -v "$PWD/deploy/acme:/var/www/certbot:ro" \
  nginx:1.27-alpine nginx -t
```

## Sign-off

**Application and deployment automation: READY.**

**Infrastructure execution: BLOCKED only by the local Docker Desktop daemon not
running and the absence of a real production DNS domain/certificate authority
environment.** No deployment was attempted against an external host.

Machine-readable dry-run output: `reports/deployment_last_run.json`.
