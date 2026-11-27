416 items total confirmed = 403 items in Part 2 (289 open [10 P0, 95 P1, 184 P2], 15 to_verify, 2 not_tested, 97 verified_fixed) + 13 new Round 16 items (IDs 412-424: 5 P1, 8 P2) in Part 1; intentional unused gap IDs: 169, 179, 226, 238, 402-405.

# Paperplane v26.1 Reproduction Log (Phase -1 Part B)

Generated: 2026-11-26  
Baseline Under Test: `main` at `a972f56` (local `v242` code matching live `https://paperplane.qd.je/`)  
Suite Gate: `761 passed, 5 warnings, 4 subtests passed` twice (`122.90s`, `175.16s`); `legacy-scan`: `0 findings`.

---

## 1. Open P0 Launch Blockers (All 10 Reproduced / Root-Caused Before Edits)

### 1. ID 1 (P0, FLAKY) — AI Translate fails on 69-page files (`HTTP 429` / `502` / hangs)
- **Reproduction Steps:**
  1. Inspected live EC2 production logs (`paperplane-app` and `paperplane-pdf-nginx-1`, `2026-11-25 16:30–19:00 UTC`).
  2. Observed 10-page Spanish `POST /api/ai/translate` returning `200 OK` (`120,942` B at `16:48:28 UTC` and `120,850` B at `18:13:49 UTC`), whereas 69-page Spanish/Hindi logged:
     - `Translation batch failed language=es batch=1 block_ids=[0..13] reason=Translation provider failed (network timeout or connection error)`
     - `AI provider host=api.bluesminds.com attempt=1..4 timeout=20.6s HTTP=429`
     - `Translation repair failed language=es batch=1 block_ids=[10, 11]` & `[12, 13]` (`upstream HTTP 429`) -> Nginx returned `HTTP 429` (`17:19:54`) and `HTTP 502` (`17:23:43`).
- **Observed Code (`file:line`):**
  - `ai_engine.py:2377-2381` (`TRANSLATION_MAX_PARALLEL_BATCHES = 2`, `TRANSLATION_MAX_REPAIR_REQUESTS = 16`).
  - `ai_engine.py:2644-2720`: `translate_pdf_layout` fires parallel worker batches back-to-back with zero inter-batch pacing against `api.bluesminds.com` (`BLUESMINDS_MODEL=nvidia/nemotron-3.5-lightning-30b-a3b`). When some batches hit network timeout + others hit `429`, `all_rate_limited` (`ai_engine.py:2666`, added in `v241`) is `False` (because timeout != `"429"`), so `translate_pdf_layout` immediately fires up to 16 MORE repair requests against an already rate-limited endpoint!
  - `ai_engine.py:798`: `_provider_request` waits at most `(0.4, 2.0, 5.0)` seconds unless upstream sets `Retry-After` — way too short to recover from per-minute provider RPM/TPM limits.
  - `server.py:4751-4798`: `/api/ai/translate` is a single synchronous `POST` waiting up to `AI_TRANSLATION_REQUEST_TIMEOUT_SECONDS = 300.0` (`server.py:233`). Any proxy/idle timeout or long queue becomes `502` or browser `Failed to fetch`.
- **Planned Fix:**
  1. Add adaptive rate-limit cooldown + concurrency throttling (drop to serial pacing with explicit jittered backoff on first 429; abort repair amplification whenever ANY recent `429`/rate-limit window opens; configure smaller resilient batches with progress persistence & partial-fraction threshold `>= 0.50` / fail loudly if `< 50%` translated).
  2. Support asynchronous AI job execution + status polling (`/api/ai/jobs` + status poll used by UI while keeping `POST /api/ai/translate` synchronous-compatible for REST clients) so multi-minute 69-page translations never hit proxy connection timeouts or drop with `502`.
  3. Add Devanagari/Hindi Unicode output regression tests + controlled flaky 2-pass verification for both `es` and `hi` on small (10p) and large (69p) PDFs.

### 2. ID 4 (P0, FLAKY) — Cloud Import (`Drive /view` vs direct PDF URL)
- **Reproduction Steps:**
  1. Audited `server.py:6565-6670` (`cloud_sync`) and `converters.py:246-350` (`is_safe_url`, `safe_fetch_url`).
  2. Inspected handling of Google Drive URLs (`server.py:6585-6634`) and direct PDFs.
- **Observed Behavior:**
  - `server.py:6585` rewrites Drive `/view` links via `_drive_download_url` and `_confirm_drive_download`. When Drive serves an image or confirmation page without `%PDF-`, `server.py:6624-6629` explicitly rejects with `"Google Drive returned {media_type}, not a PDF..."` (matching live observation that the owner's previously shared Drive link literally serves `image/png`, whereas public PDFs like `https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf` and `https://arxiv.org/pdf/1706.03762` import cleanly).
  - Also noticed UX edge: `safe_fetch_url` (`converters.py:305`) / `cloud_sync` should harden redirects/Drive virus-scan HTML extraction (`confirm=...` / `uuid=...` modern Google Drive `drive.usercontent.google.com` download URLs!) AND surface exact actionable messages without generic failures.
- **Planned Fix:** Upgrade `_confirm_drive_download` (`server.py`) for modern `drive.usercontent.google.com` HTML confirmation forms (`id="download-form"` inputs), verify both direct + Drive `/view` paths in controlled two-round tests, and explicitly flag owner-supplied real PDF Drive link if `image/png` remains on the owner's URL.

### 3. ID 359 (P1, FLAKY — prioritized in Reproduction Log) — AI Chat `"Connection interrupted"` / HTTP 429
- **Reproduction Steps:**
  1. Inspected `ai_engine.py:772-925` (`_provider_request`), `ai_engine.py:1417` (`answer_pdf_question`), and `server.py:4429-4474` (`/api/ai/chat`, `/api/ai/chat/stream`).
- **Observed Code:** Chat calls `api.bluesminds.com` under short backoff `(0.4, 2.0, 5.0)`; streaming failures mid-stream or `429` bursts right after Translate/Brief tests surface `"Connection interrupted"` / `"AI service returned HTTP 429"`, and if no answer is produced, fail without grounded document-level fallback/retry clarity. (Also check `app.js` SSE stream parser for partial chunks & undefined `.text` read.)
- **Planned Fix:** Add rate-limit-aware retry/backoff + defensive SSE chunk error parsing (`no Cannot read properties of undefined`) + honest fallback/metadata awareness (`ID 286`/`ID 305`) + prove twice consecutively cleanly.

### 4. ID 358 (P0) — Sign-in (Email OTP & Google OAuth2)
- **Reproduction Steps & Code Check (`a972f56`):**
  1. Email OTP + Password Reset verified in code (`email_service.py:44` `_has_authenticated_mailbox_smtp`, `email_service.py:187` `send_otp_email`, `email_service.py:445` `send_password_reset_email`; `server.py:3638`). Live EC2 `v242` verified email OTP delivered via `smtp.gmail.com` and login accepted.
  2. Google OAuth2 code flow (`server.py:3682,3727`; `persistence.py:448`; `app.js:9110-9301`) opens real `accounts.google.com` OAuth consent screen (`ID 424` displays `"qd.je"` from GCP console).
  3. Residual code hardening checked: `app.js:2795` removed duplicate Settings sign-out listener in favor of `app.js:9305` (`#settings-signout-btn`); verify post-sign-out Settings modal state closes/clears stale user details immediately (`v26` P0 cosmetic finding), ensure cross-tab logout & auth error states (`ID 197`/`198`), and re-verify full signup, forgot/reset password, OTP expiry/lockout, and twice-consecutive OTP login on deployed build.

### 5. ID 101 (P0) — Admin Secret Code Exposure & Guards
- **Reproduction Steps & Code Check:**
  1. Ran `pytest -q tests/test_launch_audit_v13.py -k "test_101_admin_settings_required_at_startup"`: **passed**.
  2. Checked `server.py:200-225`: `_required_admin_setting("PAPERPLANE_ADMIN_KEY")` and `_required_admin_setting("PAPERPLANE_ADMIN_CODE")` fail closed at startup when missing (no hardcoded fallback).
  3. Checked `.github/workflows/secrets.yml`: Gitleaks CI scan configured (`--config=/repo/.gitleaks.toml`).
  4. **Blocker:** Production env values `PAPERPLANE_ADMIN_KEY` & `PAPERPLANE_ADMIN_CODE` on EC2 + public git commit `8dd50e6` history purge require **owner execution** (never invent/set production secrets automatically).

### 6. ID 2 (P0) + ID 314 (P1) + ID 349 / ID 394 (P1) — 69-page Executive Brief (`Failed to fetch`, `.txt` PDF download, duplication, INR currency)
- **Reproduction Steps (Controlled Local Run + Live Log Trace):**
  1. Live EC2 Nginx logs (`2026-11-25 18:10:29 & 18:10:32 UTC`) show `POST /api/ai/summarize` terminated with `499 0` then `400 0` directly at Nginx before reaching FastAPI -> browser `safeFetch` (`app.js:1159`) threw `"Connection error: Could not reach server. (Failed to fetch)"`.
  2. Ran local `ai_engine.summarize_pdf` on a 69-page PDF (`task-9981`) with provider unconfigured: returned `11,029` chars citing all `69` pages, **but** printed `"Local extractive notes from [Pages 1-12]:\nThis document was reviewed with deterministic local extraction..."` inside EVERY chunk section (`ai_engine.py:1769`)!
  3. Checked `app.js:6364-6399` (`downloadSummaryPdf`): encodes text ONLY via `pdf-lib` `StandardFonts.Helvetica` (WinAnsi). Any `₹`, `ﬁ`/`ﬀ`, em-dash, curly quote, or non-Latin1 character throws inside `try`, triggers `catch` (`app.js:6397`), and downloads a **`.txt` file** instead of `.pdf`!
  4. Checked `ai_engine.py:1359` (`_remove_unsupported_summary_currency`): checks numbers against truncated `source_text` (`1700` chars/page), causing `"INR 900000"` on dense pages to turn into `"currency unspecified"`.
- **Planned Fix:**
  1. Break chunk retry storm early when systematic failure occurs, run bounded parallel/async brief job (`/api/ai/jobs` or streaming keepalive) + in-memory `File` clone to prevent HTTP/2 `400 0`/`Failed to fetch`.
  2. Build real server-side/Unicode PDF generation endpoint `POST /api/ai/summarize/pdf` (PyMuPDF `insert_htmlbox` + embedded Unicode TTF `FreeSans`/`DejaVu`/`Noto Sans Devanagari`) AND browser WinAnsi-sanitizing PDF generator fallback so "Download PDF" ALWAYS downloads a valid `%PDF-` binary file (never `.txt`!).
  3. Clean duplicated chunk fallback boilerplates, preserve full-document currency verification & trailing page context (`ID 349`, `ID 394`).

### 7. ID 102 (P0) — Feedback Submit & Admin Arrival
- **Reproduction Steps & Code Check:**
  1. Inspected `server.py:9307-9385` (`/api/feedback` -> `add_user_feedback` `persistence.py:1957` and `/api/admin/feedback` -> `admin_get_feedbacks` `persistence.py:1984`). Both use `persistence.connect()` -> `DATABASE` (`Path(DATA_DIR)/paperplane.sqlite3`).
  2. Ran `pytest -q tests/test_launch_audit_v13.py -k "test_93_102_account_and_feedback_visible_after_process_restart"`: **passed**.
  3. Verified read-only on EC2 `/data/paperplane.sqlite3`: **`'v26 live retest test — please ignore'`** (plus `v25`, `v24`, `v23`, `v22`, `v20`, `v18`, `v16` test rows, 19 total rows) IS stored in `user_feedbacks` in the production SQLite DB.
- **Planned Fix:** Add explicit Admin UI / API E2E test confirming submitted feedback arrives in the admin Feedback tab without reload and verify visually on live deploy.

### 8. ID 98 (P0) — Cashfree Production Gate
- **Reproduction Steps & Code Check:**
  1. Inspected `server.py:4062-4375` (`create_checkout_session`, `verify_cashfree_order`, `cashfree_webhook`, `CASHFREE_ENV`). Verified EC2 `.env` has `CASHFREE_ENV=TEST`.
  2. Confirmed pricing UI matches INR-only one-time plans (`₹0 / ₹19 / ₹49 / ₹299`).
- **Planned Fix:** Keep `PROD` fail-closed guards intact, verify sandbox checkout end-to-end (never real money), check daily sandbox probe CI (`cashfree-sandbox-probe.yml`), and flag `CASHFREE_ENV=PROD` + real ₹19 payment test as owner-only final gate.

### 9. ID 93 (P0) — Redeploy Account / Data Persistence
- **Reproduction Steps & Code Check:**
  1. Verified EC2 `docker-compose.yml` mounts `paperplane-pdf_paperplane_data` -> `/data` (confirmed live via `docker inspect paperplane-app` `.Mounts`!).
  2. Noted `paperplane-backup` container shows `(unhealthy)` in `docker compose ps` (`10 days`) because `Dockerfile` `HEALTHCHECK` probes HTTP port `8501` while `paperplane-backup` runs `scripts/backup_db.py --daemon`.
- **Planned Fix:** Fix `paperplane-backup` compose healthcheck (or check daemon file freshness) so backup monitoring is healthy, verify Studio IndexedDB & user DB persistence cleanly across container recreate in isolated test and live deploy.

### 10. ID 340 (P0) & ID 341 (P0) — Mobile Bottom Bar Overlap (`<=900px`) & Breadcrumb Shrink (`P / W / A`)
- **Reproduction Steps (Local Playwright Chromium `task-9936` on `a972f56`):**
  1. Tested `/merge-pdf`, `/split-pdf`, `/compress-pdf`, `/pricing`, `/ai-intelligence` at `390x844`, `820x900`, `1024x768`, `1280x800` scrolled to bottom: empty forms showed `.mobile-workspace-bar` (`h=66`, `top=778`/`834`), `.breadcrumb-trail` at `1024x768` and `1280x800` showed `Paperplane (66px)` / `Workspace (66px)` / `AI Document Intelligence (144px)` unclipped (`styles.css:787-813`).
  2. **Gap Remaining to Verify & Harden:** Must test WITH files loaded + `#run-button` + result cards + `#pricing` CTA buttons across intermediate scroll offsets (not only bottom-of-page) at `390px`, `480px`, `600px`, `768px`, `820px`, `900px` exact (`<=900px` boundary), AND test `ID 341` on intermediate widths (`901px..1100px`) where `.breadcrumb-trail` shares header space with signed-in workspace pills and `#topbar-username`!

---

## 2. Newly Highlighted Round 16 / v26 Critical Defects Reproduced in Code

- **ID 411 (P1) — Studio Digital Signatures `"Digital signature error: Failed to fetch"`:**
  - Nginx live logs (`18:06:08` & `18:06:21 UTC` Nov 25) show signed-in `POST /api/studio/sign/digital` returned **`HTTP/2.0 400 0`** before reaching FastAPI (HTTP/2 request abort / mutated `File` descriptor or `proxy_request_buffering off`), while Guest run (`18:39:45` & `18:40:26`) returned **`402 244`** (`security_forms.js:544-548` bypassed `studioRequestError` at `security_forms.js:27-37`!).
- **ID 412 (P1) — Auth Dialog Terms/Privacy `href="#"`:** Found in `web/index.html:989-1055`.
- **ID 413 (P1) — Studio Thumbnail Rotation:** `web/assets/page_organizer.js` / `app.js` thumbnail renderer vs `/Rotate 90/180/270` canvas sizing.
- **ID 414 (P1) — `/compress-pdf-to-100kb` & `/compress-pdf-to-200kb` show Tool Directory:** `web/assets/app.js:10234` vs landing SEO route handling.
- **ID 415 (P1) — Placeholder defaults (`untitled` / `anonymous` / `unspecified`) written into files:** `converters.py` metadata & Markdown/Word converters.
- **ID 416 (P1) + ID 369 (P1) — Stale AI/Studio doc + chat history across Change PDF / fresh load:** `web/assets/app.js:618,7838` IndexedDB restoration & chat state.
- **ID 418 (P2) — Unknown routes return bare JSON `404`:** Missing HTML `404` handler for `Accept: text/html`.
- **ID 419 (P2) & ID 422 (P2) — Hidden `Paperplane Settings` is first `<h1>` & ghost `"U User Paperplane Settings"` in nav:** `web/index.html:230` and `1688`.
- **ID 421 (P2) — Pro card raw backticks around `` `sk_live_...` ``:** `web/index.html:1116,1392,1832`.
- **ID 423 (P2) — Silent guest `/dashboard` redirect to `/tool-desk`:** missing user message.

---

## 3. Do-Not-Regress Baseline Verification (`file:line` Confirmed in `a972f56`)

| ID | Status in v26 | Verified Code Location (`file:line`) | Action in This Round |
|---:|---|---|---|
| **318** | Verified Fixed (11x) | `security_forms_engine.py:414`, `server.py:6187` | Add regression test asserting output PDF contains signer text layer & opens valid |
| **317** | Verified Fixed (2x) | `security_forms_engine.py:795`, `server.py:6300` | Add regression test asserting encrypted AES-256 output (`needs_pass == True`) |
| **207** | Verified Fixed | `server.py:126,6823`, `app.js:1128` | Keep chunked upload & XHR progress bar intact |
| **3** | Verified Fixed | `page_organizer.js:1393`, `app.js:3183` | Keep IndexedDB save/restore & add persistence test |
| **49** | Open (3x clean, owner confirm) | `editor.js:1798-1864` | Keep retry + blob export working cleanly (do not close without owner Haan/Nahi) |
| **184** | Quota cookie Fixed | `server.py:487`, `tests/test_guest_quota_v18.py` | Preserve cookie isolation; fix counter display in `ID 352` |
| **240** | Verified Fixed | `security_forms_engine.py:414` | Assert signer name & timestamp in text layer |
| **283** | Verified Fixed | `converters.py:2037-2046` | Keep Under-100KB default + non-black image luminance regression test |
| **220** | Verified Fixed | `converters.py:1537-1582` | Keep sRGB ICC + Ghostscript PDF/A-1b valid |
| **241** | Verified Fixed | `converters.py:1159,1286` | Assert `Page 1 of N` formatted text |
| **309** | Verified Fixed | `converters.py:2469` | Keep A4 / Letter / 200-DPI point sizing |
| **299** | Verified Fixed | `server.py:4160-4191` | Assert no `cashfree_order_id` or env leak on billing status |
| **246** | Verified Fixed | `deploy/nginx.conf.template:2,73,92` | Preserve `server_tokens off` + CSP header |
| **343** | Verified Fixed | `converters.py:932` (`_sanitize_xml_text`) | Preserve XML control-char stripping on complex DOCX |
| **316** | Verified Fixed | `app.js:5906-5926` | Preserve metadata JSON viewer & export |
| **337** | Verified Fixed | `converters.py:3347` | Preserve aspect-ratio letterboxing |
| **333** | **Reopened in v25 / Split in v26** | `converters.py` metadata & `pdf-lib` paths | Reproduce `notes_test.pdf` Creator/CreationDate overwrite & fix across ALL pipelines |
