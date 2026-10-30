# Paperplane PDF: Production Deployment and Operations Guide

## 1. Overview & Architecture

Paperplane PDF is designed for containerized production deployment with defense-in-depth isolation, strict network boundaries, and ephemeral file processing.

```
                              [ Public Internet ]
                                       │
                                       ▼ HTTPS (Port 443)
                         ┌───────────────────────────┐
                         │    Nginx Reverse Proxy     │
                         │  - TLSv1.2 / TLSv1.3 Term │
                         │  - Rate Limiting (30 r/s) │
                         │  - Upload Limit (500 MB)  │
                         │  - HSTS & Security Headers│
                         └─────────────┬─────────────┘
                                       │ HTTP (Internal Docker Network)
                                       ▼ Port 8501
                         ┌───────────────────────────┐
                         │   Paperplane FastAPI App  │
                         │  - Non-root user (1001)   │
                         │  - SSRF-safe URL fetchers │
                         │  - Guest capability tokens│
                         │  - Ephemeral job cleanup  │
                         └─────────────┬─────────────┘
                                       │
                        ┌──────────────┴──────────────┐
                        ▼                             ▼
                 [ SQLite Database ]           [ Ephemeral Jobs ]
                 /data/paperplane.sqlite3      /data/jobs/<uuid>
```

---

## 2. Infrastructure Requirements

| Component | Minimum Specification | Recommended Production |
| :--- | :--- | :--- |
| **CPU** | 2 vCPUs | 4+ vCPUs (for parallel OCR and LibreOffice conversions) |
| **RAM** | 4 GB | 8 GB+ (accommodates Chromium and large PDF rendering) |
| **Disk** | 20 GB SSD | 50 GB+ SSD (persistent volume for database & active jobs) |
| **OS** | Linux (Ubuntu 22.04 LTS / Debian 12 / RHEL 9) with Docker & Docker Compose |
| **Network** | Ports 80 & 443 open to internet; port 8501 restricted to localhost/internal |

---

## 3. Pre-Deployment Configuration

### Step 1: Environment File Setup

Copy the production configuration template:

```bash
cp .env.example .env
chmod 600 .env
```

Generate a secure random 32-byte hexadecimal session secret:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Edit `.env` and configure:

```ini
PAPERPLANE_ENV=production
PAPERPLANE_DOMAIN=pdf.yourcompany.com
PAPERPLANE_SESSION_SECRET=<generated_32_byte_hex>
PAPERPLANE_REQUIRE_AUTH=false
PAPERPLANE_ALLOW_BILLING_SIMULATION=false
PAPERPLANE_SECURE_COOKIES=true
PAPERPLANE_COOKIE_SAMESITE=lax
PAPERPLANE_ALLOWED_ORIGINS=https://pdf.yourcompany.com
PAPERPLANE_TRUSTED_HOSTS=pdf.yourcompany.com,paperplane,127.0.0.1
PAPERPLANE_DATA_DIR=/data
PAPERPLANE_MAX_FILE_SIZE=524288000
PAPERPLANE_JOB_TTL_SECONDS=86400
```

> [!IMPORTANT]
> Never use wildcards (`*`) for `PAPERPLANE_ALLOWED_ORIGINS` or `PAPERPLANE_TRUSTED_HOSTS` in production. Always set `PAPERPLANE_ENV=production` to lock down billing simulation endpoints and enforce cookie security.

### Step 2: TLS/SSL Certificate Provisioning

Paperplane's Nginx configuration terminates TLS on port 443 and redirects port 80 to HTTPS.

1. Obtain valid certificates from a trusted Certificate Authority (e.g., Let's Encrypt / Certbot).
2. Place the certificate and private key in the `deploy/certs/` directory:
   - `deploy/certs/fullchain.pem`
   - `deploy/certs/privkey.pem`
3. Secure permissions:

```bash
chmod 600 deploy/certs/privkey.pem
chmod 644 deploy/certs/fullchain.pem
```

> [!WARNING]
> Do not use self-signed certificates or test keys in production. Browsers will reject them, and OAuth/secure cookies will fail.

---

## 4. Docker Deployment Workflow

### Build and Launch

Run the service using Docker Compose:

```bash
# Build the production image with all engines (LibreOffice, Tesseract, Chromium, qpdf)
docker compose build

# Launch in background with automated restarts
docker compose up -d
```

### Verify Service Health

Check container status and health checks:

```bash
docker compose ps
```

Verify backend health endpoint:

```bash
curl -k https://127.0.0.1/api/health
# Expected JSON output:
# {"status":"ok","version":"3.0.0","service":"paperplane-api","database":"connected","environment":"production"}
```

Inspect logs:

```bash
docker compose logs -f --tail=100
```

---

## 5. Security & Isolation Controls

1. **Non-Root Execution**: The backend container runs under the dedicated `paperplane` user (`UID 1001`, `GID 1001`). It has write access only to `/data` and `/tmp`.
2. **Reverse Proxy Enclosure**: The FastAPI application binds exclusively to the private Docker network and `127.0.0.1:8501`. Public traffic cannot bypass Nginx.
3. **Upload Constraints**: Enforced at both proxy (`client_max_body_size 500m;`) and application levels (`PAPERPLANE_MAX_FILE_SIZE=524288000`).
4. **SSRF Defenses**: Cloud-sync and URL-based imports use a strict socket resolver that rejects loopback (`127.0.0.0/8`), private networks (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local (`169.254.0.0/16`), cloud metadata endpoints (`169.254.169.254`, `metadata.google.internal`), and IPv6-mapped IPv4 addresses.
5. **Job Access Isolation**: Authenticated jobs are accessible only to their owning account. Guest jobs require a cryptographically random capability token (`guest_token`) set in an `HttpOnly` cookie or bearer authorization. Directory traversal is blocked via strict `is_relative_to(job_dir)` path containment.

---

## 6. Backup & Restore Procedures

### Database & Account State Backup

The application stores user accounts, API keys, subscription records, and job metadata in SQLite located at `/data/paperplane.sqlite3`.

To take an atomic, lock-free live backup:

```bash
# Atomic online backup using SQLite's online backup API via CLI
docker compose exec paperplane python -c "
import sqlite3
src = sqlite3.connect('/data/paperplane.sqlite3')
dst = sqlite3.connect('/data/paperplane_backup_$(date +%Y%m%d_%H%M%S).sqlite3')
src.backup(dst)
dst.close()
src.close()
print('Backup complete.')
"
```

Or backup the entire persistent Docker volume:

```bash
docker run --rm -v paperplane_data:/data -v $(pwd)/backups:/backup alpine \
  tar czf /backup/paperplane_data_$(date +%Y%m%d).tar.gz -C /data .
```

### Restore Procedure

To restore from a backup archive:

```bash
# 1. Stop the application
docker compose down

# 2. Restore volume contents
docker run --rm -v paperplane_data:/data -v $(pwd)/backups:/backup alpine \
  sh -c "rm -rf /data/* && tar xzf /backup/paperplane_data_<TIMESTAMP>.tar.gz -C /data"

# 3. Restart services
docker compose up -d
```

---

## 7. Rollback & Emergency Procedures

If a deployment failure occurs:

1. **Rollback Container Image**:
   ```bash
   docker compose down
   docker tag paperplane-pdf:previous paperplane-pdf:latest
   docker compose up -d
   ```
2. **Revert Configuration**:
   ```bash
   git checkout HEAD~1 -- docker-compose.yml deploy/
   docker compose up -d --force-recreate
   ```
3. **Emergency Job Dir Cleanup**:
   If disk usage spikes due to uncleaned abandoned jobs:
   ```bash
   docker compose exec paperplane python -c "
   from persistence import cleanup_expired_jobs
   cleaned = cleanup_expired_jobs(max_age_seconds=3600)
   print(f'Cleaned {cleaned} expired jobs.')
   "
   ```
