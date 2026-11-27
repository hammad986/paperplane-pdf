# Paperplane v24 / v25 / v241 / v242 Claims Audit (Phase -1 Part A)

Generated: 2026-11-26  
Working Branch: `main` (`a972f56`)  
Remote `origin/main` Head: `ca5d4e60` (`https://github.com/hammad986/paperplane-pdf.git`)

---

## 1. Git, Served Live Build & Baseline Suite Gate Status

### Git Push Attempt (`origin/main`)
- Local `main` contains commits `e33e66a` (`v241`), `6e45a42`, and `a972f56` (`v242`) directly ahead of `origin/main` (`ca5d4e60`).
- Running `GIT_TERMINAL_PROMPT=0 git push origin main` exited with:
  `fatal: could not read Username for 'https://github.com': terminal prompts disabled`
- Because HTTPS push credentials / PAT / SSH deploy key for `github.com/hammad986/paperplane-pdf.git` are not configured in this Linux container, **pushing to GitHub `origin/main` is currently blocked on repository push credentials**. All v241/v242 changes ARE present in our local `main` working tree and deployed live on EC2.

### Served HTTP Verification (`https://paperplane.qd.je/`) vs Local `main` (`a972f56`)
| Asset | Live Size (bytes) | Live MD5 | Local `main` (`a972f56`) Match |
|---|---:|---|---|
| `web/assets/app.js` (`/assets/app.js?v=242`) | 485,007 | `4e2a3671c56609d7fd2ba67e988d3018` | Exact match |
| `web/assets/styles.css` (`/assets/styles.css?v=93`) | 318,327 | `1edba3ef713f0fc99c6bc49696e13997` | Exact match |
| `web/assets/pdf_runtime.js` (`/assets/pdf_runtime.js?v=27`) | 7,172 | `542629a3234f19f52f134ffad3454560` | Exact match |
| `web/assets/feedback.js` (`/assets/feedback.js?v=21`) | 19,888 | `4c0246d4b10d14a3292a92425801f9a0` | Exact match |

### Baseline Test Suite (`pytest -q` twice) & Legacy Scan on `a972f56`
- **Run 1 (`pytest -q`):** `761 passed, 5 warnings, 4 subtests passed in 122.90s (0:02:02)`
- **Run 2 (`pytest -q`):** `761 passed, 5 warnings, 4 subtests passed in 175.16s (0:02:55)`
- **`npx -y modern-web-guidance@latest legacy-scan`:** `0 findings from 38 qualified guides.`
- Note: These two 761-test runs verify the exact `v242` working tree on local `main` (`a972f56`). They supersede the older `ca5d4e60` `755` gate locally, while the GitHub remote `origin/main` still sits at `ca5d4e60` pending push.

---

## 2. Files Changed in `v241 + v242` (`ca5d4e60..a972f56`)
1. `email_service.py`: Added `_has_authenticated_mailbox_smtp()` (`email_service.py:44,120,159`) and normalized `SMTP_FROM_EMAIL` (`email_service.py:24`) so authenticated Gmail SMTP is allowed alongside Resend/custom relays.
2. `persistence.py`: Updated `create_google_session` (`persistence.py:448-461`) to stamp `last_seen_at` on Google login.
3. `server.py`: Added Google OAuth2 authorization-code exchange `_exchange_google_auth_code` (`server.py:3682,3750`), `/api/auth/google` code flow (`server.py:3727`), `google_code_flow_enabled` on `/api/auth/config` (`server.py:3777-3782`), and OTP resend hardening (`server.py:3638`).
4. `ai_engine.py`: Cached repeated source segment translations (`ai_engine.py:2623-2638`), skipped bounded repair loops when all initial batches fail with HTTP 429 (`ai_engine.py:2666,2676`), and added `_translation_block_styles` (`ai_engine.py:2554`) + `_translation_block_rotations(..., text_dict=...)` (`ai_engine.py:2528`).
5. `web/assets/app.js`: Rewrote Google login UI (`renderGoogleFallbackButton` `app.js:9110`, `completeGoogleAuthPayload` `app.js:9128`, synchronous `googleCodeClient.requestCode()` `app.js:9170-9209`, `startGoogleSignIn` `app.js:9184`, `8000` ms SDK timeout), added AI greeting filtering (`renderAiConversation` `app.js:618-629`, `updateAiDocBar` `app.js:7838`), hid generic `#result-view-studio-btn` on rich AI results (`app.js:6338`), relocated Settings sign-out handler cleanly to `#settings-signout-btn` (`app.js:9305`), and preserved existing guest API keys guard.
6. `web/assets/styles.css`: Added `#topbar-username` truncation (`styles.css:935,7365,7466`), `1361–1520px` topbar breakpoint (`styles.css:8188`), mobile Studio dock zoom-slot compacting (`styles.css:10025-10030`), and compact mobile photo tool spacing.
7. `web/assets/feedback.js`: Made feedback popover immediately opaque/high-z-index/scrollable (`feedback.js:121,175,180,335`).
8. `web/index.html` & `web/assets/service-worker.js`: Updated asset query versions (`v=242` `index.html:3484`, `v=93` `index.html:17`, `v=21` `index.html:3480,3486`, `paperplane-shell-v219` `service-worker.js:1`) and `.settings-password-card` markup.
9. Test files updated in `e33e66a..a972f56`: `tests/test_ai_workflows.py`, `tests/test_email_and_waitlist.py`, `tests/test_frontend_contracts.py`, `tests/test_launch_audit_v23.py`, `tests/test_production_security.py`.

---

## 3. Claim-by-Claim Code Verification (`v24` / `v25` / `v241` / `v242`)

| Item ID | Claimed Work (`v24`/`v25`/`v241`/`v242`) | Code Reality (`file:line`) | Audit Verdict |
|---:|---|---|---|
| **317** | Protect output downloadable & encrypted | `server.py:6300` (`/api/studio/security/protect`), `security_forms_engine.py:795` (`protect_pdf`), `server.py:2989` (`/api/jobs` worker path) | **Found + Live-Verified (v241 2x)** — Do not regress |
| **318** | Sign PDF download delivers signed file | `security_forms_engine.py:414` (`add_visual_signature`), `server.py:6187` (`/api/studio/sign/visual`), `app.js` sign workflow | **Found + Live-Verified (11x)** — Do not regress |
| **361** | Studio More Tools dropdown reachable (7 items) & toggles closed | `web/index.html:554` (`#studio-more-dropdown`), `web/assets/app.js:4241` | **Found + Live-Verified (v239/v241 3x)** — Do not regress |
| **373** | Studio OffscreenCanvas renders embedded fonts (no tofu boxes) | `web/assets/studio_render_worker.js:56` (`glyph` path), `studio_render_worker.js:1-12` | **Found + Live-Verified (v239/v241 3x + R16)** — Do not regress |
| **401** | Studio top toolbar no longer overlaps Pages panel header | `web/assets/styles.css:1972,4899-4920,10077` | **Found + Live-Verified (v241 2x at 1919px)** — Do not regress |
| **358** | Sign-in Email OTP + Google OAuth2 code flow + Settings sign-out | `email_service.py:44,187,445`; `server.py:3638,3727`; `persistence.py:448`; `app.js:9110,9184,9292,9305` | **Email Found + Live-Verified (4x on v241/v242)**; Google flow rewritten & opens real OAuth (`ID 424` GCP app name `"qd.je"` pending owner) |
| **369** | Filter stale AI greeting messages when no document loaded | `app.js:618-629` (`renderAiConversation`), `app.js:7838` (`updateAiDocBar`) | **Found in code — Live FAILED (v241 & R16)** — IndexedDB/restored stale doc (`arXiv 1706.03762`, `89-summary24.pdf`) still loads as ready in fresh/guest sessions (needs Phase 1 fix + ID 416) |
| **207** | Chunked 60 MB upload & XHR progress bar | `server.py:126,6823`; `app.js:1128-1153` (`onUploadProgress`) | **Found + Live-Verified (v18/v20/v22)** — Do not regress |
| **3** | Studio page deletion persists across reload & 30s | `web/assets/page_organizer.js:545,1393`; `web/assets/app.js:149,3183` (IndexedDB storage) | **Found + Live-Verified (v16–v22)** — Do not regress |
| **49** | Studio Export retries dropped fetch / 503 & exports clean PDF | `web/assets/editor.js:1798-1864` (`exportPDF`, retries `1831-1837`) | **Found + Verified 3x live (v18/v20/v22)** — Keep open pending owner confirm |
| **184** | Per-device guest quota signed cookie isolation | `server.py:487` (`paperplane_guest_quota`); `persistence.py:1000,1316`; `tests/test_guest_quota_v18.py` | **Found + Live-Verified (R11)** — Quota isolation holds; display counter (`ID 352`) still broken (`0/10`) |
| **240** | Sign PDF visual stamp in text layer | `security_forms_engine.py:414` (`add_visual_signature`) | **Found + Live-Verified (R11 + v26)** — Do not regress |
| **283** | Compress preserves images on both presets | `converters.py:2037-2046` (`_prefer_smaller_compression_source`, `compress_pdf`) | **Found + Live-Verified (v22 + R13)** — Do not regress |
| **220** | PDF/A-1b output with sRGB ICC Profile & Ghostscript | `converters.py:1537-1582` (`_find_srgb_icc_profile`, `pdf_to_pdfa`) | **Found + Live-Verified (v22 + v24 veraPDF 129/129 rules)** — Do not regress |
| **241** | Add Page Numbers renders `Page n of total` | `converters.py:1159,1286` (page number formatter in `converters.py`) | **Found + Live-Verified (v22 + R13)** — Do not regress |
| **309** | Scan to PDF A4 / Letter / 200 DPI physical dimensions | `converters.py:2469` (`scan_to_pdf`) | **Found + Live-Verified (v22)** — Do not regress |
| **299** | `/api/billing/status` hides `cashfree_order_id` & secrets | `server.py:4160-4191` (`billing_status`) | **Found + Live-Verified (v22)** — Do not regress |
| **246** | Security headers (CSP) & `server_tokens off` | `deploy/nginx.conf.template:2,73,92` | **Found + Live-Verified (v22 + R16)** — Do not regress (`connect-src` still needs `blob:` review for ID 342) |
| **293** | Flatten PDF form widgets + highlight annotations | `security_forms_engine.py:297` (`flatten_pdf_forms`) | **Partial**: widget removal verified live (v26 Fill->Flatten); highlight annotation bake-in & Studio cross-tool path still incomplete |
| **294** | 5 MB Compress/Watermark/Page Numbers completion | `watermark_job_worker.py`, `converters.py:2046`, `server.py:7067` | **Found + Live-Verified (v20)** — Do not regress |
| **295** | PDF to Word creates editable DOCX (not rasterized) | `converters.py:932-990` (`pdf_to_word`, `_sanitize_xml_text`) + `pdf_to_word_job_worker.py` | **Found + Live-Verified (v20)** — `ID 308` mixed-content/table disclosure in Phase 2 |
| **298** | Annotate PDF highlight persists with `/Contents` comment | `converters.py:2875` (`annotate_pdf`) | **Found + Live-Verified (v20 + v22)** — Do not regress |
| **343** | PDF to Word XML character sanitization on complex PDFs | `converters.py:932` (`_sanitize_xml_text`) | **Found + Live-Verified (R14 744 KB DOCX)** — Do not regress |
| **316** | PDF Metadata interactive viewer & JSON export | `web/assets/app.js:5906-5926` | **Found + Live-Verified (v24/v26)** — Do not regress |
| **337** | Resize PDF preserves aspect ratio (letterbox) | `converters.py:3347` (`resize_pdf_pages`) | **Found + Live-Verified (v24)** — Do not regress |
| **333** | Metadata provenance (preserve Creator + CreationDate) | `converters.py` metadata helpers | **Split / Reopened**: `test-text-10page.pdf` preserves metadata; `notes_test.pdf` / Merge / Split rewrite `Creator='pdf-lib'` (fix in Phase 1) |
| **1, 2, 314, 349, 394** | AI Translate (`translate_pdf_layout`) & Brief (`summarize_pdf`, `downloadSummaryPdf`) | `ai_engine.py:772,1139,1349,1693,2576`; `server.py:4675,4751`; `app.js:6364` | **Code partial / Still failing live**: 69p Translate hits 429/502; signed-in Brief hit HTTP/2 `400 0` / `Failed to fetch`; `downloadSummaryPdf` still falls back to `.txt` on non-WinAnsi chars; offline note strips trailing text |
| **4** | Cloud Import URL & Google Drive `/view` error handling | `server.py:6565` (`/api/cloud/sync`), `converters.py:305` (`safe_fetch_url`) | **Code working on PDFs (`W3C testfiles`, `arXiv`)**; owner Drive link returns `image/png` (owner input needed) |
| **101** | `_required_admin_setting()`, `.gitleaks.toml`, `.github/workflows/secrets.yml` | `server.py:200-211`; `.github/workflows/secrets.yml` | **Code guard verified (`test_101` passes)**; production credential rotation & git history purge remain owner-only |
| **93** | Persistent `/data` and `/backups` Docker volumes | `docker-compose.yml` (`paperplane_data`, `paperplane_backups`), `persistence.py:30` | **Compose volume confirmed mounted on EC2 (`paperplane-pdf_paperplane_data` -> `/data`)**; `paperplane-backup` shows `unhealthy` (`Dockerfile` healthcheck mismatch) + formal create->redeploy->login check due |
| **98** | Cashfree sandbox purchase & production fail-closed guard | `server.py:4062-4375`, `persistence.py`, `tests/test_cashfree_billing.py` | **Code + Sandbox live verified**; `CASHFREE_ENV=TEST` on EC2; `PROD` keys + ₹19 test owner-gated |
| **102** | Feedback write/read DB consistency | `server.py:9307,9380`; `persistence.py:1957-1997` | **Code & live DB verified (`v26 live retest test — please ignore` present in `/data/paperplane.sqlite3`, 19 rows)**; admin UI screenshot arrival proof in Phase 0 |
| **340, 341** | Mobile bottom bar clearance & breadcrumb shrinking | `web/assets/styles.css:775-817,8073-8105,10016-10020` | **Code present**; desktop breadcrumb PASS, narrow/scrolled tool buttons & `<=900px` checks being hardened in Phase 0 |
| **374, 375, 376, 406, 408, 409, 411** | Studio Organizer bar, Compress/OCR/Sign modals | `web/assets/page_organizer.js:1022,1308`; `web/assets/optimization_engine.js:155,223`; `web/assets/security_forms.js:27,521` | **Code partially patched in v24 — LIVE BROKEN**: `security_forms.js:546` & `optimization_engine.js:179,324` bypass `studioRequestError` causing `"[object Object]"` on HTTP 402; Organize bar & modal document carry-over fail on live paths (Phase 1) |
| **251** | Admin dashboard plan breakdown & totals | `web/assets/admin.js:409`, `server.py` admin stats | **Broken live (`9+2+1=12 of 13`, `student_pro` dropped, `16%` wrong)** — Phase 3 fix |
| **282** | Strip internal job counter prefix from filenames & UI | `server.py` job file naming & `web/assets/app.js` | **Client browser path clean (`v242`); server download/upload/compare/Studio restore still leak prefix live** — Phase 2 fix |
| **350–354, 381, 367** | Legal pages, limits table, op-counting, e-sign label, PWA copy | `web/index.html`, `server.py`, `web/assets/app.js` | **ID 367 wording partial live (`Native Apps Early Access`)**; `ID 352` counter stays `0/10` on live; `ID 381` pages still carry `DRAFT` banners (Phase 2b) |
| **386, 387, 388, 389, 390, 391, 392, 395, 396, 397, 398, 399, 400** | Staging QA + Round 14 v24 fixes (`app.js`, `converters.py`, `styles.css`, `server.py`) | Present in `ca5d4e60` (`web/assets/app.js`, `converters.py:428,2037`, `styles.css`) | **Found in local code & unit-tested**; require full live re-verification in Phase 2 + A–Z self-retest |
