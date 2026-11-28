# Paperplane v24–v30 Claims Audit (Phase -1 Part A)

Generated: 2026-11-28  
Working Branch: `main` (`ff48416cc17fd93c1663327b1096ca29fe7a8b99`, `"all done"`)  
Remote `origin/main` Head: `ff48416cc17fd93c1663327b1096ca29fe7a8b99`  

---

## 1. GitHub Parity, Served Live Asset Verification & Baseline Test Gate (`ff48416c`)

### Live (`https://paperplane.qd.je/`) vs Local `main` (`ff48416c`) HTTP Asset Verification
| Asset | Live Size (B) | Live MD5 (`https://paperplane.qd.je/assets/...`) | Local MD5 (`ff48416c`) | v30 FINAL Expected MD5 | Status |
|---|---:|---|---|---|---|
| `web/assets/app.js` | 521,790 | `439324828038c6ca641326bc69624913` | `439324828038c6ca641326bc69624913` | `439324828038c6ca641326bc69624913` | Byte-for-byte exact match |
| `web/assets/styles.css` | 327,256 | `993ee073796f8a9a818396a547a15496` | `993ee073796f8a9a818396a547a15496` | `993ee073796f8a9a818396a547a15496` | Byte-for-byte exact match |
| `web/assets/pdf_runtime.js` | 7,703 | `c0349257016382b81b469fc8101ad544` | `c0349257016382b81b469fc8101ad544` | `c0349257016382b81b469fc8101ad544` | Byte-for-byte exact match |

### Baseline Test Suite (`pytest -q`) on `ff48416c`
- Observed Run on `ff48416c`: `809 passed, 5 warnings, 4 subtests passed in 137.52s (0:02:17)` (`>=` v30 baseline `809`, floor `803`).

---

## 2. Verification of Key Prior Claims in `ff48416c` Codebase

| Area / Claimed Work | Verified Code Location (`ff48416c`) | Status in v30 FINAL Baseline |
|---|---|---|
| **Hammad's Plan prerequisite (`ID 203` both owners)** | `server.py:209-224` (`ADMIN_OWNER_EMAILS = {"mdhammad2906@gmail.com", "mdhammad29006@gmail.com"}`, `_require_admin`) | Preserved — must stay intact while adding `IDs 458–460` hierarchy |
| **Admin 24h Lockout & Pre-OTP Code Flow (`IDs 458–460` gap)** | `server.py:9727-9885` (`/api/admin/auth/status`, `step1`, `step2`, `sessions`); `persistence.py:1569-1725`; `web/assets/admin.js:169-492` | **Old design still active**: Step 1 asks Secret Key + Secret Code before OTP, triggers 24h lockout after 3 failures (`locked_until`), no `device_name` on `admin_sessions`, any admin can delete sessions |
| **User Session & OTP Verification (`IDs 452, 453, 455, 457`)** | `persistence.py:399-465`, `640-761`, `1090-1115`, `1226`; `server.py:552-655`, `3510-3837`, `4207-4246`, `4361-4495`; `web/assets/app.js:204-227`, `739-753`, `2834-2916`, `9935-10080`, `10543-10645` | **Open P0/P1 defects**: OTP resend & multi-tab/timeout races, no rolling session extension or expiry diagnostic, `COOKIE_SAMESITE` / cross-site billing return auth loss, `handleCashfreeReturn` lacks verifying-state & expiry display (`ID 456`), `setAuthenticatedWorkspaceUser` / `/api/ai/*` lack strict job-owner/client session-identity mismatch protection |
| **Cashfree Checkout & Pricing Fail-Closed (`ID 98`)** | `server.py:4253-4547`; `persistence.py:852-931`; `.env` key inspection | Fail-closed code present; live sandbox mode remains owner-gated until live PROD keys + ₹19 real test |
| **Admin Startup Fail-Closed (`ID 101`)** | `server.py:200-209` (`_required_admin_setting`); `scripts/prepare_admin_history_purge.py:1-100` | Code fails closed when unset; AWS rotation & public history purge remain owner-only |
| **Metadata Provenance (`ID 333` & `ID 415`)** | `web/assets/local_pdf_worker.js:30-38,278` (plus server `converters.py` metadata handlers) | Local worker copies `creator`/`creationDate` where supported; `notes_test.pdf` LaTeX/hyperref `Creator`/`CreationDate`/`Producer` loss & `pdf-lib` fallback need full audit + server/client hardening |
| **Studio Organizer, Modals, Redact & Flatten (`IDs 374, 375, 376, 427, 428, 433, 451, 454`)** | `web/assets/app.js:5225-5296` (Organizer drag), `web/index.html`, `web/assets/editor.js`, `web/assets/page_organizer.js`, `web/assets/optimization_engine.js`, `web/assets/security_forms.js` | Present with partial v29 patches; reopened/open defects (`451` annotation loss on reorder, `374` guest drag, `454` IndexedDB save warning, `375`/`376`/`427`/`428`/`433`) verified in Phase A pass |
| **Responsive Layout (`IDs 340, 341, 434`)** | `web/assets/styles.css:775-830`, `7343-7489`, `8125-8365`, `8927-8965`, `10099` | Contested on narrow `<=900px` bottom bar vs primary CTAs (`340`), breadcrumb narrow wrapping (`341`), and `1366x768` topbar overlap (`434`) |
| **Email OTP Delivery (`ID 358` / `ID 420`)** | `email_service.py:37-185,187-392`; `server.py:2195-2208` (`deliver_otp_or_raise`) | Gmail authenticated SMTP fallback enabled; Email OTP live reliability verified on v249/v250 runs 1–2; Google consent name (`ID 424`) and provider migration (`ID 420`) remain owner-gated |
| **Persistent Storage & Billing Schema (`ID 93` / `ID 456`)** | `docker-compose.yml:30-85`; `persistence.py:93-157,897-925,1493-1509` | Persistent `paperplane_data` volume in compose; plan expiration (`subscription_expires_at`) stored in `users` table (`persistence.py:899,916-921`) but omitted from `/api/auth/me` (`server.py:4230-4245`), `/api/billing/status` (`server.py:4380-4392`), Settings UI, and missing user order history |
