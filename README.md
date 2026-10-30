# Paperplane PDF

**Paperplane PDF** is a high-performance, privacy-first PDF utility and editing platform designed for effortless document workflows. Inspired by the simplicity and category-driven clarity of iLovePDF, Paperplane pairs clean 4-step tool workflows with an Advanced Studio for in-depth page management, content editing, form filling, and cryptographic document security.

---

## 🌟 Key Features

### 1. Category-Driven PDF Utility Hub
- **Organize PDF**: Merge PDFs, Split & Extract pages, Remove pages, Rotate, and Organize page order.
- **Optimize PDF**: Multi-level compression (Extreme, Recommended, Low), Flatten forms, and Repair corrupted PDFs.
- **Convert PDF**: JPG/PNG to PDF, PDF to Images, PDF to Text, PDF to Markdown, Office conversions (DOCX/PPTX/XLSX), and HTML to PDF.
- **Edit PDF**: Add text, shapes, highlight, crop margins, side-by-side text comparison, and permanent text redaction.
- **Sign & Protect**: Password protection (AES-256), Password removal, Visual signature stamps, and PKCS#7 digital certificate signing.
- **PDF Intelligence**: AI-powered document summarization, multi-lingual translation, and key insights.

### 2. Streamlined 4-Step Tool Workflows
Every core utility follows an intuitive workflow:
1. **Choose a Tool** from the homepage catalog or quick category filters.
2. **Drag & Drop** files with instant thumbnail preview and size validation.
3. **Configure Options** tailored strictly to the selected operation.
4. **Download** verified results immediately or proceed with "Process Another File".

### 3. Advanced Studio Workspace
For power users needing multi-modal interaction:
- Visual drag-and-drop page organizer.
- Interactive multi-layer PDF reader and editor.
- Visual AcroForm builder and field filler.
- Visual signature pad and certificate manager.

---

## 🛡️ Production Security & Architecture

Paperplane is built with defense-in-depth security principles:
- **Tenant & Job Isolation**: Authenticated jobs are strictly scoped to the owning account. Guest workflows utilize 256-bit unguessable cryptographic capability tokens.
- **SSRF Defense**: Strict multi-layer IP filtering and redirect inspection block loopback (`127.0.0.1`), private RFC-1918 subnets, and cloud metadata endpoints (`169.254.169.254`).
- **Path Traversal Containment**: All download operations enforce strict sandbox boundary checks via `Path.is_relative_to()`.
- **Truthful Capabilities**: Host dependencies (LibreOffice, Tesseract, Chromium, qpdf) are checked at runtime. Missing dependencies display honest badges instead of simulating false success.
- **Non-Root Execution**: Runs under a dedicated `paperplane` user (`UID 1001`) with read-only root and an isolated persistent `/data` volume.
- **Automated Ephemeral Lifecycle**: Input and output files expire and are automatically purged after 24 hours.

---

## 🚀 Quick Start (Local Development)

### Prerequisites
- Python 3.12+
- (Optional for full engine support) `tesseract-ocr`, `libreoffice`, `chromium`, `qpdf`, `ghostscript`

### 1. Install Dependencies
```bash
python -m pip install -r requirements.txt
python -m pip install -r requirements-dev.txt
```

### 2. Configure Environment
```bash
cp .env.example .env
```

### 3. Run the Development Server
```bash
python app.py
```
Open your browser to: **`http://127.0.0.1:8501`**

---

## 🐳 Production Deployment (Docker & Nginx HTTPS)

Paperplane includes a multi-stage production Docker setup with Nginx reverse proxy, modern TLS termination, and rate limiting.

### 1. Set Up Environment & Secrets
```bash
cp .env.example .env

# Generate a cryptographically secure session secret
python -c "import secrets; print(secrets.token_hex(32))"
```
Edit `.env` to set:
- `PAPERPLANE_ENV=production`
- `PAPERPLANE_DOMAIN=pdf.yourdomain.com`
- `PAPERPLANE_SESSION_SECRET=<generated_secret>`
- `PAPERPLANE_ALLOWED_ORIGINS=https://pdf.yourdomain.com`
- `PAPERPLANE_TRUSTED_HOSTS=pdf.yourdomain.com,paperplane,127.0.0.1`

### 2. Install TLS Certificates
Place valid CA certificates in `deploy/certs/`:
- `deploy/certs/fullchain.pem`
- `deploy/certs/privkey.pem`

### 3. Build & Launch
```bash
python scripts/deploy_production.py
# or from a Linux shell:
bash scripts/deploy_production.sh
```

The deployment suite validates production secrets and Docker Compose, checks the
Nginx template, builds and starts the stack, verifies `/health`, `/sitemap.xml`,
`/robots.txt`, and `/api/operations`, and runs an isolated DOCX-to-PDF smoke
conversion. Use `python scripts/deploy_production.py --dry-run` to inspect the
actions without changing Docker state.

To provision or renew Let's Encrypt certificates before the HTTPS stack starts:

```bash
PAPERPLANE_DOMAIN=pdf.yourdomain.com \
PAPERPLANE_CERTBOT_EMAIL=ops@yourdomain.com \
bash scripts/provision_ssl.sh
```

SQLite WAL hot backups run in the `paperplane-backup` Compose service. A one-off
backup can be created with `python scripts/backup_db.py`; backups are stored
under `/data/backups` and retained according to
`PAPERPLANE_BACKUP_RETENTION_DAYS`.

### 4. Health Check
```bash
curl -k https://127.0.0.1/api/health
```

For detailed deployment topologies, backup procedures, and rollback plans, see [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

---

## 💻 Public Developer REST API (v1)

Paperplane PDF provides a versioned, asynchronous REST API under `/api/v1` for integrating PDF processing into backend microservices, web apps, and automated pipelines.

### Free Daily Testing Sandbox
- **Allowance:** 10 free calls / day (up to 3 AI-assisted operations / day).
- **Payload Limit:** 10 MB per file.
- **Concurrency:** Up to 2 active processing jobs per account.
- **Schedule:** Resets daily at 00:00 UTC.
- **Authentication:** `Authorization: Bearer YOUR_PAPERPLANE_API_KEY` (Header-only; query parameters rejected with HTTP 400).
- **Idempotency:** Supports `Idempotency-Key` header to safely retry requests without double-charging quotas.

### Quick Example (Python)
```python
import requests

API_BASE = "http://127.0.0.1:8501/api/v1"
HEADERS = {"Authorization": "Bearer YOUR_PAPERPLANE_API_KEY"}

# Submit PDF compression job
with open("document.pdf", "rb") as f:
    resp = requests.post(
        f"{API_BASE}/jobs",
        headers={**HEADERS, "Idempotency-Key": "compress_001"},
        data={"operation": "compress"},
        files={"files": f}
    )
job_id = resp.json()["job_id"]
print(f"Queued job: {job_id}")
```
For complete documentation, see [`docs/API_GUIDE.md`](docs/API_GUIDE.md) and interactive Swagger UI at [`/api-docs`](http://127.0.0.1:8501/api-docs).

---

## 🤖 AI Document Intelligence (AgentRouter / Gemini)

Paperplane PDF integrates AgentRouter to power `gpt-6.1-sol` with resilient local fallback for:
- Executive document summarization (Executive Brief with Copy & Download)
- Smart structured metadata extraction (canonical typed schema for Invoices and Resumes, interactive modal with itemized line items, Developer JSON tab, and RFC-4180 CSV export)
- Document question answering with BM25 lexical keyword retrieval and verified page citations

See [`docs/AGENTROUTER_SETUP.md`](docs/AGENTROUTER_SETUP.md) for configuration details, live diagnostic probe instructions, and key whitelisting guide.

---

## 🧪 Testing & Verification

Run the automated test suite:

```bash
pytest -v
```

The test suite validates:
- **Core PDF engines**: merge, split, compress, watermark, page numbering, image conversions, redaction, forms, and signatures.
- **Security controls**: SSRF blocking, Google OAuth cryptographic ID token verification, session revocation, billing simulation restrictions, job capability tokens, path traversal protections, and ISO 32000-1 §7.5.2 PDF header validation.
- **Developer REST API v1**: API key lifecycle, header-based auth enforcement, query parameter key rejection (HTTP 400), account-level daily quotas (10 calls/day, 3 AI calls/day), 10 MB file ceiling, idempotency keys, tenant isolation, and direct AI endpoints.
- **Smart Metadata Extraction**: Ground truth invoice and resume extraction, typed canonical response contract, line items parsing, and RFC-4180 CSV generation.
- **Password reset lifecycle**: SHA-256 hashed token storage, 30-minute expiration window, single-use invalidation, anti-enumeration responses, and session revocation.
- **Truthful capabilities API**: runtime status reporting across all 37 catalog operations.
- **194 passed unit and integration tests (0 failures)**.

---

## Documentation Links

- [Master Feature Audit & Inventory](docs/MASTER_FEATURE_AUDIT.md)
- [Developer REST API Guide](docs/API_GUIDE.md)
- [AgentRouter AI Setup & Verification Report](docs/AGENTROUTER_SETUP.md)
- [Automated & Manual Test Release Evidence](docs/TEST_EVIDENCE.md)
- [UX Benchmark & iLovePDF Comparison Matrix](docs/UX_BENCHMARK.md)
- [Production Release Readiness Report](docs/RELEASE_READINESS.md)
- [Offline Desktop & Mobile Client Architecture](docs/OFFLINE_CLIENT_ARCHITECTURE.md)
- [Security Checklist & Audit Report](docs/SECURITY_CHECKLIST.md)
- [Production Deployment Guide](docs/DEPLOYMENT.md)
- [Google Sign-in Local Testing and Configuration Guide](docs/GOOGLE_OAUTH_LOCAL_TESTING.md)

---

## 📄 License
Proprietary & Confidential. All rights reserved.
