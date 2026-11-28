452 items total confirmed = 449 items in Part 2 (elite list v30 FINAL r2: 300 open [12 P0, 98 P1, 190 P2], 132 verified_fixed, 15 to_verify, 2 not_tested; intentional unassigned gap IDs: 169, 179, 226, 238, 402-405) + 3 new v30 FINAL Hammad's Plan items (IDs 458-460: 3 P0 open) in Part 1 V30 FINAL MERGE = 452 total checklist items (303 open [15 P0, 98 P1, 190 P2], 132 verified_fixed, 15 to_verify, 2 not_tested); Phase A Launch Gate = 31 items (15 P0 + 4 new non-P0 gate items + 12 core broken-flow items).

# Paperplane v30 FINAL Reproduction Log (Phase -1 Part B)

Generated: 2026-11-28  
Baseline Under Test: `main` at `ff48416cc17fd93c1663327b1096ca29fe7a8b99`  
Baseline `pytest -q`: `809 passed, 5 warnings, 4 subtests passed in 137.52s`

---

## 1. Hammad's Plan — Admin Redesign (IDs 458–460, TOP PRIORITY)

### ID 458 (P0, Admin) — Active admin session list with device names & superadmin-only removal
- **Code Observation:**
  - `persistence.py:249-256`, `1682-1725`: `admin_sessions` schema has `(id, token_hash, email, client_ip, created_at, expires_at)` — no `device_name`, `user_agent`, or `last_active_at` columns.
  - `server.py:9867-9885`: `GET /api/admin/sessions` returns `row` without device/location formatting and labels all rows `"role": "superadmin"`; `DELETE /api/admin/sessions/{session_id}` allows ANY `ADMIN_OWNER_EMAILS` member (both `mdhammad2906@gmail.com` and `mdhammad29006@gmail.com`) to revoke another session.
  - `web/assets/admin.js:452-472`: `#sessions-tbody` renders `email`, `"Super admin"`, `created_at`, `expires_at`, and always renders a `"Log out"` button on non-current sessions regardless of whether the caller is `mdhammad2906@gmail.com` or `mdhammad29006@gmail.com`.
- **Plan:** Add `user_agent`, `device_name`, `last_active_at` to `admin_sessions`, touch `last_active_at` on verified requests, resolve approximate IP location via `_lookup_admin_location`, return explicit `role` (`superadmin` vs `admin`) + `can_revoke_sessions` flag, and enforce server-side (`403`) + UI hiding so ONLY `mdhammad2906@gmail.com` can revoke sessions while preserving both accounts' admin login access (`ID 203`).

### ID 459 (P0, Admin) — Remove 24-hour admin lockout; repeating 3-failure email verification OTP to `mdhammad2906@gmail.com`
- **Code Observation:**
  - `persistence.py:1569-1625`: `record_admin_failed_attempt` sets `locked_until = now + 86400` when `current_attempts >= 3`, and `get_admin_lockout_remaining` blocks all attempts with HTTP `423` for 24 hours.
  - `server.py:9258-9300`, `9727-9848`; `web/assets/admin.js:174-296`: Renders `#lockout-screen` (`"Admin Console Locked ... 24 Hours"`), `"before 24h lockout"`, and rejects requests with `423`.
- **Plan:** Remove all 24h lockout enforcement and `#lockout-screen` copy; track consecutive failures since last OTP verification in `admin_auth_attempts`; after 3 failures require an OTP dispatched specifically to `mdhammad2906@gmail.com`; verifying that OTP resets the 3-attempt budget cleanly so every subsequent 3 failures re-triggers email verification.

### ID 460 (P0, Admin) — Require Admin Secret Code AFTER OTP verification
- **Code Observation:**
  - `server.py:9737-9858`: Currently `/api/admin/auth/step1` asks `email + admin_key + admin_code` BEFORE sending OTP, and `/api/admin/auth/step2` asks ONLY `otp` + `challenge` and immediately mints the admin session without validating `admin_code` afterward.
  - Inline `/admin` HTML (`server.py:9273-9325`) + `web/assets/admin.js:209-302`: Puts Admin Secret Code input on Screen 1 instead of after OTP verification.
- **Plan:** Require Admin Secret Code entry & server-side verification AFTER OTP verification succeeds (never bypassing OTP or storing plaintext codes), ensuring valid OTP + wrong secret code is rejected and increments the 3-failure cycle toward re-verification.

---

## 2. Session, Auth & Billing Core Blockers (IDs 452, 453, 455, 456, 457)

### ID 452 (P0, Site/Auth) — Signed-in session dies after ~7 minutes
- **Code Observation (`persistence.py:399-465, 1090-1115, 1226`, `server.py:3522-4000`, `web/assets/app.js:2868-2916`):**
  - Check cookie attributes, sliding expiration, cross-request 401 clearing races, Nginx/timeout interactions during long AI calls (`AI_TRANSLATION_REQUEST_TIMEOUT_SECONDS = 300.0` vs client `checkAuthStatus()` 5s timeout + concurrent requests), and `AUTH_SYNC_KEY` / cookie max-age preservation so an active signed-in session reliably persists >= 60+ minutes through continuous multi-batch AI Translate/Summarize work.

### ID 453 (P1, Site/Auth) — Repeated sign-in 2FA OTP codes rejected
- **Code Observation (`persistence.py:640-761, 776-850`, `server.py:3582-3779`, `web/assets/app.js:9970-10080`):**
  - Trace `create_email_otp` -> `verify_email_otp`: check edge cases where double-submit, pending form vs JSON submit, whitespace/zero-padding, or `email_otp_resend_state` vs `require_otp` challenge overwrites can invalidate a freshly received code; keep strict attempt limits & cooldowns while making fresh valid 6-digit OTP entry deterministic across repeated logins.

### ID 455 (P0, Site) — Session flips to a different account mid-task
- **Code Observation (`server.py:532-625`, `4631-5162`, `web/assets/app.js:204-227, 739-753, 2834-2916`):**
  - Audit all places reading/caching user identity (`setAuthenticatedWorkspaceUser`, `authRequestVersion`, `state.user`, `state.billing`, `localWorkScope()`, and server job/AI endpoints). Bind AI/job initiation & status/download/UI updates strictly to the verified `user_id` of the session; invalidate/abort UI updates if an unexpected `user_id` mismatch occurs without silently inheriting another account's tier/email.

### ID 457 (P0, Site) — Session lost on Cashfree payment return (?billing=return)
- **Code Observation (`config.py:61-65`, `server.py:4434, 4469-4495`, `web/assets/app.js:10543-10645`):**
  - When Cashfree redirects cross-site back to `/?billing=return&order_id=...`, `COOKIE_SAMESITE` or startup `checkAuthStatus()` + `handleCashfreeReturn()` race can fail or trigger `401` modal (`safeFetch` `app.js:1245-1253`).
  - Furthermore, `app.js:10578` fires `void handleCashfreeReturn()` without displaying a visible `"Verifying payment…"` state when returning, and if `/api/billing/verify-order` hits `401` or `PENDING`, users see Guest/Auth modal instead of a clear verifying/success state with plan name + expiry.

### ID 456 (P1, Site) — Plan expiry shown nowhere + missing Order/Payment History
- **Code Observation (`persistence.py:852-925, 1023`, `server.py:4230-4246, 4380-4392`, `web/index.html:1750-1856`, `web/assets/app.js:2629-2750`):**
  - `subscription_expires_at` exists in SQLite `users` (`persistence.py:899, 916`) but `/api/auth/me` and `/api/billing/status` do NOT return `subscription_expires_at` or user order history. Neither `#pane-account` nor `#pane-billing` renders plan expiry date/time or an Order/Payment history list.

---

## 3. All Other Open P0s & Launch Gate Items (Summary)

| ID | Priority | Area | Root Cause / Status in `ff48416c` |
|---:|---|---|---|
| **1** | P0 | AI Translate | `ai_engine.py` synchronous 300s request (`server.py:4992-5028`) + 429 rate-limit repair storms + session drop (`452`). Needs resilient pacing, chunked/retry handling, zero mojibake for `es`/`hi`, 2x clean pass. |
| **2** | P0 | AI Summarize / Brief | `ai_engine.py` chunked summary timeout/429 fallback produces `Offline Analysis`; INR preservation (`ID 394`) & full coverage to verify (`_render_executive_brief_pdf` `server.py:5056` produces real PDF). |
| **4** | P0 | Cloud Import | Owner's Google Drive link returns `image/png` (owner-supplied link defect); inspect `/api/cloud/sync` error handling & public PDF URL reliability twice cleanly. |
| **93** | P0 | Infra / DB | `docker-compose.yml` mounts `/data`; inspect `paperplane-backup` healthcheck + formal create->restart->verify account survival test. |
| **98** | P0 | Billing | Cashfree `CASHFREE_ENV=TEST` (sandbox) in `.env`; **owner-only** PROD key swap & ₹19 real transaction. |
| **101** | P0 | Admin Security | `_required_admin_setting` fails closed at startup; **owner-only** AWS rotation & git `8dd50e6` purge. |
| **340** | P0 | Responsive UI | `.mobile-workspace-bar` at `<=900px` (`styles.css:8965`) vs `.main-area` bottom padding on tool & pricing views. |
| **341** | P0 | Responsive UI | `.breadcrumb-trail` wrapping/shrinking rules (`styles.css:775-830`, `8241-8295`) across 390/820/1366/1920px. |
| **358** | P0 | Sign-in | Email OTP works when SMTP/Resend creds valid; repeated OTP code failure (`453`), Google popup silent fail (`435`), and consent name (`424`, owner GCP). |
| **333** | P1 | PDF Metadata | LaTeX/hyperref `notes_test.pdf` loses `Creator`/`CreationDate`/`Producer` on client `pdf-lib` / server metadata edits. |
| **359/441** | P1 | AI Chat | Guest vs signed-in behavior discrepancy (`Page context: 1` vs full document & BM25 unrelated 429 fallback). |
| **369** | P1 | AI Restore | Stale document state vs clean Restore/Clear prompt on fresh session & post-login. |
| **374/451/454** | P1 | Studio Organizer/Save | Guest thumbnail drag silent fail (`374`), Organize reorder wiping unsaved annotations (`451`), spurious/failing IndexedDB save warning (`454`). |
| **375/376/427/428/433** | P1 | Studio Modals & Forms | Compress/OCR modal silent failures/hangs, Hardened Redaction dead/blank render, 3 hanging Studio scans, in-Studio Flatten Forms Bake not flattening. |
| **430/434/435** | P2/P1 | UX / Layout / OAuth | Compress uploads before quota check (`430`), `1366x768` topbar overlap (`434`), silent popup suppression fallback (`435`). |
| **New** | Feature | Settings -> Customer Support | Requested by owner (`28 Nov 2026`): solo-founder self-service troubleshooter + guided support ticket form + `/api/support` email/DB workflow. |
