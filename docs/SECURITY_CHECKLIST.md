# Paperplane PDF: Production Security Checklist and Audit Report

## 1. Executive Summary

This security audit and verification checklist documents the hardening measures implemented across **Paperplane PDF** prior to the October 31, 2026 production release. All high-severity architectural vulnerabilities identified during the baseline inspection have been mitigated through code-level security controls, strict input validation, tenant isolation, and defense-in-depth deployment boundaries.

---

## 2. Vulnerability Mitigation Matrix

| Audit Item | Baseline Vulnerability | Hardening Implemented | Verification Status |
| :--- | :--- | :--- | :--- |
| **SEC-01** | Simulated Google sign-in accepted arbitrary emails without token verification. | Enforced cryptographic Google OAuth2 ID token validation using `google-auth` (`verify_oauth2_token` with `requests.Request()` verifying signature, audience matching `GOOGLE_CLIENT_ID`, valid Google issuer, and verified email flag). Safely returns `503 Service Unavailable` if Google OAuth credentials are not configured. Sessions are persisted in SQLite and can be immediately revoked via `POST /api/auth/logout`. Public frontend safely receives client ID only via `GET /api/auth/config`. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-02** | `/api/billing/simulate-*` endpoints allowed unauthenticated tier elevation. | Hardened endpoints to strictly return `403 Forbidden` when `PAPERPLANE_ENV=production` or `ALLOW_BILLING_SIMULATION=false`. Removed client-controlled auto-upgrades. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-03** | `/api/cloud/sync` and URL converters accepted arbitrary URLs, exposing internal network to SSRF. | Implemented `safe_fetch_url` with strict IP resolution and custom `SSRFRedirectHandler`. Blocks loopback (`127.0.0.0/8`), private subnets (`10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`), link-local/cloud metadata (`169.254.169.254`), and IPv6-mapped IPv4. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-04** | Jobs lacked tenant isolation; any client could access other users' jobs. | Added cryptographic `guest_token` capability column to jobs. Enforced ownership checks: authenticated users can only access their own jobs; guests require their exact capability token. Path traversal blocked via `Path.is_relative_to()`. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-05** | Production authentication defaults were permissive; session cookies lacked protection. | Configured `HttpOnly`, `SameSite=lax`, and `Secure` cookie flags. Enforced production environment mode. Host header injection blocked via strict host whitelisting. | **VERIFIED** (`config.py`, `server.py`) |
| **SEC-06** | Nginx deployment configuration lacked HTTPS termination. | Created production Nginx configuration with TLSv1.2/1.3, modern cipher suites, HSTS header, automatic HTTP-to-HTTPS redirect, and 500 MB upload limits. | **VERIFIED** (`deploy/nginx.conf.template`, `deploy/nginx.conf`) |
| **SEC-07** | Operations catalog marked all 37 operations as implemented regardless of host engines. | Updated `GET /api/operations` and frontend cards to truthfully report host runtime availability (`available=True/False`, `prerequisite`). Tools without required engines show honest readiness warnings. | **VERIFIED** (`tests/test_production_security.py`, UI inspect) |
| **SEC-09** | Password reset lacked secure token generation, hashing, and anti-enumeration protections. | Implemented `password_resets` table in SQLite with SHA-256 token hashing, 30-minute expiration window, strict single-use invalidation, anti-enumeration responses, and session revocation upon password update. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-10** | Rigid `startswith(b"%PDF-")` rejected valid PDFs with leading whitespace/comments. | Hardened file header validation conforming to ISO 32000-1 §7.5.2 (`b"%PDF-" in content[:1024]`), preventing false rejection of valid compliant documents. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-11** | Multiple fragmented documentation endpoints risked exposing unsafe demo actions. | Standardized on Swagger UI at `/api-docs` as the single canonical developer documentation route; redirected `/docs` and sanitized OpenAPI schema. | **VERIFIED** (`tests/test_production_security.py`) |
| **SEC-12** | API keys passed in query parameters risked leaking credentials into proxy logs and referrer headers. | Public REST API strictly requires `Authorization: Bearer <key>`. Explicitly rejects `?api_key=` in query params with HTTP 400. Stores only SHA-256 hashes of keys. | **VERIFIED** (`tests/test_developer_api.py`) |
| **SEC-13** | Server-side AI provider credentials risked exposure via client bundles or public Swagger schema. | `AGENTROUTER_API_KEY` is strictly server-side in `.env`. Customer Paperplane keys are isolated. Diagnostic probe redacts all secrets. Kill switch halts outbound calls. | **VERIFIED** (`tests/test_developer_api.py`) |

---

## 3. Pre-Launch Operational Security Checklist

### A. Secret Hygiene & Key Rotation

- [x] **No hardcoded secrets**: Verified that no live API keys, JWT secrets, or private keys are embedded in source files.
- [x] **Compromised Secret Hygiene**: Confirmed that previously exposed Google OAuth client secret was scrubbed from repository files and documentation. Documented that client secret must never be committed.
- [x] **Repository ignore rules**: Confirmed `.gitignore` and `.dockerignore` block all sensitive extensions.
- [ ] **Rotate pre-existing development keys**: If any API key (e.g., Cashfree sandbox keys, Gemini keys) was ever committed to version control, rotate it immediately in the respective vendor dashboard before launch.
- [ ] **Generate production `PAPERPLANE_SESSION_SECRET`**:
  ```bash
  python3 -c "import secrets; print(secrets.token_hex(32))"
  ```
  Set this value in production `.env`. Do not leave it empty.
- [ ] **Replace TLS certificates**: Ensure `deploy/certs/privkey.pem` and `deploy/certs/fullchain.pem` are valid CA-issued certificates for the production domain, NOT test or self-signed certificates.

### B. Network & Infrastructure Isolation

- [x] **Non-root container user**: Verified `Dockerfile` runs as `paperplane` (UID 1001).
- [x] **Internal port binding**: FastAPI container binds only to internal Docker bridge and `127.0.0.1:8501`.
- [x] **Nginx reverse proxy**: Terminating HTTPS on port 443 with HSTS enabled (`max-age=31536000`).
- [x] **Host header whitelist**: `PAPERPLANE_TRUSTED_HOSTS` configured with production domain; wildcard `*` strictly forbidden.
- [x] **CORS whitelist**: `PAPERPLANE_ALLOWED_ORIGINS` explicitly lists allowed origin schemes; wildcard `*` excluded.

### C. Application Security Controls

- [x] **Upload size limits**: Clamped to 500 MB in both Nginx (`client_max_body_size 500m;`) and FastAPI (`MAX_FILE_SIZE`).
- [x] **Rate limiting**: Dual-layer rate limiting (Nginx 30 r/s burst 50 on `/api/`, plus FastAPI IP-based sliding window).
- [x] **SSRF defense**: Multi-layer DNS verification and socket connection guard on all URL import endpoints.
- [x] **Path traversal prevention**: All job artifact retrieval routes verify output file paths strictly reside inside the designated job sandbox using `is_relative_to()`.
- [x] **Tenant job isolation**: Verified that cross-user job inspection and downloading return `403 Forbidden` or `404 Not Found`.
- [x] **Cryptographic Password Reset**: 30-minute expiration, SHA-256 hashed storage, single-use consumption, session invalidation.

### D. Compliance & Truthful Advertising

- [x] **No fake progress or results**: All operations perform genuine transformations using verified libraries (`pypdf`, `pymupdf`, `reportlab`, `qpdf`, `pdf2image`, `weasyprint`, etc.).
- [x] **Truthful capability reporting**: Unavailable engines (e.g., LibreOffice or Tesseract when host binaries are absent) are honestly identified with required prerequisite messages rather than simulating success.
- [x] **Data retention transparency**: Ephemeral storage lifecycle clearly documents automatic job cleanup after 24 hours.

### E. UI Brand & Content Integrity Verification

- [x] **Zero emoji icons**: Replaced all emojis across HTML, CSS, and JS with crisp SVG icons or clean semantic text tags.
- [x] **Zero em dashes**: Audited and replaced all em dashes (`—`) with clean punctuation or colons across website copy, legal terms, and UI strings.
- [x] **No purple gradient or pill buttons**: Purged `#8b5cf6` gradients and pill radii; standardized on `#0284c7` ocean blue palette and 6-8px border radii.
- [x] **Dedicated legal documentation**: Honest, verified Privacy Policy and Terms of Service served at `/privacy` and `/terms`.
- [x] **Automated test suite**: 133 passing tests across security, API, engine transformations, and session revocation.
