353 elite-list items confirmed in paperplane-codex-elite-prompt-v23.pdf (99 pages; v23 checklist canonical IDs 1–357 with intentional gaps).

# 2026-11-21 continuation — ID 122 OffscreenCanvas Studio renderer

- Real 69-page fixture: `C:/Users/mdham/Downloads/notes.pdf`, 5,456,746 bytes. Local Chromium mobile viewport 390×844, DPR 3, CPU throttled 4×. After the worker canvas shim and shared-session lifecycle fix, two rounds passed content-checked exports with exact page text/order, page 1 and page 40 thumbnails, selection/invert, navigation, slot recreation, no overflow, and zero page/console errors. The worker remained active and enabled in both runs. Readiness 13.86s/9.46s; max long tasks 428ms/616ms; <250ms threshold still fails. Evidence: `browser-id122-mobile-69page-studio-export_worker_canvas_shim_final_20261121.json`.
- Production-mode Docker image `paperplane-v23-audit:codex-v151-offscreen-canvas`, image ID `sha256:a9c519f3d3ead802020b401153fa9c3f5802b2a2e70a76d3c696cd2b7c312566`, healthy with four workers. Two browser runs kept the renderer active, preserved all 69 page texts/order, reported zero page/console errors, and yielded max tasks 879ms/533ms. Temporary container and tmpfs removed. Evidence: `docker-build-v151.log`, `docker-id122-v151-runtime.json`, `browser-id122-mobile-69page-studio-export_v151_docker_20261121.json`.
- First integration runs revealed worker fallback was hidden by passing browser checks; the renderer now exposes a failure reason and the browser harness rejects an inactive worker. Initial failure was PDF.js requesting a DOM canvas from a worker. Browser checks verified the OffscreenCanvas shim fixes this code path.
- Full pytest rerun after correcting two stale runtime-version assertions: 637 passed twice, four existing deprecation warnings per run. Logs: `pytest-current-v161-final-run1.log`, `pytest-current-v161-final-run2.log`.
- Classification: renderer worker fallback/shared-session lifecycle fixed locally; ID 122 remains PARTIAL for the long-task target and physical-device validation. Release verdict remains HOLD.
- Do-not-regress: current P0 round 105 completed 60/60 checks with zero page errors. Current local responsive matrix passed all 704 checks for 44 routes × 8 CSS widths × 2 rounds. Production Docker shell v85 cached and loaded app v145, CSS v61, organizer v20, PDF runtime v25, and Studio render worker v4 offline in two 390px rounds; both returned HTTP 200 with zero page errors. Evidence: `browser-p0-round105.json`, `browser-id27-narrow-zoom-layout.json`, `browser-v151-docker-offline-pwa.json`.

# 2026-11-21 continuation — ID 357 offline local PDF operation

- Before fix, two local Chromium rounds loaded the cached shell offline but local Merge could not load uncached PDF.js/PDF-lib assets; the UI prompted to upload selected files to the server. Instrumented requests recorded `/assets/pdf.min.js` and `/assets/pdf-lib.min.js` failing offline. No job POST occurred. Evidence: `browser-id357-offline-local-merge-repro-v85.json`.
- Added `/assets/pdf.min.js`, `/assets/pdf.worker.min.js`, and `/assets/pdf-lib.min.js` to the shell precache; local_pdf_worker was already present. Bumped the cache to `paperplane-shell-v86`.
- Two current-source offline Chromium rounds and two v152 production-Docker offline rounds each returned HTTP 200 for `/merge-pdf`, kept Local mode selected, downloaded a 961-byte 2-page PDF, preserved `OFFLINE-LOCAL-A` then `OFFLINE-LOCAL-B`, and made zero `/api/jobs` requests. All rounds had zero page errors. Container used synthetic secrets and tmpfs only, was stopped/removed, and no payment was made.
- The two Docker rounds also reopened the downloaded PDF in Studio while offline, rendered page 1, and confirmed the OffscreenCanvas worker stayed active and enabled with zero page errors.
- Evidence: `browser-id357-offline-local-merge.json`, `browser-v152-docker-offline-pwa.json`, `docker-v152-offline-runtime.json`, `docker-build-v152.log`; regression: `test_offline_shell_precaches_pdf_dependencies_for_browser_local_processing`.
- Full current-source suite after the shell-v86 change: 638 passed twice, four existing deprecation warnings each; logs `pytest-current-v162-run1.log` and `pytest-current-v162-run2.log`.

# 2026-11-20 continuation — ID 27 live/local drift

- Read-only live Chromium: all 44 operation routes × seven viewport widths × two rounds = 616 checks. At 1024px, `.workspace-tabs` overlaps `.topbar-right` on all 44 routes in both rounds (88 failed checks); assets served are app.js v91/styles.css v51. No page errors; other measured routes did not report layout failures. Evidence: `browser-id27-live-layout-2026-11-20.json`.
- Ran the matching local current-candidate Chromium regression at 1024px on all 44 routes twice. app.js v124/styles.css v56 passed 88/88, with no topbar overlap, horizontal overflow, or page errors. Evidence: `browser-id27-local-1024-regression.json`; runner: `browser_id27_local_1024_regression.py`.
- Interpretation: source-side responsive fix is verified locally; public deployment still serves the older asset set, so the live defect remains open until the user deploys and the same 1024px check is repeated.
- Verification: focused v23 tests passed 101/101, then the complete current pytest suite passed twice sequentially at 617/617 (145.92s and 151.18s; four existing deprecation warnings each). Logs: `pytest-id27-continuation-run1.log`, `pytest-id27-continuation-run2.log`.

## 2026-11-20 continuation — ID 28 isolated Watermark stress

- The diagnostic runner previously imported `server` before configuring a temp data directory, so configuration initialization could read the normal local data path. Moved the import inside the temporary workspace after setting `PAPERPLANE_DATA_DIR`; the rerun no longer emitted the stored-credential warning and did not inspect the default data directory.
- Two fresh runs each executed 40 concurrent 20-page Watermark conversions in five rounds of eight. All 40 jobs per run completed; every output retained all source page markers and its unique watermark. Maximum per-job times were 2.70s and 2.89s. Evidence: `id28-concurrent-watermark-stress.json` (latest run); runner: `repro_id28_concurrent_watermark.py`.
- The historical queued task stuck at 20% is still unexplained and not reproduced; ID 28 remains PARTIAL.

## 2026-11-20 continuation — ID 29 guest gate and same-session Unlock

- Fresh isolated current-source Chromium checked guest plan selection at desktop and 390px mobile. Both showed the account-required modal, sent zero `/api/billing/checkout-session` POSTs, and had zero page errors. Evidence: `browser-id29-current-guest-checkout-gate.json`; runner `browser_id29_current_guest_checkout_gate.py`.
- Two independent Chromium browser contexts received distinct signed guest quota cookies. Guest A submitted two local Merge jobs and got 2/2 completed with usage 2; guest B submitted one and got 1/1 completed with usage 1. No page errors. Evidence: `browser-id29-current-guest-quota-isolation.json`; runner `browser_id29_current_guest_quota_isolation.py`.
- Current-source Protect→Unlock was rerun twice. Both protected downloads were encrypted PDFs, the password/file handoff remained in the same page session, unlock returned HTTP 200, and the resulting unencrypted PDF retained its source marker. Evidence: `browser-id307-protect-unlock-same-session.json`.
- No real payment or production billing/TLS check was attempted; retain the production owner gate.

## 2026-11-20 continuation — ID 37 Grayscale browser workflow

- On current isolated local source, Chromium uploaded a colored two-page PDF through `/convert-pdf-to-grayscale` at 1366px and 390px, then downloaded the output in both runs. Both PDFs retained two pages; 345,600 output pixels per round had max R/G/B channel difference 0. Each round made one expected `/api/jobs` POST and had zero browser errors. Evidence: `browser-id37-current-grayscale.json`; runner `browser_id37_current_grayscale.py`.
- This adds current-source browser evidence for server processing only; it does not change the 25/41 browser-local coverage count.

## 2026-11-20 continuation — browser-local Grayscale and mobile drawer fix

- Added `grayscale` to browser-local supported operations. At 72 DPI the browser checks visible page pixels; already-gray input is returned byte-for-byte to preserve text. Colored pages render at 150 DPI, are converted with bounded row chunks and periodic main-thread yielding, then assembled into a raster-only PDF. Caps are 100 MiB input, 100 pages, 32M analysis/render pixels and 64 MiB encoded pages; encrypted, oversized or unsupported cases show the existing explicit server fallback.
- First Chromium output check caught that Canvas `filter` did not reliably grayscale PDF.js output. Replaced it with explicit per-pixel luminance conversion and reran. Two rounds (1366px/390px) each downloaded colored results with 345,600 pixels verified and channel difference 0; already-gray output matched input bytes and retained searchable markers. Zero `/api/jobs` calls and page errors; `browser-id37-local-grayscale.json`.
- The same mobile run found hamburger navigation only opened, never toggled closed; the remaining backdrop intercepted the result-download link. Changed it to open/close, and the two-round phone check now asserts backdrop hidden and `aria-expanded=false` before download.
- Asset cache versions advanced to app.js v126, worker v26, PDF runtime v23 and shell v59. Focused browser-path/contract tests and node syntax checks were rerun.

## 2026-11-20 — ID 27 current route-layout regression sweep

- Reran all 44 local operation routes in two Chromium rounds at 320, 390, 820, and 1366 CSS px (352 checks) against app.js v121/styles.css v56. All routes returned HTTP 200 with zero document/visible-content overflow and zero browser errors. ID 27 stays PARTIAL for missing owner M-1–M-11 screenshot comparison and physical-device/safe-area testing. Evidence: `browser-id27-current-source-scroll-guard-v56.json`.

## 2026-11-20 — ID 28 current-candidate Docker catalog

- Built image `paperplane-v23-audit:codex-v122-rootmargin0` (`sha256:490ce59bc87515f10fa72ccb81d75c112fa9ea84ca988736303def7fc8760e64`) and ran the full synthetic catalog in a disposable four-worker production-mode container with `/data` and `/tmp` on tmpfs, dummy-only local settings, and no provider credentials. Each Chromium round content-checked 41 workflows, blocked one SSRF probe, reported two provider-only operations unavailable, and had zero page errors. Watermark completed in 3.20s and 3.18s with valid content. Container was stopped/removed. The historic single Watermark job stuck at 20% for over seven minutes remains unexplained; ID 28 stays PARTIAL. Evidence: `browser-id28-v117-current-image-catalog-v122-rootmargin0.json`.

## 2026-11-20 — ID 122 strict-visibility thumbnail follow-up

- Compared two fresh baseline rounds on app.js v121/page_organizer.js v15 with two rounds after changing the thumbnail IntersectionObserver from 180px prefetch to a 0px root margin. On the real 69-page notes.pdf at 390×844/DPR 3 and 4× CPU slowdown, page-1 readiness changed from 11.97/8.98s to 8.74/7.72s; long tasks over 50ms changed 53/44 to 35/33, and maxima changed 946/964ms to 659/875ms. Every page marker/text/order, 69 organizer cards, page-1/page-40 thumbnails, selection and navigation checks, export, zero overflow and zero errors passed. The 250ms responsiveness target is still missed; leave ID 122 PARTIAL. A combined strict-visibility/DPR-1 control regressed first-page readiness to 11.01s/7.16s with maximum tasks of 804/510ms and fewer visible pixels (1,297 vs 2,110), so retain DPR 3; evidence: `browser-id122-mobile-69page-studio-perf-rootmargin0-dpr1.json`. Evidence: `browser-id122-mobile-69page-studio-perf-current1120.json`, `browser-id122-mobile-69page-studio-perf-rootmargin0.json`.
- Rebuilt production-mode image `paperplane-v23-audit:codex-v122-rootmargin0` (`sha256:490ce59bc87515f10fa72ccb81d75c112fa9ea84ca988736303def7fc8760e64`) in a disposable 4-worker container with synthetic local settings and tmpfs `/data` and `/tmp`. Two mobile Chromium 69-page exports preserved all page text/order in 9.90s/10.71s; 390px width, visible 1.5× canvas content and zero errors. Container was stopped and removed.
- Offline current-source shell v54 passed two rounds: app.js v121, styles.css v56 and page_organizer.js v16 were cached; offline reload returned HTTP 200 with CSS active and no errors (`browser-id357-service-worker-v54-offline-local.json`). Current P0 sweep passed 60/60. Full pytest passed twice, 613 tests each, four existing deprecation warnings (`pytest-id122-rootmargin0-run1.log`, `pytest-id122-rootmargin0-run2.log`).

## 2026-11-19 — live ID 1 provider stability rerun

- On `https://paperplane.qd.je/`, submitted only a generated 10-page synthetic PDF. Spanish round 1 returned HTTP 200 and downloaded a PDF with 10/10 translated phrases, 10/10 source page markers, and no source English. Spanish round 2 returned HTTP 504 with `Retry-After: 5` and no download.
- Hindi returned HTTP 422 in both rounds because 20% of blocks, segments, and source characters translated; no PDF was produced. All four requests had zero browser page errors.
- Keep ID 1 PARTIAL. The refreshed evidence overwrote the previous matrix at `browser-live-id1-translation-matrix.json`; runner log: `browser-id1-live-translation-continuation-2026-11-19.log`.

## 2026-11-19 — ID 28 current-image catalog continuation

- First container attempt failed because production correctly rejected an HTTP-only public-origin setting. Corrected the harness to use the synthetic HTTPS origin `https://paperplane.example.test`; no application change was needed.
- Started the digest-verified production candidate in a disposable four-worker container with tmpfs data and a synthetic account. Two full Chromium catalog rounds each content-checked 41 outputs; SSRF was refused, two provider-only operations were unavailable without credentials, and there were zero browser errors. Watermark passed both rounds.
- Container was stopped and removed. This does not explain or close the prior intermittent Watermark worker stall; ID 28 remains PARTIAL.
- Evidence: `browser-id28-v117-current-image-catalog-continuation-2026-11-19.json`, `docker-id28-v117-runtime-continuation-2026-11-19.json`, `browser-id28-current-image-continuation-continuation-2026-11-19.log`, `run_id28_current_image_continuation.py`.

## 2026-11-19 — ID 122 mobile raster profiling follow-up

- Real 69-page `notes.pdf`, Chromium 390×844/DPR 3, 4× CPU slowdown. Temporary single-worker mobile thumbnail rendering completed the full workflow and exact text/page-order export, but peak tasks remained 690ms/651ms and first-page readiness was 11.13s/12.75s. Rejected and reverted this candidate.
- Disabled-thumbnail raster control still had 876ms/622ms long tasks, isolating substantial cost outside thumbnail rasterization. A PDF.js `onContinue` yielding trial measured 694ms/536ms. It also failed the <250ms target and was reverted.
- Current retained-source full suite was rerun twice: 609 passed each time; logs are `pytest-eta-continuation-run1.log` and `pytest-eta-continuation-run2.log`.
- Evidence: `browser-id122-real-thumbnail-queue-v120.json`, `browser-id122-mobile-thumbnail-disabled-control-v119.json`, `browser-id122-page-render-yield-control-v120.json`.


# Phase -1 Part A — baseline and v22 claims

Baseline branch/commit: main / 03436d90d9fc233eedf3a614eaa5de4f520137ca. The worktree was clean at start. No branch was created, and no reset, commit, push, deployment, production payment, or admin login was performed. A separate read-only Chrome inspection of the live pages was followed by two authorized guest operations using a public five-page PDF; they created normal transient job records for retention cleanup, not account or user document changes.

Full suite run before any v23 code change: **488 passed, 1 Starlette/httpx deprecation warning** twice. Logs: pytest-baseline-run1.log, pytest-baseline-run2.log. This confirms the v22 count and satisfies v23's baseline gate.

## ID 249 — Studio toolbar at 1360px

Reproduced the primary ribbon wrapping and placing Export PDF on a second line at a 1360×900 viewport. Changed desktop ribbon layout to a single non-wrapping row and compacted icon controls between 901–1450px while retaining native button titles/accessible labels. Two Chromium runs confirmed the primary row is 41px high, the complete ribbon fits its 816px client width, Export PDF fits inside the visible toolbar, document width remains 1360px, and no page errors occurred. Evidence: `browser-id249-studio-toolbar-1360.json`, script, and two screenshots.

## ID 250 — PDF to Markdown output title and hierarchy

Reproduced that the upload pipeline passed a random staged path to the converter without preserving the user's original filename, and that regular 12pt lines were promoted to `###`. Passed a sanitized original upload name through job options, use it as the H1 fallback when PDF metadata has no trustworthy title, and reserve heading markup for larger or bold text. Two browser API uploads of a synthetic PDF named `Annual Report.pdf` completed and downloaded 125-byte Markdown with `# Annual Report`, two unmarked body paragraphs, and `## Key Findings`. Focused regression tests passed. Evidence: `browser-id250-markdown-upload.json`, script.

## ID 251 — Admin plan counts and job dates

The live evidence cannot be asserted from the old synthetic 13-account dataset, so seeded a controlled 13-account dashboard fixture to discriminate the percentage calculation and missing tier rows. Reworked the plan breakdown to render every tier returned by analytics with each percentage divided by `total_users`, and changed the “today” metric to an explicit UTC calendar-day count separate from all-time jobs. A persistence regression seeded five tiers and jobs across UTC midnight. Two Chromium runs showed all five categories and distinct totals (987 all time / 7 today) with no page errors. Evidence: browser JSON/script/screenshots and the analytics regression test.

## ID 252 — Summary citation noise and truncation

Aligned consecutive supported inline page references into compact ranges and capped very long scattered inline citations at 120 characters while preserving the complete verified page set for source chips. The summary chip renderer compresses consecutive pages and limits visible disjoint ranges with an explicit remainder count. Tests verify a six-page run becomes `[Pages 1-6]`, scattered references stay bounded without losing the returned page IDs, and two browser rounds render `Pages 1-6` with capped ranges. Evidence: `browser-id252-summary-citations.json`, script, and citation regression test.

## ID 256 — Safe repair failure message

Two local Chromium runs uploaded a malformed no-trailer PDF through the repair job API. Both jobs failed with the friendly “This PDF is too damaged to repair automatically.” message; no pikepdf or `code=4` internal string appeared and the browser had no JS errors. Existing tests also verify storage errors receive a distinct safe retry message. Evidence: `browser-id256-repair-safe-error.json`, script.

## ID 259 — Studio and AI document page-count difference

Rather than silently present the original AI upload as the edited Studio result, added a visible disclosure to the AI active-document card that the AI workspace keeps its own PDF copy and must be given the edited export to refresh page count and analysis. Two Chromium upload rounds used a ten-page PDF at 1366px and 390px; both showed the ten-page AI count and disclosure with no horizontal overflow or JS errors. Evidence: `browser-id259-ai-copy-disclosure.json`, script, screenshots.

## ID 262 — Browser crash on PDF upload

Two fresh Chromium sessions uploaded a generated ten-page PDF through the Merge page's file input. Both sessions stayed alive, kept the upload listed, and reported no crash or JS error; selection completed in 2.004s and 1.685s. Evidence: `browser-id262-upload-stability.json`, script, screenshots.

## ID 258 — Daily synthetic sandbox probe

The local probe passed against local TEST credentials, verifying an unpaid INR 1.00 order and the checkout modal without a payment attempt. Browser inspection of GitHub run 44357454438 showed the scheduled job fails because `CASHFREE_APP_ID` and `CASHFREE_SECRET_KEY` are missing from repository Actions secrets. No secret values were accessed. A deduplicated owner-assigned issue alert is implemented for future failures, but the change is uncommitted. Owner must configure the TEST secrets and later verify notification delivery; ID 258 remains PARTIAL.

## IDs 267–268 — Studio toolbar delete and fresh upload

Two fresh Chromium rounds uploaded the same generated ten-page document directly into Studio. It rendered all ten pages without a null-style error; clicking the toolbar Delete page then yielded nine pages without the bogus “Cannot delete all pages” toast. No page errors occurred. Evidence: `browser-ids267-268-studio-upload-delete.json`, script, screenshots.

## ID 271 — Hindi Devanagari translation output

Re-ran the controlled local translation regressions. Both returned PDF outputs with the expected extractable Devanagari strings, including `प्लेन` and `टेस्ट`. No live provider/browser download was available in this pass, so classification remains partial; final proof requires content-checking a real provider-generated downloaded PDF after deployment.

## IDs 295 and 309 — DOCX rasterization and Scan-to-PDF dimensions

The current two-round v23 browser catalog converted a 4.98 MB, 69-page PDF into a 1.27 MB editable DOCX with 207 paragraphs and preserved first-page text; this confirms the old rasterization blowup is absent locally (mixed-media preservation is separately tracked as ID 308). The current Scan-to-PDF browser rounds for ID 253 also cover ID 309: 2400×1800 pixels at Original 200 DPI became 864×648 PDF points. Evidence: `browser-catalog-round2.json`, `browser-id253-scan-dpi.json`.

## ID 294 — Large-file server operations

Generated a 4.83 MB, 69-page image/text PDF, then uploaded/downloaded it in Chromium through Compress, Watermark, and Page Numbers. All three completed in 0.92s, 1.65s, and 1.30s; output retained 69 pages, Compress retained its text marker, Watermark retained `CONFIDENTIAL`, and Page Numbers contained first/last `Page N of 69` stamps. Evidence: `browser-id294-large-server-tools.json`, script.

## ID 301 — Sparse-PDF broad question response

Reproduced with a 24-page gallery PDF containing only 159 searchable characters. Added a deterministic low-text-density check for broad subject/summary questions; it now says the subject cannot be reliably identified and recommends OCR, instead of “No relevant information found.” The focused regression and two local Chromium API runs passed without provider access or JS errors. Evidence: `browser-id301-sparse-pdf-message.json`, script.

## IDs 297–298 — Cloud import trigger and annotation comment

The shared Drive/Dropbox URL dialog was exercised from both entry points in two Chromium rounds; each trigger opens the same single URL field and action. The current browser catalog annotation download was also checked for `ANNOTATION_AUDIT_NOTE` in extracted PDF text. Evidence: `browser-ids274-275.json`, `browser-catalog-round2.json`.

## ID 302 — PDF-to-Excel table columns

Two local Chromium runs uploaded a grid PDF and downloaded the resulting workbook. Both preserved the exact 3×4 table with separate Item, Quantity, Price, and Amount columns and both data rows. Unstructured prose still exports as one text column, which is not structured table data. Evidence: `browser-id302-excel-table-columns.json`, script.

## ID 303 — Sidebar Compare and Metadata entries

Two local Chromium rounds opened the Edit PDF sidebar category and confirmed both Compare PDF and PDF Metadata controls are listed and visible. Evidence: `browser-id303-sidebar-compare-metadata.json`, script.

The attached v23 PDF is 99 pages. Its tracker summary states 353 elite-list items: 247 open (11 P0, 76 P1, 160 P2), 89 verified_fixed, 15 to_verify, and 2 not_tested. The canonical IDs span 1–357 with intentional gaps and documented tracker-only artifact 244. The first line above records the count before work.

## V22 claims audit

| # | Claim from v22 report | Current code/evidence check | Result |
|---|---|---|---|
| 1 | ID 241 {total} substitution | server.py:2682-2704 replaces both {n} and {total}; regression coverage is in tests/test_text_layer_v18.py and tests/test_launch_audit_v22.py. | Present locally; live verified in v22 per PDF. Retest old failure mode in Phase -1. |
| 2 | ID 309 Scan-to-PDF sizes | converters.py:2245-2289, server.py:2397-2399, web/assets/app.js:3525-3532; tests in tests/test_launch_audit_v22.py; local Chromium evidence from v22 scripts. | Present locally; live verified in v22 per PDF. Retest raw-pixel failure mode. |
| 3 | ID 283 compression content guard | converters.py:1920-2084 skips alpha/palette/CMYK image replacement and validates rendered black-pixel changes; job warning passes via server.py:2372-2388, persistence.py:51, 227-235, 1080+, and web/assets/app.js:4638-4642. Tests in v21/v22 audit test files. | Present locally; live verified in v22 per PDF. Add exact rendered image regression to current v23 tests. |
| 4 | ID 299 billing status omits Cashfree order ID | server.py:3790-3826 response no longer includes cashfree_order_id; internal billing persistence and verification still use the field. | Present locally; live verified in v22 per PDF. Retest privacy regression. |
| 5 | ID 1 safe provider status/fallback | ai_engine.py:760-909, 1910-1934, 2060-2085; configured fallback is encrypted in persistence and used by the selected-provider helper. Safe 429 status reaches server.py:2818-2838. | Local controlled 429 fallback passes; imbalanced character-vs-block translation is now rejected with HTTP 422 and no download. Live deployed provider still fails content discrimination in the 10-page matrix; keep ID 1 PARTIAL. |
| 6 | ID 246 CSP and nginx version disclosure | deploy/nginx.conf.template:1-2, 70+ has server_tokens off and CSP; deploy/nginx-http.conf.template:1-2 disables tokens. | Present in templates; live verified by v22 per PDF. Recheck current served response read-only. |
| 7 | ID 220 PDF/A profile handling | Dockerfile:40-48 installs ICC profiles and copies sRGB; converters.py:1411-1503 finds profile and validates PDF/A metadata/OutputIntent. Prior WSL artifacts exist only in V21 reports. | Code is present; live verified by v22 per PDF. Production-image veraPDF validation still owed; do not reopen live fix on that alone. |
| 8 | Full suite 488 twice | Current clean baseline run: 488 passed twice, one warning each. | Confirmed. |
| 9 | 176 responsive route checks | V22 evidence `reports/launch-audit-v22/route-layout-matrix.json` is not present in this checkout. The attached v23 PDF records the later defects at 846/1024 and 390px. | V22 route-matrix claim is unverified here; v23 P0 340/341 reproduced and retested locally below. |
| 10 | 44-operation catalog 39 completed and P0 status report | V21 evidence folder exists, while the referenced V22 catalog/P0 artifacts are absent. | V22 claim is not current proof; rerun of the local catalog is in progress. |

This audit confirms v22 code claims only where present above. It does not close any v23 item without the v23 reproduction and regression checks.

## V23 implementation and local reproduction

| Item | Change/reproduction | Result and evidence |
|---|---|---|
| ID 1: misleading partial Translate | `ai_engine.translate_pdf_layout` now records translated block fraction and refuses to emit output below 50%; the API reports `failed` and includes the measured fraction header for partial/complete outputs. Added `tests/test_launch_audit_v23.py::test_translation_below_half_fails_with_actual_fraction`. | Local deterministic-provider browser runs and the focused regression pass. Live public-site repeats against the five-page sample exposed inconsistent quality: Spanish translated-marker pages 5/5 then 3/5; Hindi attempt 1 returned HTTP 429 and attempt 2 showed a Hindi-script marker on only 1/5 pages. Both successful HTTP 200 PDFs retained substantial English. This is not a fixed live result; see `browser-live-ai.json` and `live-translation-*-attempt-*-5-pages.pdf`. |
| ID 2: offline brief presentation/summary quality | Long-document fallback now emits one clearly labeled Offline Analysis heading and scoped section notes, with explicit text that local notes cannot establish absence elsewhere. Provider prompt now requires exact source numerics/units and forbids unsupported currency/absence claims. UI labels offline extractive notes separately from AI synthesis. | The 24-page cancellation/deadline fixture is covered by unit tests; the 69-page browser output was exercised with the deterministic test provider. Live public summary returned HTTP 200 and citations for pages 1–5, but the response omitted `summary_mode`, so provider synthesis cannot be distinguished from offline fallback; the required provider-backed 69-page case remains unverified. See `browser-live-ai.json`. |
| ID 4: Drive and direct cloud import | Local Chromium called `/api/cloud/sync` twice for the correct W3C testfiles PDF and twice for the exact owner Drive `/view` URL from v23. | W3C attempts both returned HTTP 200 and content-checked one-page `dummy.pdf`. The exact Drive URL failed both times with the truthful `Google Drive returned image/png, not a PDF` response. The link does not currently point to a PDF, so the owner Drive import requirement cannot pass until a valid PDF link/file is supplied. Evidence: `browser-p0.json` (`cloud_import_p0_paths_twice`). |
| ID 93: account/data persistence | Initial process-restart test was followed by a current-image four-worker container replacement run on an isolated named volume. | Fixed locally: concurrent SQLite initialization was serialized; six cold-start initializers passed, all four workers became healthy, the account and feedback row survived container replacement, and Chromium login/authenticated `/api/auth/me` passed. The earlier Docker-engine-unavailable attempt is superseded. Evidence: `browser-id93-container-persistence.json`, `browser_id93_container_persistence.py`. |
| ID 101: admin secret code exposure | Confirmed required env-only startup settings, Gitleaks workflow `.github/workflows/secrets.yml`, and ran `scripts/prepare_admin_history_purge.py` to create a separate sanitized mirror at `C:/Users/mdham/Downloads/pdf_splitter/paperplane-redacted-v23-prep-2026-11-19.git`. | The script scanned reachable commit messages and every remaining object without printing the compromised value; `git fsck --full --no-reflogs` passed, the new mirror has no remote, and its warning marker was removed after verification. The two protected existing mirrors and source repository were not modified. This history-only candidate predates uncommitted v23 code and is NOT a publish-ready mirror. Credential rotation, owner review, coordinated force-push/cache purge, and Security Audits review remain owner steps. |

| ID 1: current-live translation provider matrix (2026-11-20) | Re-ran the live Translate UI twice for synthetic 10-page Spanish and Hindi PDFs against `https://paperplane.qd.je`. | Both Spanish runs returned HTTP 200 and content-checked downloads with 10/10 Spanish pages, all page markers retained, and no source English remaining. Both Hindi runs returned HTTP 422 because only 20% of blocks/segments/characters were translated; the UI produced no download. All four rounds had zero browser errors. The safe minimum-coverage rejection works; the deployed Hindi-provider completeness defect remains open. Evidence: `browser-live-id1-translation-matrix.json`, `browser_live_id1_translation_matrix.py`, `id1-live-es-round1.png`, `id1-live-es-round2.png`, `id1-live-hi-round1.png`, `id1-live-hi-round2.png`. |

| ID 1: provider JSON string segment IDs (2026-11-20) | Hardened `_parse_translation_batch` to normalize valid decimal-string IDs without accepting malformed/ambiguous IDs, booleans, or segments outside the request. | Focused parser tests passed. Current-source browser runs exercised the actual translate endpoint/parser with a controlled provider returning string IDs: Spanish and Hindi succeeded twice each on 3-page and 69-page PDFs, preserving page count/order and searchable translated markers while removing source text (8/8, no browser errors). Local v133 image health/parser checks passed and the Docker image was removed after smoke. The raw live-provider response was unavailable, so this explains a plausible class of dropped segments but does not prove it caused the deployed Hindi 20% response. Keep ID 1 PARTIAL pending post-deploy live verification. Evidence: `browser-id1-local-bilingual-end-to-end.json`, `browser_id1_local_bilingual_end_to_end.py`, `pytest-current-v133-summary.json`, `docker` image digest in `SELF-ANALYSIS.md`. |
| ID 102: feedback delivery | Two local Chromium rounds submitted feedback through a browser same-origin request while an authenticated admin Feedback tab was open. | Both showed the new row via automatic polling without reload; the disposable feedback record was deleted. Evidence: `browser-p0.json` (`feedback_submission_visible_in_admin_poll_without_refresh`). |
| ID 207: 60 MiB Merge progress and output | Ran `scripts/browser_v14_smoke.py` twice against the current code, with a synthetic 60 MiB, 759-page PDF plus a 10-page PDF. | Both local Chromium runs observed XHR progress and cancel recovery, downloaded the merge output, and content-checked 769 valid pages. Second run output: `browser-full-smoke-round2.log`. Owner's image-heavy fixture was unavailable. |
| ID 6: false authorship claim with blank PDF metadata | Uploaded a one-page PDF with neither author metadata nor an author statement and asked whether Albert Einstein wrote it. | Three focused regression tests passed. Local Chromium request to `/api/ai/chat` returned HTTP 200 with “I can't verify that authorship claim…” and no citations. Evidence: `browser-p0.json`; test: `test_false_author_claim_is_corrected_when_metadata_and_text_have_no_author`. |
| ID 9: Smart Metadata section-number/date and first-run viewer | The local extractor returned a stable section-number result; a two-round Chrome test then exercised an invoice upload/view/export flow, a controlled first-attempt 502, and a delayed response interrupted by navigating to another tool. | Section-like `3.3.1` is neither date nor topic. Transient 502 retried to HTTP 200; viewer mounted, actual JSON download parsed, result card survived close. Tool switch cancelled/invalidated the delayed request and no stale viewer/result appeared. Zero page errors. Provider availability remains unproven. Evidence: `browser-p0.json`, `browser-id9-metadata-viewer-e2e.json`, `browser_id9_metadata_viewer_e2e.py`. |
| ID 35: greeting with an active document | Posted a real one-page PDF with “Hello, how are you?” to local `/api/ai/chat` through Chromium. | HTTP 200 greeting response, no citations, no document-retrieval fallback. Evidence: `browser-p0.json` (`general_greeting_works_with_document_loaded`). |
| ID 10: Studio Extract no automatic download | Opened a one-page PDF in Studio and clicked the visible Extract button. Repeated the real browser flow twice. | Both runs triggered Chromium downloads; downloaded PDFs reopened with one page and the expected page text. No page errors. Latest run recorded in `browser-p0.json` (`studio_single_page_extract_download_content_checked`). |
| ID 11: blank/stale canvas during deep page jump | Loaded a synthetic 69-page PDF in Chromium, waited for its canvas, navigated to page 69, then returned to page 1. Repeated twice. | Each target active page rendered visible (non-white pixel) content. No page errors. `browser-p0.json` (`studio_page_jump_1_69_1_canvas_rendered`). |
| ID 14: Annotate succeeds but Redact misses the same keyword | Submitted the same fixture containing “Important” to local Chromium requests for `/api/pdf/annotate` and `/api/studio/security/redact`. Repeated twice. | Both endpoints returned HTTP 200; annotation output had one annotation, while redaction removed “Important” from extracted text and preserved “review note”. Evidence: `browser-p0.json` (`annotate_and_redact_find_same_keyword`). |
| ID 12: raw Markdown and duplicated nested page tokens in chat | Uploaded a source PDF in the local browser and asked a document-summary question with the AI provider disabled. | Removed duplicate citation emission from deterministic extraction. Two browser runs rendered a single inline citation tag and a single matching verified-page chip, with no raw markdown or nested `[[Page N]]`. Provider-backed LaTeX/format variance remains unverified. Evidence: `browser-p0.json`; regression in `tests/test_launch_audit_v23.py`. |
| ID 13: Studio page delete delay | In two browser runs, opened a 69-page PDF, deleted page 34, then verified page count and the shifted page content. | Page count updated to 68 and page 34 became former page 35 in 0.763s and 0.765s. Evidence: `browser-p0.json` (`studio_delete_one_page_updates_count_and_content`). |
| ID 15: sticky navigation allegedly overlaps tool headers | Scrolled `/ocr-pdf` and `/remove-pages-pdf` to 560px at 1104×760 in two Chromium runs; measured tool-title, topbar, and mobile-nav rectangles. | No measured overlap: the topbar had scrolled out of view and the title was above the viewport. Exact reported sticky-pill screenshot behavior was not reproduced, so the item remains partial. Evidence: `browser-p0.json` (`tool_heading_not_obscured_after_scroll_1104px`). |
| ID 16: developer page spec links and footer API Docs loop | Added CSP-compatible Swagger/ReDoc pages and generated OpenAPI JSON, then checked developer and legacy URLs. | Two browser runs verified Swagger, ReDoc, and schema routes (200+ paths), with all developer/footer links and `/docs`, `/api-docs`, `/redoc` resolving without the old loop. Browser had no page errors. Regression: `test_public_api_spec_links_resolve_without_developer_page_loop`. |
| IDs 17–21: Tool Desk, route aliases, Studio panel/toolbar geometry, Run label, first page render | Chromium loaded `/tool-desk`, followed both aliases, toggled Studio Pages at desktop width, measured the Run label at 390 px, and opened a real one-page PDF in Studio. | Directory and both routes resolved, toolbar remained visible beside the Pages panel, no midword label break was found, and first page canvas rendered in 1.035s. Evidence: `browser-p0.json` cases `tool_desk_view_and_tool_route_aliases`, `studio_sidebar_toggle_does_not_cover_toolbar`, `run_button_label_does_not_split_midword`, `studio_first_page_canvas_paints_within_5_seconds`. |
| ID 5: summary citation nondeterminism | Set all Executive Brief provider calls to temperature zero and verified provider wire payloads for OpenAI-compatible, Anthropic, and Gemini. Repeated browser summary calls against the local deterministic offline mode. | Provider payload tests passed; both offline runs returned identical text and the same page chips, exactly aligned with inline citations. Live provider nondeterminism remains unverified; item partial. Evidence: `browser-p0.json` (`executive_brief_repeated_citation_parity`) and tests in v23 suite. |
| ID 8: Remove Pages first-attempt latency | Built a content-heavy 10-page PDF of 5,050,539 bytes and removed page 2 via two local browser `/api/jobs` runs. | Both first attempts completed without retry in 1.621s and 1.533s. Downloaded PDFs were parsed: each has 9 pages and former page 3 now appears at page 2. Exact owner fixture unavailable. Evidence: `browser-p0.json` (`remove_pages_first_attempt_latency_on_5mb_pdf`). |
| ID 98: Cashfree | No real payment or production credentials were used. | Sandbox can be exercised by existing regression; production keys and one real payment are owner-only. Guest checkout/account-required wording still needs an explicit local browser retest. |
| IDs 317/318: Protect and Sign downloads | Chromium at local server, signed-in disposable Pro, two rounds each. Captured downloads and parsed actual PDFs. | Protect: 1,479 bytes twice, one encrypted page each. Sign: 1,554 bytes twice, signer text present on one page each. No page errors. `browser-p0.json`. |
| ID 340: fixed mobile bar covers actions | Added bottom safe-area padding to the tool shell. Chromium at 846×712 uploaded a synthetic PDF, scrolled the action into view, measured geometry for Split, Merge and Compress. | All three primary actions were above/nonintersecting the fixed bar (`button bottom 380px`, bar top 646px). `browser-p0.json`. |
| ID 341: breadcrumb collapses | Ancestor breadcrumb items do not flex-shrink; active leaf alone may shrink. | Chromium at 1280×800 and 1024×768 showed full `Paperplane / Workspace / AI Document Intelligence`; no single-letter collapse. `browser-p0.json`. |
| ID 314: Executive Brief PDF download | Delayed object-URL revocation after anchor click. Invoked the production browser-side PDF generation/download path in Chromium. | Captured a 986-byte, one-page PDF; opened with PyMuPDF and verified the synthetic content. `browser-p0.json`. |
| 44-operation content browser sweep | Local Chromium audit via `scripts/browser_v21_catalog.py` against isolated app/database. | 39 completed; OCR, Summarize, Translate unavailable without local services; PDF/A failed in this container; HTML-to-PDF was correctly blocked by SSRF policy. Full item-level results: `browser-catalog.json`. This is not 44/44 successful functionality. |

### Post-change test status

Focused regressions: `tests/test_launch_audit_v23.py` and `tests/test_ai_workflows.py` pass. The standalone account/feedback persistence and v23 fraction-gate checks pass. This earlier 490-test note is superseded by the continuation below.

## Continuation: targeted fixes, browser checks, and final local suites

Additional code work covered checklist defects 315, 319, 321, 323, 333–335, 337–338, 342–343, and 352:

- Studio opens now show a loading overlay immediately; a delayed second open and first Text-tool activation were checked in Chromium.
- Compression stores the explicit missed-target warning in the job record. A noisy image PDF sent through a real local Chromium `/api/jobs` request with the 100 KB preset returned the actual output size, the warning, and a rendered non-black page.
- Progress uses the same rounded measured upload percentage for the bar and label; processing uses an indeterminate bar instead of a fabricated percent. Toast pointer hit testing confirmed the notification cannot capture the underlying click.
- PDF metadata editing retains unedited author/creator/producer/date fields. A browser-produced PDF was downloaded and parsed.
- PDF-to-Markdown no longer uses the storage filename as its H1; glyph geometry restores spaces in the targeted no-space regression. The local browser download was content checked.
- Two-dimension photo resizing letterboxes instead of stretching; the browser downloaded and inspected a 100×100 output.
- Smart Metadata fallback rejects common attribution boilerplate and favors a prominent centered heading; synthetic PDF regression passes. The reported real source PDF was unavailable.
- Local-result Blob handoff opened the merge result in Studio and rendered the page. Full coverage across every local PDF/photo tool, route changes, and reloads remains open.
- The signed guest quota was exercised in a separate local browser context: ten accepted server jobs were reflected as 10/10 usage, and job eleven was rejected with HTTP 402 / `TIER_LIMIT_REACHED`.
- Pricing now renders limits for every operation and tool pages link to the table. The privacy copy marks itself as a draft and removes unsupported provider-training and at-rest-encryption claims. `/refund`, `/contact`, and `/status` now resolve to pages that clearly disclose missing owner-approved policy/monitoring details instead of returning 404.
- ID 45 initial Studio/footer finding: a trailing `.app-global-footer { visibility: visible }` rule overrode the intended hide-until-scroll behavior; removing it fixed the desktop first-paint issue. This earlier 1366px-only note is superseded by the final six-viewport matrix and 901px ribbon fix at the end of this log.

ID 3 Studio retention was rechecked in guest Chromium twice: delete page 1 from a 10-page fixture, confirm persisted nine-page IndexedDB content, reload, wait 30 seconds, and verify page count plus former page 2 text. Both rounds had zero page errors; see `browser-p0-round8.json` and `browser-p0-round9.json`.

ID 49 export retries: controlled Chromium tests aborted the first POST and separately injected a first-attempt HTTP 503. Both retry paths succeeded in two consecutive runs. Each downloaded an 867-byte PDF verified by PyMuPDF for page count and expected source text. The v23 prompt keeps closure pending the owner’s decision; see `browser-p0-round12.json` and `browser-p0-round13.json`.

ID 184 guest quota isolation was repeated twice using separate Chromium contexts: one accepted operation showed 1/10 for the active guest and 0/10 for the independent browser; the active guest then reached 10/10 and the eleventh operation returned 402. Evidence: `browser-p0-round21.json` and `browser-p0-round22.json`.

ID 296 trusted-proxy attribution was rechecked in two browser rounds; two distinct forwarded client IPs were stored on the matching audit events. A focused regression additionally verified the untrusted direct-client spoof case is ignored. Evidence: `browser-p0-round23.json`, `browser-p0-round24.json`, and `tests/test_launch_audit_v10.py::test_trusted_proxy_ip_is_attributed_and_untrusted_forwarding_is_ignored`.

ID 293 Flatten was checked in a local browser with a real Highlight annotation: the downloaded PDF retained the source text, rendered the yellow highlight appearance, and had zero active annotations. Evidence: `browser-p0-round25.json` and `tests/test_launch_audit_v20.py::test_flatten_bakes_highlight_annotation_and_removes_annotation_record`.

ID 292 Split was checked in Chromium on a labeled 10-page PDF. The `1-2`, `1`, and `1,1,2` outputs were downloaded and each page's text/count was checked against the exact requested pages. Evidence: `browser-p0-round26.json` and `tests/test_launch_audit_v20.py::test_split_ranges_return_the_requested_page_content_and_count`.

Latest local browser evidence: `browser-p0-round3.json` through `browser-p0-round34.json`, plus `browser-p0.json`; rounds 3–5 each contain 18 assertions and zero page errors, rounds 6–7 cover pricing/legal routes, rounds 8–9 verify ID 3 retention, rounds 10–13 verify ID 49 retry paths, rounds 19–20 verify ID 168 first paint/Studio restore, rounds 21–22 verify ID 184 guest quota isolation, rounds 23–24 verify local ID 296 proxy attribution, round 25 verifies ID 293 flattening, round 26 verifies ID 292 split ranges, and round 29 verifies ID 137 Studio theme synchronization and Studio restore toast geometry; round 30 verifies ID 7 SPA workflow/FAQ copy transitions from Merge to Split; round 31 verifies ID 22 upload wording and empty-state restoration after clearing chat; round 32 verifies ID 23 authenticated Free quota enforcement; round 33 verifies ID 24 AI readiness-status consistency; round 34 verifies ID 26 Aadhaar redaction in the downloaded PDF. The latest P0 run covers 60 checks with zero page errors. The latest route/viewport matrix passed 176/176; ID 36 checked rendered copy on 46 public/tool routes, ID 167 checked headings across all 44 tool routes, ID 221 checked an authenticated first-visit feedback prompt and dismissal at 390×844, ID 205 visually/measurably checked the desktop workspace navigation pill, and ID 313 measured signature/security dialogs at 390/820/1366/1920 px (8 measurements) with no horizontal clipping and internal scrolling on the phone security dialog. ID 90 was tested separately: two four-job concurrent Merge rounds completed and downloaded valid PDFs, and the OTP header-leak test passed.

The current 506-test suite passed twice after the final tree update (runs 3 and 4), with one existing Starlette/httpx deprecation warning on each run. Logs: `pytest-final-run3.log`, `pytest-final-run4.log`.

After the mobile Pricing limits table was converted to stacked rows, `node --check web/assets/app.js` passed and the full 506-test suite passed twice more (runs 5 and 6). The local Chromium mobile visual sweep passed 9 view/route combinations (Home, Merge, Pricing at 320×740, 390×844, and 820×900), with no document overflow or page errors. At both 320 and 390 px it separately checked all 44 Pricing rows and each of the five displayed data labels; evidence and screenshots: `browser-mobile-visual.json`, `mobile-pricing-limits-row.png`, and 320/390/820 px screenshots.

Live public-site smoke: downloaded TotPDF's five-page numbered sample, confirmed the fixture's source text/page count, uploaded it to the deployed Merge and Split routes in server mode using a fresh guest browser, and opened/content-checked the results. Two copies merged to 10 searchable pages; split-all returned five one-page PDFs in source order 1–5. No page errors and no payment. Evidence: `browser-live-smoke.json`, `live-merge-10-pages.pdf`, `live-split-5-pages.zip`. This produced two transient job records on the deployed service; no production account/admin state changed.

Intermediate repeat runs found three Cashfree tests reusing fixed emails in the persistent test database; changed those probes to unique addresses. They also exposed two API-doc tests asserting the prior production redirect behavior; updated them to assert the new working spec route while keeping default FastAPI `/openapi.json` disabled. The final post-change full suite passed **506 tests twice**, one existing Starlette/httpx deprecation warning each. This does not complete the 353-item checklist. Production-provider, deployment, owner-wording, and broad per-tool checks remain open as stated in `FINAL-REPORT.md`.



ID 137 theme and mobile toast overlap follow-up: first screenshot review caught that the canvas surround remained dark after light controls were fixed. Added theme-aware Studio stage, empty-state, and loading surfaces. A second screenshot then exposed the restore toast over the mobile toolbar; `showToast` now positions Studio notices below the measured variable-height toolbar and tracks viewport resize. Chromium exercised the real Settings dark→light controls, reload persistence, and restore toast placement on desktop and 390 px mobile. Both toast geometries had zero toolbar intersections; the mobile document width stayed 390 px. Evidence: `browser-p0-round29.json`, `studio-loaded-390.png`; implementation: `web/assets/styles.css`, `web/assets/app.js`.


ID 7 SPA workflow/FAQ transition: started on the Merge tool page, then selected Split from the in-app sidebar. The downloaded data contexts had distinct headings and FAQ labels. After navigation, the visible SEO workflow contained the Split heading and FAQ and neither the prior Merge heading nor prior Merge FAQ. Evidence: `browser-p0-round30.json`; source behavior in `web/assets/app.js::syncSeoContent`. This verifies final SPA state on the local build, not every tool pair.


ID 22 AI empty state: a clean Chromium context showed the exact “Upload PDF to chat” instruction and Choose PDF control on desktop and 390 px mobile, with no content overflow. Then sent a general greeting and clicked Clear Chat; first reproduction left the empty-state card hidden after the conversation cleared. Fixed the clear handler to run `updateAiDocBar()` after resetting the conversation. The same browser test now verifies the empty state and upload copy return. Evidence: `browser-p0-round31.json`; source: `web/index.html`, `web/assets/app.js`.


ID 23 Free-tier quota bypass: in Chromium with the seeded authenticated Free account, submitted ten real `/api/jobs` requests and confirmed all returned 202, `/api/billing/status` reported 10/10, and request eleven returned 402 `TIER_LIMIT_REACHED`, tier `free`, usage 10. Evidence: `browser-p0-round32.json`.

ID 24 AI readiness status: in the controlled local environment with no provider credentials, `/api/ai/capabilities` reported `executive_brief_available: false`; public `/api/ai/test-connection` reported `configuration_missing`; authenticated `/api/admin/ai-health` also reported `configuration_missing` and `configured: false`. Evidence: `browser-p0-round33.json`.


ID 26 Aadhaar output verification: uploaded a synthetic PDF containing `1234 5678 9012` through the real Mask Aadhaar job, downloaded the returned PDF, and checked its text layer contains no first eight digits while retaining `9012` and the `XXXX XXXX` replacement. Rendered pixels inside the replacement text bounds had mean luminance below 90, confirming a dark rendered mask. Evidence: `browser-p0-round34.json`.


ID 25 catalog coverage: the saved local 44-operation catalog records 39 completed operations, OCR/Summarize/Translate unavailable due unconfigured local services, and PDF/A failure in this Windows host. These gaps leave the historical 38/41 tool pass only partially revalidated. Evidence: `browser-catalog.json`; production/provider and production-image checks remain open.

## Continuation: ID 1 provider retry/fallback visibility

The local v23 AI dispatcher already retries transient upstream failures and can use a separately configured provider. Extended its sanitized runtime health snapshot to record the last request outcome, a rate-limit flag, and whether the configured fallback handled the request; the admin response excludes credentials and raw provider bodies. Self-review found four production workers, so the state is persisted in the shared SQLite settings table, with an allowlist that stores no provider body or credential. State for an old provider is not presented as the current provider's status. The Admin AI Settings health banner now explains an HTTP 429 and fallback status. A controlled local integration test forced primary HTTP 429, ran translation through the fallback provider, parsed the downloaded one-page PDF, and verified the translated Spanish text. The test also checked health state and confirmed both test credentials were absent. A separate SQLite readback test verifies another worker can read the allowlisted state and that secret fields are discarded. Local Chromium opened `/admin` using controlled admin API responses and verified the visible health banner, rate-limit wording, fallback wording, credential absence, and cache-busted `admin.js?v=15` (5/5 checks, no page errors). Evidence: `tests/test_ai_workflows.py::test_translation_falls_back_after_primary_rate_limit_and_reports_admin_health`, `tests/test_launch_audit_v23.py::test_ai_provider_health_is_shared_storage_sanitized_and_worker_readable`, `browser-id1-admin-health.json`, `browser-id1-admin-health.png`. The final two complete suite runs passed 508 tests each: `pytest-cont-id1-run7.log` and `pytest-cont-id1-run8.log`.

Additional local regression: the translation acceptance gate used to count source characters only, allowing one long block to make a result appear sufficiently translated even when most shorter blocks remained in the source language. It now requires at least 50% of both blocks and source characters, surfaces both coverage values for partial results, and rejects zero-block results before coverage evaluation so upstream 429/empty-result classifications survive. A deliberately imbalanced PDF (98% of characters but 25% of blocks translated) now returns HTTP 422 without offering a download in the local Chromium flow. Two local browser rounds × Spanish/Hindi each passed the 10-page 429→configured-fallback path and downloaded content-checked PDFs. Evidence: `browser-id1-imbalanced-coverage.json`, `browser-id1-10page-rate-limit-fallback.json`, `browser_id1_10page_rate_limit_fallback.py`, `tests/test_launch_audit_v23.py::test_translation_rejects_one_large_block_when_other_blocks_are_preserved`.

The deployed live 10-page Spanish/Hindi matrix still fails: the Spanish run marked complete contained only source markers, and the three other downloads were partial with source markers and no target-language markers. ID 1 remains PARTIAL pending deployed-provider/configuration correction and a passing content-discrimination retest.

## Continuation: ID 2 69-page summary mode

Chromium uploaded a generated 69-page labeled PDF through `/ai-intelligence`, clicked Generate Executive Brief, and downloaded/parsed the actual `/api/ai/summarize` response. With no local provider configured, the API returned HTTP 200 and `summary_mode=offline_extractive`; all 69 page citations were present, including page 69, and the final-page fact remained in the brief. The visible result contained exactly one “Executive Summary (Offline Analysis)” heading and a single corresponding mode badge. Screenshot review found the old header badge was statically “Synthesis”, even on local fallback responses; changed it to report “Offline Analysis”, “AI Synthesis”, or “Mode Unreported” based on the API field and explicit fallback heading. Chromium then tested the actual offline response and controlled provider-synthesis and missing-mode responses; all three labels matched, with no page errors. Evidence: `browser-id2-69page-summary.json`, `id2-summary-route.png`, `id2-summary-mode-mapping.png`; script `browser_id2_69page_summary.py`.

This closes a misleading local presentation bug and verifies the local 69-page offline path. The deployed summary omitted `summary_mode` in the prior public check and the provider-backed 69-page synthesis/quality requirement remains open.

ID 34 layout recheck: before and after the generated 69-page brief, measured AI Chat, Smart Metadata, and Executive Summarizer card rectangles at 390×844, 820×900, 1280×720, and 1920×1080. At desktop sizes, chat remained in the left column and both panels stayed in the right column. At 390/820, all three occupied the mobile stacked column. Every measured card stayed inside viewport bounds, the document had no horizontal overflow, and all three columns retained the same coordinates/widths after summary generation. This matches the stated reference composition; ID 34 is marked FIXED LOCALLY for the current build. Evidence is in `browser-id2-69page-summary.json` (`before_summary_layout`, `post_summary_layout_checks`).

## Continuation: IDs 37, 39, and 242 local processing and AI directory grouping

### ID 242 current live mode reconciliation

The contradictory older live observations are resolved against the currently served UI. Two fresh Chromium contexts visited Merge, Split, Remove, and Rotate; every route returned HTTP 200 and loaded the local-processing checkbox checked with no `localStorage` override. In each context, changing Merge to Server survived reload and switching to Rotate, with zero page errors. This verifies the live default and preference behavior; content-checked local execution, quota separation, and controlled server fallback are evidenced separately in `browser-id37-id242-local-processing.json`. Evidence: `browser-live-id242-processing-mode.json`, harness `browser_live_id242_processing_mode.py`.

The latest Chromium run visited all 44 operation routes in a fresh context. Nine client-side workflows (Merge, Split, Remove, Rotate, Organize, Photo Compress, Photo Resize, Photo Merge, and Exam Photo Resizer) generated downloadable outputs; PDF page text/order/rotation and image decodability/dimensions were parsed, with zero `/api/jobs` requests for each local run. Toggling the visible switch to Server and back to Local survived reload. The test then replaced the frozen local PDF runtime with a controlled failing implementation; the UI disclosed that server retry uses the daily allowance, made exactly one server job, and returned a content-checked merge while retaining Local as the saved preference. No browser errors occurred. Evidence: `browser-id37-id242-local-processing.json`; `browser_id37_id242_local_processing.py`.

The v23 local Tool Desk now exposes AI Chat, Smart Metadata, and Executive Brief through its AI Intelligence workspace, rather than repeating three individual cards in the directory. AI Translate remains distinct; legacy `/ai-pdf-chat` still returns a working page. Local Chromium verified 41 distinct directory cards, the AI category filter, the workspace, the legacy route, and 390 px layout bounds. The live deployed page still shows the AI PDF Chat duplicate card and remains a post-deploy retest item. Evidence: `browser-id39-ai-tool-dedup.json`, `browser_id39_ai_tool_dedup.py`, and `id39-*.png`.

After the final client-side changes, `node --check web/assets/app.js` and changed-file whitespace checks passed. Two fresh full-suite runs passed 508 tests each: `pytest-cont-id39-run1.log` and `pytest-cont-id39-run2.log` (one existing Starlette/httpx deprecation warning per run).

## Continuation: IDs 340 and 341 mobile P0s

Chromium with enabled Run buttons and uploaded PDF fixtures reproduced the bottom-navigation obstruction at 820 px: the button center landed under the fixed mobile bar. The new mobile CTA dock stays 8 px above the nav, and `main-area` has enough bottom scroll padding for the CTA and nav; all nine Merge/Split/Compress hit tests passed at 320, 390, and 820 px with no overlap, interception, overflow, or page errors. For ID 341, the breadcrumb's current-page segment was measured at zero width inside a 56.6 px trail at 820 px. On widths up to 900 px the shortened breadcrumb is hidden and the mobile workspace indicator now says “AI Intelligence”; 320/390/820 px all fit with no overflow. Evidence: `browser-p0-340-341-mobile-layout.json`, `browser_p0_340_341_mobile.py`, and `p0-340-split-*.png` / `p0-341-ai-*.png`.

## Continuation: ID 314 Executive Brief PDF download

Local Chromium generated the actual 69-page offline Executive Brief and clicked its PDF download button in two consecutive runs. Both browser downloads were captured, saved, opened with PyMuPDF, and checked for a valid multi-page PDF, the Executive Summary heading, and findings from both source page 1 and source page 69. Each was 4,523 bytes / 3 pages, and neither run produced browser page errors. Evidence: `browser-id314-summary-pdf-round1.json`, `browser-id314-summary-pdf-round2.json`, and `id314-executive-brief.pdf`; harness: `browser_id314_summary_pdf.py`.

The complete current P0 Chromium sweep was rerun after correcting two timing assumptions in its harness (wait for initial route reconciliation before the footer test, and hold `/api/auth/me` long enough to capture the signed-in first paint). It completed all 60 assertions with zero page errors. Evidence: `browser-p0.json`; harness: `browser_p0.py`.

## Continuation: ID 173 Rotate copy accuracy

Opened `/rotate-pdf` in Chromium and checked the rendered SEO copy, not only the server catalog: the heading says “Rotate the entire PDF document,” and the intro says a single angle applies to every page, with selected-page rotations in Page Organizer. Followed the Page Organizer related link and confirmed the SPA showed the reorder-page workflow. No obsolete “page-by-page rotation workflow” copy or browser page errors. The existing focused catalog regression test also passes under the full suite. Evidence: `browser-id173-rotate-copy.json`, `id173-rotate-copy.png`, `tests/test_launch_audit_v23.py::test_rotate_landing_copy_matches_whole_document_behavior`.

## Continuation: ID 338 Smart Metadata title

Recreated the discriminator in a one-page PDF: a small Google attribution/permission notice precedes a large centered “Attention Is All You Need” title. Uploaded through AI Intelligence and clicked Extract Structured Entities. The `/api/ai/extract` response and the opened Developer JSON view both report the paper title; attribution is not selected as the document title, contacts/topics remain available, and the browser recorded zero page errors. Evidence: `browser-id338-smart-metadata-title.json`, `id338-smart-metadata-title.png`, `browser_id338_smart_metadata_title.py`, and `tests/test_launch_audit_v23.py::test_smart_metadata_skips_attribution_and_uses_prominent_title`.

## Continuation: ID 315 Studio fresh first-open tools

In two independent fresh Chromium contexts, uploaded a new one-page PDF through Studio's actual file input and waited for the first page canvas to render. Without reloading, selected Text, clicked the page, and verified the text input panel appeared; then selected Stamp, clicked the page, and verified the stamp picker appeared. Both runs had zero page exceptions and zero unexpected console errors. The observed 401 was the expected guest `/api/auth/me` response. This exercises the reported first-open failure path; the historical live null-style exception itself did not occur locally. Evidence: `browser-id315-first-open-tools.json`, `id315-first-open-tools-round1.png`, `id315-first-open-tools-round2.png`; harness: `browser_id315_first_open_tools.py`.

## Continuation: ID 316 PDF Metadata JSON view/export

Added an accessible preview and JSON download to the Metadata tool result. An initial browser experiment showed that parsing the output by fetching its guest PDF download URL consumed the one-time guest capability, leaving the expected PDF download to fail. Reworked this so the owner-scoped job status response supplies an allowlisted summary read from the completed PDF; opening or exporting the summary does not access or consume the PDF download. Chromium changed title, author, and subject, downloaded/parsed the JSON, then downloaded the PDF and matched title, author, subject, keywords, creator, producer, and dates to PyMuPDF metadata. The PDF was 990 bytes / one page, JSON download was 316 bytes, and the browser had zero page errors. A regression test proves job status does not consume the guest capability and the PDF can still be downloaded once. Evidence: `browser-id316-metadata-json-export.json`, `id316-metadata-json-export.png`, `browser_id316_metadata_json_export.py`, `tests/test_launch_audit_v23.py::test_metadata_job_exposes_output_metadata_without_consuming_guest_download`.

After the ID 316 code change, two complete full-suite runs passed with 509 tests each: `pytest-cont-id316-run1.log` and `pytest-cont-id316-run2.log`.


## Continuation: IDs 320, 327, 330, 331, 332, and 339

ID 320: Chromium uploaded and rendered a one-page PDF in a clean Studio browser, clicked Clear Studio PDF with no other Paperplane tab open, and verified the document cleared with no “Close other tabs” warning. The handler now only gives the other-tab guidance for the explicit IndexedDB blocked error; other storage failures explain that browser storage could not be cleared. Failed database opens no longer poison the cached promise, and database connections close on version changes. Evidence: `browser-id320-clear-studio.json`, `id320-clear-studio.png`, `browser_id320_clear_studio.py`.

For ID 327, Chromium opened PDF to JPG and verified the selected-pages FAQ honestly states the current all-pages behavior and directs users to Split first. The same browser pass confirmed the footer label “Temporary results” for `/history` (ID 330), Light Paper is marked as the default active theme (ID 331), `/developers` sets a developer-specific document title (ID 332), and the FAQ contains eight questions covering pricing, limits, privacy, refunds, and support (ID 339). The server regression test checks the SEO capability text, navigation label, theme choice presence, and FAQ count. Evidence: `browser-id327-330-331-332-339.json`; test `tests/test_launch_audit_v23.py::test_seo_and_navigation_copy_matches_pdf_tool_capabilities`.


## Continuation: ID 344 guest auth response and badge state

Changed `/api/auth/me` to return HTTP 200 with `authenticated: false` for guest and revoked sessions. The browser opened `/tool-desk`, `/merge-pdf`, `/settings`, `/faq`, and `/history`; all five auth responses returned 200. There were zero auth 401s, browser page exceptions, or console errors. On `/merge-pdf`, the plan badge was hidden while auth was pending, then displayed “Free Guest Tool” after the guest response resolved. Updated tests cover anonymous profile, OTP pending signup, revoked logout session, and the production profile contract. Evidence: `browser-id344-guest-auth.json`.

The complete suite then passed twice: 510 tests in `pytest-cont-id344-final-run1.log` and 510 in `pytest-cont-id344-final-run2.log`, each with four deprecation warnings.


## Continuation: ID 329 history disclosure

The `/history` page now clearly states that Paperplane does not keep a job or download history list. Its page heading and SPA browser title say “Temporary results — no saved history,” and the footer link now reads “Temporary results.” Chromium verified the rendered disclosure and matching browser title; the focused server regression test checks the route HTML. Evidence: `browser-id327-330-331-332-339.json`.


After the ID 329 page title and history disclosure updates, the full suite passed twice again: 510 passed in `pytest-cont-id329-final-run1.log` and `pytest-cont-id329-final-run2.log`, each with four deprecation warnings.


## Continuation: ID 43 delayed Studio deletion and Undo

On a 10-page PDF in Chromium, delayed the successful Studio page-delete result by 12 seconds. The Undo banner stayed absent before the updated document loaded; after the resulting 9-page document rendered, the Undo button remained visible and enabled for another 12 seconds. Clicking it restored the original 10-page document. There were zero page exceptions. This verifies the undo window begins after deletion/reload completes rather than expiring during the operation. Evidence: `browser-id43-slow-delete-undo.json`, `id43-slow-delete-undo.png`, harness `browser_id43_slow_delete_undo.py`.


## Continuation: ID 41 PDF to Markdown processing budget

Added an explicit 480-second bound for long PDF-to-Markdown conversion through `run_converter_with_timeout`; the operation does not retry automatically and suggests splitting into page ranges if the budget is exceeded. The existing 4.98 MB / 69-page project `notes-69page.pdf` was uploaded through the visible `/pdf-to-markdown` route twice. Both runs returned HTTP 202, downloaded 130,305-byte Markdown in 4.7–5.3 seconds, contained exactly 69 generated page sections and first/last-page content, did not leak the job identifier, and produced no page errors. A focused test verifies the budget and timeout metadata. Evidence: `browser-id41-markdown-69page.json`, `id41-markdown-round1.png`, `id41-markdown-round2.png`; test `tests/test_launch_audit_v23.py::test_pdf_to_markdown_uses_a_bounded_long_document_budget`.

Full suite after this change: 511 passed twice in `pytest-cont-id41-markdown-run1.log` and `pytest-cont-id41-markdown-run2.log`, each with four deprecation warnings.


## Continuation: ID 50 Developer API copy

The rendered `/developers` page now has a single “Copy Snippet” label and the intro has a space between “API keys” and the parenthesized `sk_live_...` example. Verified the rendered text in Chromium and added a focused server HTML regression test. Evidence: `browser-id327-330-331-332-339.json`; test `tests/test_launch_audit_v23.py::test_developer_api_copy_has_one_copy_label_and_spaces_before_key_example`.


## Continuation: ID 38 combobox and progress states

Shortened the Split all-pages select label to “All 10 pages as PDFs (ZIP)” and the SSC preset to “SSC Photo (3.5×4.5 cm · 20–50 KB).” Chromium measured each label against the actual option field width at 390 and 1366 px; both fit. It also exercised Exam Resizer, Flatten, and Sign processing states; the progress bar was indeterminate with “Processing” status and no fabricated percent, and there were no page errors. ID 38 also mentions guessed-slug 404s, but the extracted source truncates before listing those paths, so that portion remains open pending the exact paths. Evidence: `browser-id38-options-progress.json`; harness `browser_id38_options_progress.py`.


ID 38 guessed-slug follow-up: added canonical redirects for `/resize-photo` and `/photo-resize` → `/resize-image-dimensions`, `/compress-photo` → `/compress-image-online`, and `/add-page-numbers` → `/add-page-numbers-to-pdf`. In two Chromium rounds, all four followed to the expected page and title; scanning Tool Desk card anchors found none of those stale paths. Focused route alias tests pass. Evidence: `browser-id38-legacy-slugs.json`, tests `test_132_181_route_aliases_resolve` and `test_common_guessed_tool_slugs_redirect_to_canonical_pages`.


Full suite after ID 38 changes passed twice: 516 tests in `pytest-cont-id38-full-run1.log` and 516 in `pytest-cont-id38-full-run2.log`, each with four deprecation warnings.


## Continuation: ID 40 plan-name consistency

The pricing page and the account/client views used inconsistent names for the exam and student plans. Standardized the public pricing titles and the exam account label to the billing catalog: Free, Exam Pass, Student & Educator, and All-In-One Pro & Developer. Two independent Chromium page loads rendered all four exact names and reported zero page errors. The targeted regression test compares every pricing card name against `public_pricing_catalog()` and checks the client account label. Evidence: `browser-id40-plan-names.json`, two screenshots, and `tests/test_launch_audit_v23.py::test_public_plan_names_match_billing_catalog_across_pricing_and_account_views`.

## Continuation: IDs 44 and 46 AI banner and quota copy

Chromium at 390 px and 1366 px opened AI Intelligence and confirmed the obsolete claim that the PDF and full chat history are saved in this browser is absent. In the same rounds the Tool Desk sidebar displayed “Operations Today” and the live guest usage count; Settings distinguished Free daily operations from paid per-file size and batch limits. The contradictory “Unlimited · 500 MB · 100 files” phrase was absent, with zero browser page errors. Evidence: `browser-id44-46-ai-quota-copy.json`, `id44-46-390.png`, `id44-46-1366.png`; focused regression test `tests/test_launch_audit_v23.py::test_ai_workspace_and_quota_copy_avoid_outdated_storage_and_limit_claims`.

## Continuation: IDs 28, 29, and 42 scope review

ID 28: the current 44-operation Chromium catalog contains content-checked Merge, PDF-to-JPG, Protect, and Fill Form downloads. OCR could not run on this host, so the output-content item remains partial. ID 29 remains partial: the earlier v23 browser rounds verify isolated guest quota and valid-password Unlock, and Cashfree order creation has mocked tests; this does not cover live checkout, every guest flow, production TLS, or a built production Docker image. ID 42 remains partial: moved the primary chat/upload card before the How-To explainer at viewport widths through 900px; desktop keeps its existing reference order. Two real Chromium rounds at 320×740, 390×844, and 820×1180 measured chat at y=212 (AI topbar ends y=200), confirmed the upload control is above the fixed mobile navigation, uploaded a one-page PDF and observed the loaded-document bar, and found no horizontal overflow or page errors. Two 1366×900 checks confirmed the desktop how-to-before-chat ordering remains unchanged. The prior 44-route/four-width matrix still passes. Rendered v23 PDF page 61: it names screenshot 5 but contains no embedded reference image and truncates the design description after 'clean …'. Keep the exact all-view redesign partial rather than guessing from incomplete requirements. Evidence: `browser-id42-local-ai-layout-round1.json`, `browser-id42-local-ai-layout-round2.json`, `browser_id42_local_ai_layout.py`, `source-id42-page61.png`, `web/assets/styles.css` (`styles.css?v=51`).

## Continuation: IDs 51, 52, 53, 55, and 56 layout and waitlist checks

At 1104 px, Chromium verified the Settings Storage & Privacy secondary label stays within its selected card, the paid Student plan's sidebar quota reads “Operations Today / No daily operation cap” without overflow, and each Windows/macOS/Linux/Android/iOS “Join Waitlist” action selects that platform and leaves the signup form visible. The AI Chat empty prompt is fully below its header, but the checklist's after-Clear/document-still-present case remains untested (ID 52 stays partial). A 67-page PDF loaded in Studio at 1104 px; the toolbar and Export button remained visible at their initial positions. The scroll action did not establish the original scrolled screenshot state, so ID 53 remains open. Evidence: `browser-id51-52-53-55-56.json`, `id51-52-53-55-56-1104.png`, `browser-id53-studio-header-scroll.json`, `id53-studio-header-before-scroll.png`, `id53-studio-header-after-scroll.png`.

ID 52 follow-up: two isolated Chromium contexts each uploaded a one-page PDF through AI Intelligence, confirmed its active document was visible, clicked Clear, and verified the active document bar was hidden, the page-citation empty state was restored, and the PDF's unique text marker was absent from the workspace. No page errors. Evidence: `browser-id52-ai-clear-document.json`, `id52-ai-clear-round1.png`, `id52-ai-clear-round2.png`.

## Continuation: ID 72 mobile View in Studio scroll reset

In two 390×844 Chromium rounds, ran Merge using Local processing with two real one-page PDFs, scrolled to the result at window scroll 1986 px, and clicked “View in Studio.” The transition reset the window to y=0, loaded both merged pages, and kept the Studio toolbar and Export control within the viewport. No browser page errors. Evidence: `browser-id72-mobile-view-studio-scroll.json`, `id72-mobile-result-round1.png`, `id72-mobile-studio-round1.png`, and the round 2 screenshots.

## Continuation: ID 73 Studio export after responsive resize

Reproduced a control restoration failure after resizing Studio from 390 px to desktop: the Export group had been moved to a mobile slot, while the resize selector only searched its former direct parent. Updated `placeStudioControl` to recover the node from its mobile slot, return it to its desktop origin, and use `moveBefore()` when supported with the existing append/insert fallback. Two Chromium rounds loaded a five-page PDF at 390×844, focused Export, resized to 1366×900, navigated through pages 4 and 5, and verified focus remained on Export. Both output downloads parsed as five-page PDFs and contained every unique source marker. `node --check web/assets/app.js` passed; browser evidence: `browser-id73-export-after-resize.json`, `id73-resize-round1.png`, `id73-resize-round2.png`; harness `browser_id73_export_after_resize.py`.

## Continuation: ID 77 mobile Studio page actions

Reproduced the clipping at 390×844: in Organize mode, the Resize, Earlier, Later, and OCR controls overflowed to the right beyond the mobile panel. Changed the Organizer action groups to wrap into rows and let the batch panel scroll vertically only when its contents exceed the available space. Chromium then measured all four 44 px controls within the viewport and action panel, the action row had no horizontal overflow, and the Zoom selector showed 100% rather than a truncated value. Zero browser page errors. Evidence: `browser-id77-mobile-studio-page-actions.json`, `id77-mobile-studio-actions.png`; harness `browser_id77_mobile_studio_page_actions.py`.

## Continuation: ID 80 mobile Settings width

At both 320 px and 390 px, authenticated Chromium measured the Settings page and all five tabs. The page and tab strip fit within the viewport with no horizontal overflow, every tab button fit its label and accepted a click, and there were zero page errors. Evidence: `browser-id80-mobile-settings.json`, `id80-settings-320.png`, and `id80-settings-390.png`; harness `browser_id80_mobile_settings_overflow.py`.

## Continuation: IDs 82 and 84 first-paint and Escape behavior

ID 82: all nine reported tool routes returned HTTP 200 and had substantive `.seo-content` on `DOMContentLoaded`; no route displayed a “Loading … details” placeholder immediately or after 250 ms. ID 84: the mobile sidebar closed on Escape and reset `aria-expanded` to false. When the Upgrade and Auth overlays were both open, first Escape closed only Auth and left Upgrade visible; second Escape closed Upgrade. No page errors. Evidence: `browser-id82-tool-details-first-paint.json`, `browser-id84-escape-overlay-stack.json`, `id84-mobile-drawer-after-escape.png`, `id84-overlays-after-first-escape.png`.

ID 85/87 mobile follow-up: on the Merge result card at 390 px, two rounds measured Download File, View in Studio, Process Another File, and All Tools within the viewport and confirmed none were covered; the run button was already checked against the bottom bar at 320/390/820 px in IDs 340/341. Follow-up rounds exercised actual Split and Rotate outputs at 320×844 and 390×844: ZIP pages and rotated PDF text/orientation were checked; all result actions fit, stayed unobscured, and the success toast overlapped neither Run nor the bottom bar. The 38 px Download File control was raised to 44 px and cache-busted as styles.css?v=50. This closes the result-card/toast cases locally. The same earlier rounds measured all four bottom-navigation labels at 11 px, closing ID 87. Evidence: `browser-id85-mobile-result-cards.json`, `browser_id85_mobile_result_cards.py`, `browser-id72-mobile-view-studio-scroll.json`, `browser-p0-340-341-mobile-layout.json`.


ID 92 New Page: two fresh Chromium contexts uploaded and rendered a one-page synthetic source PDF. Clicking New Page opened the confirmation dialog. Cancel left the source page count/canvas and selected file intact. Confirm rendered a single 596×842 A4 canvas. Reload returned to the normal empty Studio (`0` pages), not a failed zero-byte PDF, and showed no Studio error, toast, page exception, or console error. Evidence: `browser-id92-new-page-confirmation.json`, `id92-blank-page-round1.png`, `id92-blank-page-round2.png`; harness `browser_id92_new_page_confirmation.py`.


ID 119 Studio Organize mobile: at 390×844 in two fresh Chromium contexts, uploaded a five-page synthetic PDF, selected Organize, verified `.studio-pages-open`, and measured the visible thumbnail panel at x=8/y=345/w=374/h=300 with five page cards. The Pages drawer control closed it; no page errors. Evidence: `browser-id119-mobile-organize.json`, `id119-organize-mobile-round1.png`, `id119-organize-mobile-round2.png`; harness `browser_id119_mobile_organize.py`.


ID 104 Cloud Import auto-open: Chromium repeated actual PDF selection twice each on `/compress-pdf` and `/pdf-to-text`. On all four route/context combinations, `#cloud-modal` remained hidden while `cloud-modal-check.pdf` appeared in the selected-file list. No page errors. Evidence: `browser-id104-cloud-import-auto-open.json` and route screenshots; harness `browser_id104_cloud_autoopen.py`.


ID 115 Feedback widget: in two 390×844 Chromium contexts, measured the launcher against the final visible Tool Desk card and Studio zoom selector; neither overlapped. Open Auth and Upgrade backdrops caused `#pp-feedback-container` to compute as `display:none`. No page errors. Evidence: `browser-id115-feedback-overlap.json`, `id115-widget-studio-round1.png`, `id115-widget-studio-round2.png`; harness `browser_id115_feedback_overlap.py`. The test enabled the launcher explicitly because guest sessions do not meet the widget's signed-in prompt condition.


ID 123 local downloads: in two clean Chromium contexts, merged two marker PDFs with browser-local processing. Result metadata showed `merged-PDF.pdf · 998 B`, and the Download link remained visible for re-download. Each downloaded file parsed as a two-page PDF with both markers. No page errors. Evidence: `browser-id123-local-download-result.json`, `id123-local-merge-round1.png`, `id123-local-merge-round2.png`; harness `browser_id123_local_download_result.py`.


ID 126 standalone security entry points: in two Chromium rounds per route, uploaded `audit.pdf` on `/protect-pdf` and `/unlock-pdf`, clicked Open Security Audit & Sanitize, and confirmed the modal opened on the Audit tab. `window.PaperplaneSecurityForms.currentFile.name` was `audit.pdf` for all four cases; no page errors. Evidence: `browser-id126-security-entrypoints.json`; harness and screenshots.

ID 125 Advanced Studio toolbar: at 1920×1080, two Chromium runs measured the toolbar at 80px high; primary row controls fit within the viewport without horizontal overflow, while annotate tools occupy a second 36px row. Since the reported request asks for smaller tools and the full toolbar still spans two rows, left PARTIAL. Evidence: `browser-id125-studio-toolbar-geometry.json`, screenshots.


ID 139 Available Tools sidebar: two fresh Chromium rounds covered `/apps`, `/download`, `/privacy`, `/terms`, and `/mask-aadhaar-card-online`. Each returned 200; seven sidebar tool entries appeared on first paint and remained after 1.1 seconds. No page errors. Evidence: `browser-id139-sidebar-tools-deep-routes.json`, `id139-sidebar-deep-routes-round1.png`, `id139-sidebar-deep-routes-round2.png`; harness `browser_id139_sidebar_routes.py`.


P0 full browser rerun: after correcting Studio light-theme control foreground behavior and making the contrast probe wait for the theme state, local Chromium completed all 60 checks with zero page errors. ID 137 switched Dark→Light on the responsive Studio flow, verified the toolbar foreground and canvas colors, and verified persistence after reload. Evidence: `browser-p0.json`; `browser_p0.py`; CSS `styles.css?v=30`.


ID 127 Tool Desk links/routes: two local Chromium rounds confirmed all 41 tool cards render as distinct `<a href>` links and every canonical route returned HTTP 200. `/scan-pdf` redirects to `/scan-to-pdf`; `/tools` and `/all-tools` redirect to `/tool-desk` (301). No page errors. Evidence: `browser-id127-tool-card-routes.json`, `id127-tool-card-links-round1.png`, `id127-tool-card-links-round2.png`; test `test_tool_directory_aliases_redirect_to_canonical_pages` passed.


ID 128 Feedback lifecycle: two isolated signed-in synthetic accounts checked first-time launcher visibility. In one context, dismiss hid the launcher and persisted an account-scoped flag; Settings > Privacy reopened the form. In the second, selecting rating 4/Idea and submitting a synthetic comment returned HTTP 200 from the local feedback endpoint; the launcher hid after submit, and Settings > Privacy reopened it. No page errors. Evidence: `browser-id128-feedback-lifecycle.json`, `id128-feedback-settings-round1.png`; harness `browser_id128_feedback_lifecycle.py`.


ID 129 duplicate Sanitize action: two browser rounds uploaded a synthetic PDF through `/protect-pdf` and `/unlock-pdf`, opened Security Audit & Sanitize, selected the Audit tab, and counted the pane actions. Exactly one visible “Sanitize Document Now” button appeared in all four cases; no page errors. Evidence: `browser-id129-sanitize-action-count.json`, `id129-sanitize-dialog-round1.png`, round2; harness `browser_id129_sanitize_button.py`.


ID 131 1104px sidebar clipping: at 1104×760 in two Chromium rounds, loaded `/download` and `/developers`. The download heading began at x=347; the developer Limits & Reset card began at x=867.5; both were fully in bounds to x=1104, did not intersect the sidebar (x=0..270), document width stayed 1104, and there were no page errors. Evidence: `browser-id131-1104-sidebar-layout.json`, `id131-1104-layout-round1.png`, round2; harness `browser_id131_1104_layout.py`.


ID 135 tool limits copy: in two Chromium rounds, `/summarize-pdf` displayed “PDF files up to 50 MB each on Free and 500 MB each on paid plans · This tool processes 1 file per run”; `/mask-aadhaar-card-online` displayed the same size limits for PDFs and images and one file per run. No Merge mention or truncation; both included a Pricing limits link and had no page errors. Evidence: `browser-id135-tool-specific-limits.json`; harness `browser_id135_limits_copy.py`.


ID 142 search grammar: at 390×844, two local Chromium rounds searched “translate”. The live label read “1 tool found for “translate”” and the result was one `/translate-pdf` link; no page errors. Evidence: `browser-id142-search-singular.json`, `id142-search-grammar-round1.png`, round2; harness `browser_id142_search_grammar.py`.


ID 143 Developer banner copy: two Chromium runs at 1104×760 loaded `/developers`; the rendered banner ended with “dedicated API keys (sk_live_...)” and did not contain “keys(”. No page errors. Evidence: `browser-id143-developer-banner-spacing.json`, `id143-developer-banner-round1.png`, round2; harness `browser_id143_banner_spacing.py`.


ID 144 custom 404 navigation: the server-rendered unknown-route page now includes a responsive top navigation for Tool Desk, Studio, AI Intelligence, and Pricing. In two Chromium rounds at 390px and 1366px, the route retained HTTP 404, all mobile links fit within the viewport, document width matched viewport width, and no page errors occurred. Evidence: `browser-id144-404-navigation.json`, `id144-404-mobile-round1.png`, round2; `test_html_404_page_has_responsive_workspace_navigation` passed.


ID 145 empty uploader strip: in two browser rounds, inspected `/merge-pdf`, `/compress-pdf`, and `/rotate-pdf` before file selection. For each, `#file-list` had 0px height, zero children, no text, and no background spacer; its 14px gap beneath the dropzone was the only separation. No page errors. Evidence: `browser-id145-empty-uploader-space.json`, screenshots; harness `browser_id145_empty_uploader.py`.


ID 146 Translate disabled CTA: the isolated local environment reports its Translate provider unavailable. For the exact no-file CTA state, a controlled in-browser override marked the UI operation available, then Chromium rendered “Select files to continue” while disabled. At 390×844 in two rounds, foreground #5e6f72 on #f8faf9 yielded 5.02:1 contrast and opacity 1; no page errors. This controlled check does not establish a provider-backed enabled operation. Evidence: `browser-id146-translate-cta-contrast.json`, screenshots; harness `browser_id146_translate_cta.py`.


ID 147 inconsistent Feedback mounting: fixed prompt visibility so a prior `seen` flag no longer hides it on subsequent page loads; submitted/dismissed account flags still suppress it. Two signed-in synthetic account runs at 390×844 checked `/tool-desk`, `/scan-to-pdf`, `/merge-pdf`, and `/settings`; all four returned 200 and had the widget in DOM and visible. Dismissing then navigating to Merge kept the launcher hidden. No page errors. Evidence: `browser-id147-feedback-across-routes.json`, `id147-feedback-settings-round1.png`, round2; harness `browser_id147_feedback_routes.py`.


ID 148 Processing Mode state: two browser rounds checked local mode initially across Merge/Split, switched to Server, then loaded Rotate and Settings > Privacy (all unchecked with stored `server`), switched back to Local in Settings, then loaded Remove (checked with stored `local`). No page errors. Evidence: `browser-id148-processing-mode-persistence.json`, `id148-processing-mode-round1.png`, round2; harness `browser_id148_processing_mode.py`.


ID 156 Split mode label/output: two local Chromium rounds uploaded a 3-page marker PDF and selected “All 3 pages as PDFs (ZIP)”. Each download was `split-pages.zip` with page-1.pdf/page-2.pdf/page-3.pdf; every member parsed as one page with the matching page marker, in order. No page errors. Evidence: `browser-id156-split-label-output.json`, `id156-split-all-pages-round1.png`, round2; harness `browser_id156_split_mode.py`.


ID 157 AI welcome: two clean Chromium rounds sampled 150 ms, 1 s, and 2.5 s after page entry. All six samples had exactly one welcome container and heading, zero `.ai-message` greeting duplicates, and no page errors. Evidence: `browser-id157-ai-welcome-count.json`, `id157-ai-welcome-round1.png`, `id157-ai-welcome-round2.png`.

ID 159 Home first paint: two clean Chromium rounds sampled at DOMContentLoaded and at 100 ms, 500 ms, 1.5 s, and 3 s. No visible “Loading tools…” text, width overflow, or browser page errors appeared; each returned HTTP 200. Evidence: `browser-id159-home-first-paint.json`, `id159-home-first-paint-round1.png`, `id159-home-first-paint-round2.png`.


ID 162 Photo Resize 50%: two Chromium runs uploaded a 120×80 PNG with the 50% value retained in the form and downloaded valid 60×40 JPEGs. No browser page errors. Evidence: `browser-id162-resize-50-percent.json`, `id162-resize-50-round1.png`, `id162-resize-50-round2.png`.

ID 163 local Merge progress: the fixed progress renderer now labels local stages “Read files locally”, “Process in browser”, “Prepare output”, and “Ready”; server mode uses upload/server/download labels. Two local Chromium runs performed Merge, observed those local labels and no “Stream Upload”, then downloaded a two-page PDF containing both source text markers. No page errors. Evidence: `browser-id163-local-merge-progress-copy.json`, `id163-local-merge-progress-round1.png`, round2; `web/assets/app.js` (`app.js?v=38`).

After the ID 163 JavaScript change, `node --check web/assets/app.js` and `py_compile` passed; the full Python suite passed twice with 520 tests and four existing deprecation warnings each. Logs: `pytest-cont-id163-run1.log`, `pytest-cont-id163-run2.log`.


ID 158 “Process Another File”: in two Chromium rounds on `/merge-pdf`, clicked the result action, verified the result panel hid and file queue cleared, then uploaded a different pair and completed a second content-checked Merge. Both outputs were valid two-page PDFs with the correct respective marker pairs; no page errors. Evidence: `browser-id158-process-another-workflow.json`, `id158-process-another-round1.png`, round2. The action intentionally retains the selected tool, but does not navigate/reload into a loop or re-trigger the old result.


ID 160 Settings entry-point consistency: Chromium reproduced a 27-character Storage & Privacy mismatch: the modal said Local Processing was the default for five operations, while `/settings` said only four tools were available. Updated shared preference-aware copy and refresh it when opening/mounting Settings. Two Chromium rounds compared Account, Appearance, Billing, API, and Privacy on both entry points under Local and Server defaults; all tab text matched in all cases, with mode-accurate local/server copy and no page errors. Evidence: `browser-id160-settings-entrypoints.json`; `id160-{modal,page}-{local,server}-round{1,2}.png`.


ID 164 Studio signature warning: two Chromium rounds placed a typed signature on the first page and confirmed the editor dirty state. A reload triggered the native `beforeunload` confirmation both times; after accepting, the unsaved mark was absent. No page errors. Evidence: `browser-id164-signature-beforeunload.json`.

ID 165 Photo Resize preset retention: two Chromium runs selected Passport before uploading a 600×400 PNG; selection remained Passport after upload, and each downloaded JPEG was independently opened at 350×450. No page errors. Evidence: `browser-id165-photo-preset-retained.json`.

ID 166 Page Organizer local processing: two Chromium runs confirmed the Local Processing toggle, reordered a three-page marker PDF to 3,1,2, and content-checked matching output order. The runs made zero `/api/jobs` requests and had no page errors. Evidence: `browser-id166-organize-client-side.json`.

ID 176 stale toast/breadcrumb: after creating a visible toast on Merge, two Chromium runs selected Rotate through the sidebar; the toast disappeared and the breadcrumb immediately updated to Rotate PDF. Added stale-toast clearing on operation changes; no page errors. Evidence: `browser-id176-toast-breadcrumb-navigation.json`; `web/assets/app.js` (`app.js?v=42`).

ID 178 Photo & Exam navigation: two mobile Chromium rounds expanded the sidebar and selected Photo & Exam; the Photo filter and four Photo cards were visible, the AI view remained hidden, and no browser errors occurred. Evidence: `browser-id178-photo-suite-selection.json`.


After the ID 160 Settings entry-point copy change, `node --check web/assets/app.js` and `py_compile` passed. The full suite passed twice: 520 tests each, with four existing deprecation warnings. Logs: `pytest-cont-id160-run1.log`, `pytest-cont-id160-run2.log`.


ID 172 steps with explanatory body copy: changed SEO How-it-works cards to include cautious, control-accurate guidance; added three explanatory steps to the Tool Desk and the Apps waitlist. Chromium loaded all 44 tool routes at 390 and 820px (88 views), asserted three visible step bodies per tool, and checked no horizontal overflow. Tool Desk and Apps waitlist step copy also passed. No page errors. Evidence: `browser-id172-step-body-responsive.json`; screenshots `id172-download-waitlist-390.png`, `id172-tool-desk-820.png`.
ID 183 Home privacy claim and footer; ID 189 tablet navigation: changed pricing copy that promised “100% locally” to accurately say browser processing runs locally when Local Processing is selected, added a regression assertion, and used Chromium in two rounds to verify the footer and processing-language state. The same rounds visited all 44 tool routes at 820px and 1024px (176 route/viewport checks): 820px displayed one mobile topbar, hamburger, off-canvas sidebar and bottom workspace bar; 1024px displayed desktop navigation; neither width overflowed and there were no page errors. Evidence: `browser-id183-189.json`, `browser_id183_189.py`, `id183-home-390-round*.png`, `id189-tool-desk-*-round*.png`.

ID 188 Mask Aadhaar image upload: in two local Chromium contexts, uploaded the same synthetic 950×210 PNG containing a spaced 12-digit test number through `/mask-aadhaar-card-online`; the browser input advertised PDF/JPEG/PNG/WebP, each operation returned HTTP 200 and a valid PNG download. Pixel checks confirmed the first eight digits were blacked out and the last four were unchanged; no page errors. Evidence: `browser-id188-aadhaar-image.json`, `browser_id188_aadhaar_image.py`, `id188-aadhaar-image-round*.png`. The image support was already present in the current code; this closes the stale report claim with current end-to-end evidence.

ID 190 Feedback pill vs primary CTA: a signed-in Chromium reproduction on `/merge-pdf` at 390×844 confirmed the Feedback launcher intersected the enabled Run button. Raised the launcher 54px above the mobile navigation strip and bumped the asset URL. Two fresh signed-in rounds measured no intersection and completed the Merge action; both downloaded PDFs were parsed and their source marker verified. No page errors. Evidence: `browser-id190-feedback-cta.json`, `browser_id190_feedback_cta.py`, `id190-feedback-cta-round*.png`.

ID 191 Photo Merge grid regression: reproduced the exact 4× 2400×1800 input case twice in Chromium using the Grid layout. Each output decoded as 4800×3600 JPEG; pixel samples verified the four distinct input colors in the expected 2×2 cell positions, with no page errors. Added a non-uniform-size grid unit regression. Evidence: `browser-id191-variable-grid.json`, `browser_id191_variable_grid.py`, `id191-grid-round*.png`, and `test_merge_photos_grid_uses_distinct_row_and_column_extents`.

ID 192 plan labels/pricing: two local Chromium rounds opened the Upgrade modal and compared every displayed price to `/api/billing/status`. Values matched the current catalog (Free ₹0, Exam Pass ₹19, Student & Educator ₹49, All-In-One Pro & Developer ₹299); sidebar and topbar said “View plans”; old “Pro Power User”, ₹250, and ₹750 copy was absent. Removed an obsolete CSS comment that named the retired legacy prices; no browser errors. Evidence: `browser-id192-pricing-catalog.json`, `browser_id192_pricing_catalog.py`, `id192-pricing-round*.png`.

ID 193 Studio quota-blocked export: in two Chromium rounds, loaded a synthetic one-page PDF in Studio and intercepted the export API with a controlled structured HTTP 402 `TIER_LIMIT_REACHED` response. Both rounds displayed the readable quota message in the Upgrade modal; no `[object Object]` string or page error appeared. Evidence: `browser-id193-quota-export.json`, `browser_id193_quota_export.py`, `id193-studio-quota-round*.png`.

ID 194 Photo Compress 50 KB target: a 428,615-byte, 1200×900 high-detail JPEG reproduced the oversized-output condition when compressed by quality alone. Updated the compressor to retry with proportional downscaling whenever the target remains unmet. Two Chromium runs produced valid 960×720 JPEGs of 48,415 bytes for the 50 KB target; downloads decoded successfully and had no browser errors. Added unit regression. Evidence: `browser-id194-exact-photo-size.json`, `browser_id194_exact_photo_size.py`, `id194-50kb-round*.png`, `test_compress_photo_reduces_dimensions_when_quality_alone_misses_target`.

ID 195 Photo Resize empty inputs: in two Chromium contexts on `/resize-image-dimensions`, uploaded a real test PNG with the Custom preset and all width/height/scale inputs empty. The Run action stayed disabled with the “Enter a size or scale” message; a programmatic click produced no result and zero `/api/jobs` submissions. No page errors. Evidence: `browser-id195-resize-validation.json`, `browser_id195_resize_requires_dimensions.py`, `id195-resize-validation-round*.png`.

ID 196 Master Audit #17 copy/polish set: two local Chromium rounds removed page 2 from a three-page PDF and verified `removed-pages.pdf` plus page markers 1 and 3; Split’s 12-page placeholder was `e.g. 1-3, 5, 8-12`; the Photo Resize upload accept list was JPEG/PNG/WebP; the admin console Logout button’s fetch returned 200, cleared sessionStorage, returned to sign-in, and the revoked token returned 401. Admin logout used a fresh temporary local server/session in each round; no live admin access occurred. Evidence: `browser-id196-copy-polish.json`, `browser_id196_copy_polish.py`, `browser-id196-admin-logout.json`, `browser_id196_admin_logout.py`.

ID 200 Admin Last Active: two isolated local server rounds used separate synthetic accounts, visited Paperplane while signed in, and then opened the admin console with a fresh synthetic owner session. The user row displayed a non-empty localized Last Active timestamp, and the users API returned a positive `last_active_at` value for each; no browser errors. Evidence: `browser-id200-admin-last-active.json`, `browser_id200_admin_last_active.py`, `id200-admin-last-active-round*.png`.

ID 201 Admin login location: ran the existing controlled regression for `_lookup_admin_location`: a private loopback address returns no location; a public address returns only city, region, and country from a supplied GeoIP database. The admin interface labels the column “Approximate location”. Exact device GPS and the production GeoIP database were not verified; no precise location collection was introduced. This checklist requirement remains PARTIAL because IP geolocation cannot establish an exact physical location.

ID 213 mobile result panels and Studio export filename: reproduced Protect’s Download link at y=1094 on a 390×844 viewport. Updated result handling to scroll the result card into view on narrow screens. Two browser rounds ran Protect, Unlock, and Sign; each Download link fit in the viewport and each output was content/structure checked. Also changed Studio Export’s success toast to include the actual output filename; two rounds verified both browser download name and toast name against a valid one-page exported PDF. Evidence: `browser-id213-mobile-download-visibility.json`, `browser_id213_mobile_download_visibility.py`, `browser-id213-studio-export-name.json`, `browser_id213_studio_export_name.py`.

IDs 214–218 current-code retest: Chromium rendered the workspace at 390×844. The command palette had category labels only and no API search results (215); all ten Page Organizer labels fit without overlapping arrows (216); a controlled reload marker produced a filename-specific retry message (217). AI Intelligence restored a real 10-page PDF after reload, hid the empty state, and rendered one document greeting in each of two rounds (218). This also confirms local mobile viewport browser tests are available (214). Evidence: `browser-ids214-218.json`, `browser-id218-ai-restore-race.json` and corresponding scripts/screenshots.

ID 222: two 390×844 Chromium rounds verified Log In remains visible in the topbar, and the guest profile in the mobile drawer opens Settings with visible Sign In/Create Account actions; Sign In opens the auth modal without horizontal overflow. Evidence: `browser-id222-mobile-signin.json` and screenshots.

ID 223: initial Protect → View in Studio reproduction failed. Root cause was a race: switching to Studio started restoration of an old saved document while the protected result was being loaded. Changed the handoff to skip saved-document restoration for that switch and passed the entered password only to the in-memory PDF.js load. Two Chromium rounds verified the protected output PDF rendered, its encrypted source marker remained present, and the password was not stored in session storage. Evidence: `browser-id223-protect-studio-handoff.json` and screenshots.

ID 224: current local Chrome runs did not reproduce the historical toast overlap. Content-checked four-page Merge downloads at 1366×900 and 390×844 showed no intersection between toast and result actions; Protect/Unlock/Sign downloads at 390×844 also showed no intersection in two rounds. Marked locally fixed based on current geometry; retain live retest after deployment. Evidence: `browser-id224-download-toast-overlap.json`, `browser-id213-mobile-download-visibility.json`, and screenshots.

ID 225: reproduced a displayed Summarize error and removed the selected source. Before the fix the stale result stayed visible. Clearing the result and persisting the empty session on file removal resolves it; two Chromium rounds confirmed the result panel, file rows, and metadata clear and Run stays disabled. Evidence: `browser-id225-remove-file-error.json`.

ID 227: `/crop-pdf` displays the corrected SEO lead copy in two Chromium rounds; no page errors. Evidence: `browser-id227-crop-copy.json`.

ID 228: controlled Cloud Import of a one-page PDF displayed “1 page” (singular) in two rounds. Evidence: `browser-id228-cloud-import-plural.json`.

ID 229: selecting Passport populated width/height as 350×450 before and after upload; both downloaded JPEGs decoded at 350×450. Evidence: `browser-id229-passport-fields.json`.

ID 231: four `/faq` questions and answers match the homepage FAQ. Chromium parity check and the `test_faq_workspace_matches_the_four_home_page_faqs` regression passed. Evidence: `browser-id231-faq-parity.json`.

ID 232: controlled Legacy Pro rendering hides the Settings upgrade button in two Chromium rounds. Evidence: `browser-id232-legacy-pro-settings.json`.

ID 233: pricing feature copy changed to “Document Stamps & Watermarks.” ID 234: plan badges are inside each card boundary in two rounds. Evidence: `browser-ids233-234-pricing.json`.

ID 235: two free-account Chromium sessions navigated five tool routes each with usage resolved to 0 / 10. A controlled 503 during quota refresh resolves to “Usage unavailable” in two rounds instead of leaving “Checking usage…”. Evidence: `browser-id235-quota-navigation.json`, `browser-id235-quota-failure.json`.

ID 236: Merge file hint exposes “Merge supports up to 100 PDF files per run” in two rounds. ID 239: `/history` explains no saved history and the footer link says “Temporary results”; both confirmed in two rounds. Evidence: `browser-ids236-239-copy-history.json`.

ID 245: corrected Merge SEO content to match the plain ordered file list: files merge in add order; users remove and add again to change that order. Two Chromium rounds confirmed the lead, steps, and FAQ no longer promise unavailable thumbnails/reordering. Added server-rendered regression. Evidence: `browser-id245-merge-copy.json`.

ID 248: two 390×844 Chromium rounds on `/pricing` confirmed the mobile pill reads “Pricing”, fits the available width, and remains inside the viewport. Evidence: `browser-id248-pricing-pill.json`.

ID 253: two local browser runs uploaded 2400×1800 image scans with Original 200 DPI selected. Each output PDF page measured 864×648 pt, independently parsed with PyMuPDF; no browser errors. Evidence: `browser-id253-scan-dpi.json`.

ID 254: the HTML to PDF catalog now accurately says the URL form does not accept pasted HTML. Two browser runs submitted loopback URLs and displayed `Security Guard: Access to host '127.0.0.1' is forbidden.` Evidence: `browser-id254-html-url.json`.

ID 255: two Chromium runs left the Photo Compress target at its initial 100 KB value, downloaded and decoded valid JPEGs, and measured 101,201 bytes (within 100 KiB) both times. Evidence: `browser-id255-default-photo-target.json`.

ID 257: with a one-page PDF loaded in Studio, two Chromium rounds opened Digital Signatures and remained at `/studio`; no page errors. Evidence: `browser-id257-signature-modal.json`.

ID 260: two browser sweeps confirmed `/resize-photo`, `/photo-resize`, `/compress-photo`, and `/add-page-numbers` redirect to canonical routes; no matching obsolete links were present on home. Evidence: `browser-id260-legacy-aliases.json`.

ID 261: footer now renders `Version <running app version>` from FastAPI's configured release version (`PAPERPLANE_RELEASE_VERSION`, default 2.0.0). Two browser rounds show Version 2.0.0; added a server-rendered assertion. Evidence: `browser-id261-app-version.json`.

ID 263/264: current Scan to PDF copy does not promise deskewing and its page-size selector is available; JPG to PDF copy does not promise page-size controls its form lacks. Two Chromium rounds each; no page errors. Evidence: `browser-ids263-264-copy.json`.

ID 265: added a semantically labeled AI Intelligence guide with three accurate steps. Chromium checked desktop, 390 px mobile, and 320 px narrow layouts twice; no horizontal overflow or page errors. ID 266: added explicit browser-PDF availability while native apps are pending and verified the existing waitlist steps at the same widths. The 320 px browser run also found footer-left overflow (336 px document width); wrapping footer copy fixed it, and the re-run has no overflow. Evidence: `browser-ids265-266-howto.json`.

ID 270: added `renderTranslationResult` and a View in Studio action that passes the translated PDF blob into Studio while skipping stale document restoration. Two controlled translation-result Chromium runs opened and rendered the one-page PDF in Studio with no page errors. Evidence: `browser-id270-translation-studio.json`.

ID 272/273: two runs seeded an uploaded temporary file and Studio as the prior view. The reload notice names the unavailable temporary PDF and appears only once; it clears on the next tool navigation. Loading `/` now remains at the Tool Desk rather than auto-switching back to Studio. Evidence: `browser-ids272-273-navigation.json`.

Self-found responsive bug: Apps waitlist at 320 px had a 336 px document width, caused by the unwrapped footer metadata row. Added narrow-screen wrapping and re-ran AI and Apps pages at 320/390/1366 px in two rounds; all fit and had no browser errors. Evidence: `browser-ids265-266-howto.json`.


ID 122 heavy pages: two Chrome rounds with 4× CPU throttling covered home, Compress PDF, Organize PDF, Grayscale PDF, Excel to PDF, and Studio (12 navigations). All returned 200, had no page errors or tab crashes, and fit the desktop viewport. DOMContentLoaded ranged 438–2,385 ms; longest observed main-thread task was 460 ms on the home page. This did not reproduce the reported freeze, but it leaves meaningful main-thread work and does not verify low-end mobile or heavy-document export. Evidence: `browser-id122-heavy-pages.json`.

ID 124 copy nits: two clean Chromium rounds opened `/merge-pdf` and `/html-to-pdf`. Merge's initial hint showed the plan file size and “Merge supports up to 100 PDF files per run”; HTML-to-PDF showed public HTTP/HTTPS URL input and “No file upload required,” without claiming PDF upload. Zero page errors. Evidence: `browser-id124-copy-ux.json`, `id124-copy-round1.png`, `id124-copy-round2.png`.

Latest full-suite rerun after the ID 122/124 browser checks: 552 passed with four warnings in each run (95.64s and 90.64s); logs `pytest-cont-id122-124-run1.log` and `pytest-cont-id122-124-run2.log`.


ID 125: compacted wide-desktop Studio controls via a min-width:1200px rule (25px tool buttons, 13px icons). Two 1920×1080 Chromium runs measured the full toolbar at 76px versus the earlier 80px and had no page errors or horizontal overflow. At 390px, the page remained 390px wide and visible tool targets remained 48px high. Evidence: browser-id125-studio-toolbar-geometry.json, browser-id125-mobile-geometry.json, and screenshots.


IDs 130/132/133/134: two local Chromium rounds verified direct /settings renders the Settings page with five tabs and a working Privacy pane; /dashboard redirects to /tool-desk; /history, /faq and /feedback render expected content; and /download waitlist form is visible within 273/288 ms and remains after 20 seconds. Zero page errors. Evidence: browser-ids130-134-routes-waitlist.json.

ID 136: found one stale 100/day free workflow claim on /developers while runtime quota is 10/day. Replaced the literal with the server-rendered FREE_DAILY placeholder and added a page regression. Two Chromium rounds across Home, FAQ, Terms, Settings, Pricing, Developers, and AI Intelligence found no stale 100/250 operations-per-day text; Developers displays 10 operations/day.

ID 138: /ai-intelligence returned 200 and displayed the AI Intelligence workspace in both Chrome rounds. Evidence for IDs 136/138: browser-ids136-138-quota-ai-routes.json and ids136-138-round*.png.


ID 140: pre-fix browser sweep reproduced an auth-pending profile card hidden at DOMContentLoaded on /apps and /faq, with the profile appearing after 1.1 seconds. Updated the auth-pending/restoring styling to retain the card frame and conceal unresolved name/plan fields. Two Chromium rounds across /apps, /download, /privacy, /terms, and /faq now show the card immediately and after hydration, with no browser errors. Guest identity was verified; signed-in Pro hydration remains unverified. Evidence: browser-id140-sidebar-profile.json (before), browser-id140-sidebar-profile-fixed.json (after), screenshots.


ID 150: downloaded the exact 20,597-byte public orimi pdf-test.pdf; PyMuPDF sees an unencrypted one-page PDF, while PyPDF sets is_encrypted but decrypts with an empty password. Two real Chromium server-mode rounds each completed Merge (two pages with original text) and Rotate (one page, 90 degrees), with content-checked downloads, no password warning, and no browser errors. Evidence: orimi-pdf-test.pdf, browser-id150-orimi-server-workflows.json, id150-orimi-browser-round*.png. Recheck deployed server after release because the earlier failure was production-only.


ID 149: two Chromium rounds on /merge-photos-online uploaded four unique 1200×800 photos, selected Grid, and downloaded merged-photos.jpg. Each output was 2400×1600; color samples in all four quadrants matched their respective source images. No page errors. The first harness pass confirmed the default layout is vertical stacking; the reproduction was corrected to explicitly select Grid as the prior report required. Evidence: browser-id149-photo-merge-content.json and id149-photo-merge-round*.png.


ID 151: with a seeded local student_pro session, two Chromium rounds covered Home, Compress PDF, and Settings. The signed-in Pro state was confirmed on each route. No visible ad container, SPONSORED copy, Google/AdSense network request, or page error appeared. Evidence: browser-id151-pro-ad-visibility.json and id151-pro-ad-round*.png.


ID 152: exercised all four photo tools in two Chromium rounds (Exam Resizer, Photo Compress, 50% Resize, and 2-image Grid Merge). Content-checked JPEG downloads measured 350×450, 1200×800, 600×400, and 2400×800 respectively. The browser made no /api/jobs file-processing requests and raised no page errors. Evidence: browser-id152-photo-local-processing.json and id152-photo-local-round*.png. First attempted assertion expected 4-image dimensions while only 2 source files were queued; corrected the harness expectation and completed both rounds.


ID 155: aligned static browser-processing support copy in sidebar and Settings to cover Merge, Split/extract, Remove, Rotate, Page Organizer, and photo tools. Two Chrome rounds checked six representative routes; the local toggle remained enabled and each tool page stated that files stay on device and are not uploaded. Settings states photo tools always run in browser. No page errors. Evidence: browser-id155-processing-copy-consistency.json and id155-processing-copy-round*.png. Added a rendered-copy regression test.


ID 173: updated verified missing-control claims: PDF-to-Text FAQ now directs page subsets through Split / extract; PDF-to-JPG intro states every page is exported; Compare description says plain-text report; Metadata description/FAQ names only title, author, and subject fields. Two Chromium rounds across Rotate, PDF-to-Text, PDF-to-JPG, Compare, and Metadata verified rendered steps against available controls. No page errors. The 44-route copy audit remains partial. Evidence: browser-id173-controls-copy-audit.json. Added API-content regression test.


ID 174: two 1920×999 Chromium runs loaded a 10-page PDF. The first page rendered; no phantom Page 1 loading state appeared. Seven offscreen pages remained lazy placeholders until scrolled into view. Sequential scrolling the internal canvas caused pages 1–10 to render; the last page was reachable within the scroller although the outer document stayed fixed to viewport height. The default annotation mode/Pan tool state did not change. Zero page errors. Evidence: browser-id174-studio-state.json, browser-id174-studio-sequential-scroll.json and screenshots.


IDs 185–186: in two fresh Chromium contexts, loaded Merge, toggled Browser Processing off and on through its visible slider, and confirmed preference storage, checkbox state, and accessible mode copy stayed consistent after updateButton synchronization. Submitted a five-page source PDF locally, waited for a Blob result, then navigated away to FAQ; both navigations returned HTTP 200 and completed in 0.135s and 0.129s with visible content and no page errors. Neither report reproduced; current behavior verified. Evidence: `browser-ids185-186.json`, `browser_ids185_186.py`.

ID 187: revisited two rounds of the local photo suite matrix; Exam Photo & Signature Resizer exported a decoded 350×450 JPEG and no `/api/jobs` requests were made across any photo workflow. Confirms this exam-specific operation runs browser-side rather than spending server quota. Evidence: `browser-id152-photo-local-processing.json`, `browser_id152_photo_local_processing.py`.

IDs 197–198: seeded two independent authenticated sessions; each signed out through the actual Settings UI. `/api/auth/me` returned `authenticated:false`, auth cookie and last-auth email key were absent, Guest Explorer displayed immediately and after full reload, and the reopened Settings pane showed Sign in. Zero page errors. Evidence: `browser-ids197-198.json`, `browser_ids197_198.py`.


IDs 206, 208, 209, 211: current browser evidence confirms browser-local Merge generated a Blob and the tab navigated without freezing. Prior two-round local sweeps verify one-time/no-renewal copy across Pricing/Terms/FAQ/Billing, aligned current plan names across Pricing/Settings, and matching local/server-processing preference scope across six supported tool pages and Settings. Evidence: browser-ids185-186.json, browser-ids74-81-83-policies.json, browser-id183-189.json, browser-id192-pricing-catalog.json, browser-id155-processing-copy-consistency.json.


IDs 202–204: two clean local admin-console browser runs used seeded test identities. For each, set the disposable user to Exam Pass and reset only that user's usage; both endpoints returned 200 and UI rendered the changed plan. The admin sessions panel rendered count 1. Focused pytest tests additionally verify two configured superadmin accounts can authenticate independently and one can revoke the targeted other session, plus plan/usage update targeting and audit logging. Browser logout-other was not exercised with two concurrent sessions; live OTP email delivery is unverified. Evidence: browser-ids202-204-admin-actions.json and `pytest-admin-202-204.log`.


ID 219: two Chromium uploads of the audit workbook completed Excel to PDF. Downloaded outputs each parsed as a one-page PDF (2,013 bytes, 122 text characters) with `AUDIT_OFFICE_EXCEL_OUTPUT`; no browser errors. Evidence: browser-id219-excel-download.json, browser_id219_excel_download.py, id219-excel-output-round*.pdf.


ID 210: reproduced the reported Studio page-order workflow at 1920×1080. In two rounds, the Later and Earlier buttons were visible, within the viewport, and received mouse clicks. Downloaded editor PDFs showed the order changed from Alpha/Beta/Gamma to Alpha/Gamma/Beta, then back to Alpha/Beta/Gamma. No browser errors. Evidence: browser-id210-studio-reorder-buttons.json, browser_id210_studio_reorder_buttons.py, id210-reordered-round*.pdf.


ID 220: Windows app host reports the PDF/A Ghostscript dependency unavailable. WSL Ghostscript 10.02.1 ran the PDF/A conversion command against a clean synthetic one-page PDF and produced a 7,371-byte output. PyMuPDF found PDF/A part 1 XMP, an OutputIntent array with GTS_PDFA1 and a destination profile, Ghostscript producer metadata, one page, and retained source text. The exact public `orimi-pdf-test.pdf` has a non-printing annotation and Ghostscript correctly rejected it for PDF/A. Docker engine and an independent veraPDF-style validator were unavailable; status PARTIAL. Evidence: id220-wsl-gs.pdf, id220-clean-source.pdf, id220_generate_wsl.sh.


Current full-suite confirmation after the latest audit/harness updates: 556 passed, 4 warnings in 96.35s and 556 passed, 4 warnings in 92.84s. Logs: `pytest-cont-current-run1.log`, `pytest-cont-current-run2.log`.


ID 202: seeded both configured owner sessions in the isolated local app, opened the admin sessions panel in Chromium, and clicked the other session's Log out button. The count fell from 2 to 1; the target session received 401 while the acting owner's session remained 200. No page errors. Evidence: browser-id202-two-admin-revoke.json, browser_id202_two_admin_revoke.py, id202-two-admin-sessions.png.


ID 230: two signed-in Chromium rounds scanned Pricing, Terms, and Settings → Plans & Billing for the stale automatic renewal footer and Legacy Pro renewal date. Neither appeared; Pricing displays one-time purchase wording. No browser errors. Evidence: browser-id230-renewal-copy.json and browser_id230_renewal_copy.py.


ID 237: v17 failure superseded by ID 49's local retry behavior. Two browser rounds captured and parsed actual Studio Export downloads after a dropped first fetch and first-attempt 503. The output is one-page PDF with expected text. Production retest remains attached to ID 49. Evidence: browser-p0-round12.json and browser-p0-round13.json.


IDs 240–241: two browser-p0 Sign runs captured one-page PDFs with signer text content-checked. Current catalog round 1 and round 2 also generated Page Numbers output from a two-page source; parsed content includes Page 1 of 2 and Page 2 of 2. Evidence: browser-p0.json and browser-catalog*.json.


ID 243: reproduced the Settings UI gap: API key creation returned 403 for Free/Student Pro but the Generate Key form was visible. The form now hides for non-API tiers and shows upgrade guidance. Two Chromium rounds verified Free and Student Pro hide it and direct creation is rejected; the API-enabled tier shows the form and successfully generates a disposable key. The evidence records no key secret. Added a focused API/UI-contract regression test. Evidence: browser-id243-api-key-tier-gate.json, browser_id243_api_key_tier_gate.py, test_developer_api_key_creation_is_tier_gated_in_ui_and_server.


Current full-suite confirmation after ID 243 implementation: 557 passed, four warnings in 105.62s, then 557 passed, four warnings in 101.53s. Evidence: pytest-id243-final-run1.log and pytest-id243-final-run2.log.


ID 118/246/296 current-source Docker/Nginx integration: one isolated production-mode app container mounted current workspace files behind the project Nginx template, using tmpfs data, synthetic secrets, a temporary localhost TLS certificate, and a private bridge network. Chromium verified HTML/current JS/API responses, HTTPS security headers, asset cache policy, hidden Nginx version, and HTTP→HTTPS redirect. Two failed logins sent distinct forged `X-Forwarded-For` values; both audit rows recorded the actual proxy-side client address `192.168.254.1`. Three failed admin step-one attempts with three different forged values returned 401/401/423, and a fourth forged value still saw the same locked status; the DB stored one 3-attempt bucket for the actual client address. All browser page-error checks passed; test containers and network were removed. IDs 118 and 246 are fixed locally; ID 296 remains partial pending live proxy-chain and audit-event retest. Evidence: `browser-id246-nginx-container-integration.json`, `browser_id246_nginx_container_integration.py`, `id246-nginx-proxy-home.png`.

ID 304 (Elite v23): two local Chromium rounds sent representative Markdown through the actual Summary Desk render function. Headings, lists, and bold text became semantic HTML; the visible text contained no raw `##`/`**`, and no page errors occurred. Evidence: `browser-id304-summary-markdown-render.json`.

ID 305 (Elite v23): uploaded the same attribution-leading PDF to Smart Metadata and AI Chat in one Chromium session. Both returned “Attention Is All You Need” as the on-page title, and Chat included the original filename; both endpoints returned 200 with no page errors. Evidence: `browser-id305-chat-metadata-consistency.json`.

ID 306 (Elite v23): two real Chromium runs deleted one page from a 69-page PDF. The UI showed “Deleting 1 page(s)…”, the page count reached 68 in 1.159s and 1.087s, and no page errors occurred. No artificial delay was injected in these measurements. Evidence: `browser-id306-studio-delete-69-pages.json`.

ID 307 (Elite v23): two real Chromium Protect → Unlock flows downloaded the protected output and then unlocked it from the in-memory file in the same modal/session, without selecting the downloaded file again. The encrypted intermediate and decrypted output were content-checked; unlock returned HTTP 200 and no page errors occurred. Evidence: `browser-id307-protect-unlock-same-session.json`.

ID 310 (Elite v23): corrected the SSC photo preset to treat the listed KB ceiling as decimal (50,000 bytes), with the same decimal unit for the minimum and final validation. Two actual Chromium downloads were valid 350×450 JPEGs at 49,982 bytes / 48.8 KB, under the published maximum; no browser errors. Evidence: `browser-id325-exam-resizer-stability.json`, two rounds.

IDs 311–313 responsive follow-up: two Chromium rounds measured Settings at 820px, Studio at 820px, and the signature dialog at 390px. Settings bounds were x=112–708 with document width 820; the canvas was visible below the toolbar; the signature dialog stayed within x=36–354 and the page stayed 390px wide. No page errors. The old tablet sidebar obstruction and signature dialog clipping were not reproduced. Physical-device touch/safe-area behavior remains unverified for the broader Studio mobile issue. Evidence: `browser-id311-312-313-mobile-layout.json`.

Full-suite check after the ID 310 decimal-KB implementation: `python -m pytest -q` passed 561 tests with 4 existing deprecation warnings in 105.24s, then passed 561 tests with 4 warnings in 101.26s. Logs: `pytest-id310-final-run1.log`, `pytest-id310-final-run2.log`.

ID 308 (Elite v23): current browser app converted a mixed-content PDF containing editable text, a vector-bordered table, and an embedded image to DOCX twice. Download inspection found the title/body paragraphs, a real Word 3×3 table with all six data cells and headers, and an embedded `word/media/image1.jpg`; both downloads were 38,255 bytes with no page errors. The Round 12 6.34 MB original fixture was unavailable, so this verifies a controlled equivalent, not that exact source file. Evidence: `browser-id308-word-mixed-page-fidelity.json`.

ID 299: in two local Chromium rounds, checked `/api/billing/status` as both guest and authenticated user (four responses total). Every response returned 200 and contained no `cashfree_order_id` or `order_id`; no browser errors. Evidence: `browser-id299-billing-status-disclosure.json`.

ID 2 follow-up: reproduced a provider failure in the 69-page Summary route with the local AI provider unconfigured. Added an extractive fallback regression for a failed middle section, which exposed that the fallback kept only each page's first line. Changed it to retain every eligible extracted line per page. Focused test passed; two actual Chromium rounds then uploaded 69-page PDFs and verified HTTP 200, explicit Offline Analysis badge, the page-24 decision, the page-69 final condition, and all 69 citations, with no page errors. Evidence: `browser-id2-69page-provider-failure-fallback.json`; `test_large_summary_chunk_failure_falls_back_with_all_section_lines_and_citations`. Provider-backed synthesis and live provider reliability remain unverified.

Full suite after the ID 2 fallback change: 562 passed, 4 warnings in 133.17s and 562 passed, 4 warnings in 147.75s. Logs: `pytest-id2-fallback-run1.log`, `pytest-id2-fallback-run2.log`.

Additional live issue found: `/merge-pdf` returns 200 but serves stale `app.js?v=22` and `editor.js?v=13` while the current source versions are `app.js?v=68` and `editor.js?v=14`. In real Chrome the live `#file-input` had no `multiple` attribute (so two-file selection was rejected), and a one-file test did not expose the download link within 60 seconds. This confirms deployment drift; local current-source success does not prove the live service. No deploy was performed. Evidence: `browser-live-deploy-drift.json`, `browser_live_smoke.py`.

Docker runtime follow-up for IDs 25/220 and OCR: built and ran the isolated current application image. Chromium content-checked browser downloads for 5-page Merge and Split, then PDF/A-1b and OCR. PDF/A output has the expected source text, `pdfaid:part=1`, and dereferenced `/GTS_PDFA1` OutputIntent. A 300-DPI, image-only scanned golden PDF with zero source text gained the expected OCR text (`PAPERPLANE OCR GOLDEN CHECK`, `Invoice 54821`, `Total: $124.50`) in the downloaded one-page PDF. No page errors. Evidence: `browser-docker-runtime-smoke.json`, `docker-runtime-verification.json`, `ocr-golden-source.pdf`; image metadata and health in `docker-runtime-verification.json`.

ID 78: the conflicting result-handoff claim was retested in the current code. Two Chromium runs handed translated output into Studio; the broader two-round local matrix handed Merge, Rotate, Split, and Remove results into Studio, rendered them, and retained content markers after reload. Evidence: `browser-id270-translation-studio.json`, `browser-id342-local-pdf-studio-handoff.json`.

ID 79: verified the existing no-history decision on current routes. Two browser rounds confirm `/history` clearly says jobs are not saved and the footer calls results temporary. Evidence: `browser-ids236-239-copy-history.json`.

ID 47: current Studio reorder behavior meets the mouse-click criterion. Two Chromium rounds clicked the visible Later/Earlier controls, checked they were the hit targets, and content-parsed the reordered then restored PDF. Evidence: `browser-id210-studio-reorder-buttons.json`, `browser_id210_studio_reorder_buttons.py`.

ID 48: reproduced the reported Studio Duplicate operation in the current local app. Two Chromium rounds duplicated a one-page PDF; downloaded/editor PDF bytes parsed as two pages and both retained the original marker, with no page errors. Evidence: `browser-id48-studio-duplicate.json`, `browser_id48_studio_duplicate.py`.

ID 4 live follow-up: the public 5-page TotPDF sample imported successfully on the deployed site through both `/api/cloud/sync` and the real Cloud Import modal in two Chromium rounds. Each UI round showed `Imported totpdf-sample-5-pages.pdf · 0.00 MB · 5 pages`, one file row with the expected filename, and no page errors. A second current W3C direct PDF URL also returned a valid one-page PDF. The older path embedded in the checklist currently returns upstream HTTP 404. The exact owner Drive link is not present in this workspace; prior v23 evidence for it was `image/png`, not a PDF, so item stays PARTIAL. Fixture: `totpdf-sample-5-pages.pdf` (3,785 bytes, 5 pages). Evidence: `browser-live-id4-cloud-import.json`.


## ID 100 — short mobile drawer viewport

The existing phone layout evidence used an 844px-tall viewport and did not exercise the reported short-height laptop/mobile case. Started the current local app and ran two independent Chrome contexts at 390×500. Opened the mobile menu, scrolled the sidebar to its bottom, checked profile and settings gear bounds against viewport height, and opened Settings via the gear. The profile and gear stayed visible (gear 48×48) in both rounds; no page errors. Evidence: `browser-id100-mobile-drawer-viewport.json`, `browser_id100_mobile_drawer_viewport.py`.


## ID 99 — attached PDF with neutral question

Created a one-page source with Item A=100, Item B=200, Item C=300. In two fresh Chromium contexts, attached it to AI Chat and asked only “What is the value for Item B?”—without document-reference wording. Both answers included the source value 200, showed one Page 1 citation and “Local document extract · AI provider is disabled,” and had no page errors. Evidence: `browser-id99-neutral-question-attached-pdf.json`, `browser_id99_neutral_question_uses_attached_pdf.py`.


## ID 181 — legacy tool slugs

In two Chromium rounds, checked the raw redirect response and then navigated each alias: `/metadata`→`/pdf-metadata`, `/photo-compress` and `/compress-photos`→`/compress-image-online`, `/ai-chat`, `/chat-pdf`, and `/pdf-chat`→`/ai-pdf-chat` (which the app routes to `/ai-intelligence`). Every redirect was HTTP 301 and every final page HTTP 200, with no page errors. Evidence: `browser-id181-legacy-slug-redirects.json`, `browser_id181_legacy_slug_redirects.py`.


## ID 113 — recover a PDF with damaged xref marker

Built a one-page PDF with two unique text markers, replaced its `startxref` token with `startxxxx`, and uploaded those bytes from two fresh Chromium pages to `/api/studio/repair` in automatic mode. Both responses were HTTP 200, `X-Repair-Valid: True`, and reported one recovered page. Parsed each returned PDF with PyMuPDF and confirmed both markers remained; no browser errors. Evidence: `browser-id113-repair-damaged-xref.json`, `browser_id113_repair_damaged_xref.py`.


## ID 116 — Sanitize Document Now feedback

Loaded a PDF with custom title, author, subject, and a unique page marker in Studio. Opened More Tools → Protect & Unlock PDF → Audit & Sanitize and clicked Sanitize Document Now. Two Chromium rounds displayed “Sanitization complete,” offered the sanitized download, and delivered valid one-page PDFs preserving the marker while removing the metadata. No page errors. Evidence: `browser-id116-sanitize-feedback.json`, `browser_id116_sanitize_feedback.py`.


## ID 171 — footer on every route

Using the current 46-route copy/layout matrix, visited each route in two independent Chromium rounds. Scrolled the main page to reveal the deferred footer and checked visible state, © 2026, and at least 12 link/button controls. All 92 checks returned HTTP 200 with zero page errors. Evidence: `browser-id171-footer-all-routes.json`, `browser_id171_footer_all_routes.py`.


## ID 180 — Developer API reference version and docs links

Two fresh Chromium rounds opened `/developers`. Each showed one visible “Developer REST API v1 reference” heading, `/api/v1` base URL, no stale v2.0 label, and working Swagger, ReDoc, and OpenAPI schema responses (200). `/api-docs` returned the expected 307 redirect to `/spec/swagger`. No page errors. Evidence: `browser-id180-developer-reference.json`, `browser_id180_developer_reference.py`.


## IDs 141/177 — pricing page grid and reachable checkout controls

Reproduced four pricing tiers in one row at 1920px despite the accepted 2×2 layout. The embedded inline `auto-fit` grid style overrode the stylesheet. Removed it so the existing explicit two-column desktop grid and narrow single-column breakpoint apply. Added a regression test. Two fresh Chrome rounds confirmed 4 tiers in 2 columns at 1920×1080, no modal overlay, and all three pay buttons visible after one 400px scroll. At 390×844 the pay buttons remain within viewport after scrolling. No checkout button was clicked. Evidence: `browser-ids141-177-pricing-layout.json`, `ids141-177-pricing-round1.png`, `ids141-177-pricing-round2.png`.


## ID 154 — stale pricing text

In two Chromium rounds, inspected the full rendered `/pricing` content. Current ₹19, ₹49, and ₹299 prices were present; stale ₹750 and $299/month were absent. No checkout was initiated. Evidence: `browser-ids141-177-pricing-layout.json`.


## ID 153 — reconcile tool counts with grouped AI features

Reproduced “44 PDF TOOLS” beside only 41 Tool Desk cards. Three valid AI operations are intentionally grouped in AI Intelligence and excluded from the card grid. Changed displayed total, category counts, sidebar badges, search result count, and All filter label to include these integrated workflows while preserving one shared workspace; the note identifies Chat, Smart Metadata, and Executive Brief. Added a pytest regression. Two Chromium rounds confirmed 41 cards + 3 grouped AI workflows = 44; per-category logical counts sum to 44, sidebar category badges sum to 44, and Smart Metadata search links to AI Intelligence instead of returning an empty result. Evidence: `browser-id153-tool-count-labels.json`, `browser_id153_tool_count_labels.py`.


## ID 170 — paid user tool badge

Started an isolated local server with a disposable test user, changed only that test account to Legacy Pro, and visited all 44 operation routes in two separate Chromium rounds. All 43 actual tool pages showed “Legacy Pro · no daily operation cap”; `/ai-pdf-chat` resolved to the AI Intelligence workspace without a visible guest badge. All 88 route checks had no page errors. Evidence: `browser-id170-paid-tool-badges.json`, `browser_id170_paid_tool_badges.py`.


## IDs 61 and 300 — transactional mail sender hardening

Confirmed the dispatcher previously attempted SMTP before the configured Resend API, allowing a personal mailbox transport to take precedence over the authenticated transactional provider. Updated dispatch to prefer Resend, reject consumer mailbox From domains, and return failure when no eligible transactional provider accepts the message. Two focused regressions prove Gmail sender refusal even when providers are configured and prove Resend is selected before SMTP. A separate local app ran with synthetic Gmail From plus synthetic SMTP/Resend credentials: two Chromium signup rounds received HTTP 503, no OTP pane, no session/token, and zero page errors. Evidence: `browser-id61-consumer-sender-refused.json`, `browser_id61_consumer_sender_refused.py`. Actual inbox placement and SPF/DKIM/DMARC alignment remain a verified-domain/post-deploy check. Current full-suite evidence, including this mail change: `pytest-final-id85-run1.log`, `pytest-final-id85-run2.log`.


## Continuation: ID 323 heavy-document page rendering

Two earlier delayed-read Chromium runs verify the prior Studio PDF remains behind the loading overlay while a replacement document loads. Follow-up test generated a 69-page, 76.6 MB image-heavy PDF by repeating the available scanned page, uploaded it to the current local Studio build at 390×844 and 1366×900, and explicitly waited for content canvases on pages 4, 5, 20, and 69. Render times were 0.066–0.542 seconds; each target canvas had nonzero dimensions, document width matched its viewport, and there were no page errors. This is synthetic image-heavy coverage; the exact owner PDF and deployed app remain retest evidence. Marked FIXED LOCALLY. Evidence: `browser-id323-69-image-page-render.json`, `browser_id323_heavy_page_render.py`, and screenshots.


## Continuation: ID 45 full Studio responsive check

Two local Chromium rounds uploaded a real one-page PDF at 320×740, 360×800, 390×844, 820×1180, 1024×768, 1104×760, 1366×900, and 1920×1080. The persistent-save banner was absent, Save remained visible, toolbar height measured 76–118 px, the footer was hidden at initial scroll and visible after scrolling, and document width matched the viewport at every size. No page errors. Marked FIXED LOCALLY; this is current-source desktop Chrome viewport coverage, not physical-device evidence. Evidence: `browser-id45-responsive-studio-layout-round1.json`, `browser-id45-responsive-studio-layout-round2.json`, `browser_id45_responsive_studio_layout.py`, and screenshots.

ID 173 full-route copy sweep and corrections: two fresh Chromium rounds opened all 44 operation routes (88 views, all HTTP 200, zero page errors), recorded rendered how-to copy, SEO descriptions, and visible pre-upload form fields. The capture rechecked existing fixes and surfaced remaining claims that Word-to-PDF exposed conversion/page settings, PowerPoint-to-PDF exposed orientation/output settings, Annotate supported freehand drawings/shapes, and HTML-to-PDF offered controlled page sizing. Corrected those claims in the operation/SEO catalog and rendered step details. Focused API/content regressions and browser checks passed. The inventory remains PARTIAL because controls that mount only after file selection and the resulting downloads were not semantically tested for every route.


## Continuation: ID 343 real Deutsche Bahn 12-page PDF-to-Word

Downloaded Deutsche Bahn Group's official 355-page 2025 annual report, derived a 12-page management-report excerpt, and uploaded it through `/pdf-to-word` in two fresh local Chromium rounds. Both rounds downloaded and parsed valid DOCX files; all six sampled page markers survived, four extracted tables with 62 rows and 11 embedded images were present, and all 13 DOCX XML parts decoded successfully. No browser errors. Evidence: `browser-id343-deutschebahn-real-excerpt.json`, `browser_id343_deutschebahn_real_excerpt.py`, `fixtures/deutschebahn-2025-annual-report.pdf`, `fixtures/deutschebahn-2025-annual-report-excerpt-12p.pdf`.


## Continuation: current production Docker image catalog

Built the current source with a unique local tag, started it in production mode with four workers, safe test-only session/admin values, an isolated new named volume, and Cashfree test payments disabled. The first container start correctly failed closed because this mode requires a public HTTPS URL and session secret; after supplying dummy local values the container became healthy. Two Chromium catalog rounds against the current image each content-checked 41 downloaded operation results; SSRF blocking passed, provider-backed Summary/Translate remained honestly unavailable without credentials, and browser page errors were zero. Stopped the container after testing. Docker emitted a SecretsUsedInArgOrEnv warning for the non-secret `PAPERPLANE_REQUIRE_AUTH=false` name; `.dockerignore` excludes `.env` files and no actual secrets were sent to the build. Evidence: `docker-current-image-verification.json`, `browser-id28-current-image-catalog.json`, with output files under `docker-catalog-fixtures-current-20261118/`.


## ID 90 — current Docker image concurrency follow-up

The rebuilt four-worker production image received four simultaneous Merge submissions in each of two Chromium rounds. All eight jobs completed, returned HTTP 200 downloads, and each one-page PDF preserved the expected marker; no browser page errors. The isolated test container was stopped afterward. This verifies this local image/runtime's concurrency path; it does not establish live production traffic capacity. Evidence: `browser-id90-current-image-concurrency.json`, `browser_id90_current_image_concurrency.py`.


## ID 271 — Hindi translation download text-layer check

The deterministic fallback-provider browser sweep now checks the exact `प्लेन` and `टेस्ट` strings in every page of each downloaded ten-page Hindi PDF. Two rounds passed; PyMuPDF found both strings in all pages, source English markers were absent, and there was no replacement-character mojibake or browser error. This verifies local font embedding and downloadable text extraction, not the live provider; keep the post-deploy check outstanding. Evidence: `browser-id1-10page-rate-limit-fallback.json`, `browser_id1_10page_rate_limit_fallback.py`.


## ID 161 — available real 69-page PDF compression retest

Uploaded `C:/Users/mdham/Downloads/notes.pdf` through the local `/compress-pdf` page twice in Chromium using the 100 KB preset. Both downloaded PDFs retained 69 pages and all 92,651 extracted text characters; rendered pages differed by a mean 0.0205/255 RGB (maximum page 0.8108/255). Output size remained 5,414,364 bytes and the app displayed its warning that the target could not be reached while preserving content. Source profiling found 36 unique embedded images totaling 5,190,357 bytes and 21 embedded font programs totaling 253,127 bytes. This is distinct from the report's historical `notes_test.pdf`; the reported 5.20 MB to 89.7 KB case remains unverified against its original input. Evidence: `browser-id161-download-notes-compress.json`, `browser_id161_download_notes_compress.py`.


## ID 29 — guest checkout account gate on current Docker image

In two fresh Chromium guest contexts, opened the upgrade dialog and clicked Student Pro checkout against the current production-mode local Docker image. Each run opened the sign-in/register modal with account-required copy, sent no `/api/billing/checkout-session` request, and had zero page errors. This confirms the client-side gate only; mocked backend checkout, guest quotas/password unlock, live checkout, and production TLS remain independent checks. Evidence: `browser-id29-guest-checkout-gate.json`, `browser_id29_guest_checkout_gate.py`.


## ID 37 — local Flatten PDF Forms workflow

Added `flatten` to the browser-local supported PDF operations. The PDF worker loads the selected form, calls PDF-Lib `getForm().flatten()`, and returns `flattened.pdf`; privacy disclosures now include Flatten PDF Forms. Two complete 44-route Chromium rounds downloaded the local result from a synthetic fillable PDF, confirmed the filled Applicant value and source text were preserved, confirmed the widget was removed, and observed zero `/api/jobs` posts during the operation. Overall local processing coverage is now 11 of 41 requested tools; the ID remains PARTIAL. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, updated harness `browser_id37_id242_local_processing.py`.


## ID 357 — current source offline shell and scan retest

After the app JS/cache update, two mobile Chromium rounds on the isolated current-source server verified service-worker shell v4 and `/assets/app.js?v=78`, the install prompt lifecycle, and offline shell response HTTP 200. A camera-style scan fixture produced a parsed one-page 612×792 PDF in each round; no horizontal overflow or page errors. This validates local browser simulation and shell fallback; physical-device camera and native install remain post-deployment checks. Evidence: `browser-id357-mobile-scan-pwa.json`, `browser_id357_local_source_wrapper.py`, updated `browser_id357_mobile_scan_pwa.py`.


## ID 106 — duplicate-safe retry of accepted job submissions

Added hashed app submission idempotency records scoped to authenticated-user ID or a hash of the guest request identity. The client sends one cryptographically random key across standard `/api/jobs` retries and chunked `/commit` retries; the server replays the existing job and guest capability before charging quota or rate limits. A focused API test proves guest retry returns the same job, restores its download cookie, rejects a different guest scope, stores only one job, and never stores the raw key.

Two local Chromium scenarios injected a synthetic client-visible HTTP 502 after the backend had actually returned the accepted response: one standard upload and one 10.07 MiB image-heavy chunked upload. In both cases, the retry carried the exact key, got the same job ID with an idempotent HTTP 200, and created only one job/key record. Each output parsed as a one-page PDF, preserved its source marker, and had 90° rotation. The 502 was injected at the client safeFetch adapter; this verifies replay and retry code paths, not the live reverse proxy. Evidence: `browser-id106-idempotent-submit-retry.json`, `browser_id106_submission_retry.py`, `tests/test_launch_audit_v23.py::test_app_job_idempotency_replays_guest_job_and_rejects_other_scope`.


## ID 37 — local Fill PDF Forms

Added browser worker fill support for PDF text fields, checkboxes, dropdowns, radio groups, and option lists. The full two-round 44-route local processing harness filled the Applicant field to `LOCAL-FORM-FILLED`, downloaded a valid PDF, verified the interactive widget/value remained present, and recorded zero `/api/jobs` calls for this workflow and all 12 local workflows. The first pass revealed the frontend local dispatcher did not include textarea JSON in the worker options; although the worker succeeded in a direct probe, the UI fell back to the server. Passed the JSON from the Forms tool into the worker options and reran two clean rounds. PWA shell v7 and app asset v81 also passed the two-round offline-shell/camera-scan retest. ID 37 remains PARTIAL at 12 of 41 tools. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser-id357-mobile-scan-pwa.json`, `browser_id37_id242_local_processing.py`, `browser_id357_local_source_wrapper.py`.

## ID 37 — local Edit PDF Metadata

Added browser-worker metadata editing for Title, Author, and Subject, and return an allowlisted output metadata summary for the visible JSON panel/export. Two current-source Chromium rounds tested through the actual local Processing Mode UI: changed Title and Author, retained the original Subject and Creator, preserved page text, parsed the output PDF and JSON metadata download, and observed zero `/api/jobs` submissions. The first UI run exposed that browser-local results were not receiving the worker's metadata summary; wired that summary into the result renderer and repeated both rounds. The full 44-route harness now content-checks 13 local workflows. PWA shell v8 and app asset v82 passed two isolated current-source mobile rounds, including a parsed scan PDF and HTTP 200 offline shell. Five focused regressions passed; Python compilation, JS syntax, and CRLF-aware diff checks passed. Two subsequent full-suite runs passed 581 tests each with four existing deprecation warnings (111.87s and 116.26s); logs: `pytest-id37-metadata-run1.log`, `pytest-id37-metadata-run2.log`. ID 37 remains PARTIAL at 13 of 41 workflows. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser-id357-mobile-scan-pwa.json`, `browser_id37_id242_local_processing.py`, `browser_id357_mobile_scan_pwa.py`.


## ID 27 — narrow-width layout self-analysis

Added two local Chromium rounds across all 44 tool routes at 683px and 512px CSS viewport widths, 176 route/viewport checks total. Every route returned HTTP 200, `documentElement.scrollWidth` matched the viewport, and no visible element crossed the viewport edge. The first draft falsely counted the intentionally translated off-canvas sidebar; after restricting edge checks to visible elements intersecting the viewport, the complete repeat passed. This is zoom-equivalent responsive stress, not native browser zoom or physical-device evidence. ID 27 remains PARTIAL until the owner's M-1–M-11 handset comparison. Evidence: `browser-id27-narrow-zoom-layout.json`, `browser_id27_narrow_zoom_layout.py`.


## ID 37 — current production Docker image worker verification

Rebuilt final current tag `paperplane-v23-audit:final-current` from the time-sliced workspace; image ID `sha256:fe12cd487a4e276329db9dc2b6df26e517bb666efda59089c65fbd0eda4273a6`. Started it in production mode with four workers, test-only dummy session/admin settings, Cashfree TEST configuration without credentials, and a UID-1001 tmpfs at `/data`. The health endpoint returned HTTP 200. Local Chromium filled a real PDF AcroForm and checked Metadata PDF/JSON output as documented above. Then two further mobile Chromium rounds at 4× CPU throttle uploaded the actual 69-page `notes.pdf` into Studio, exported it, and parsed every page; both outputs retained all source text/order, contained 69 pages, measured 390px document width, and had no browser errors. Stopped the container and discarded tmpfs. No production volume or payment provider was touched. Evidence: `browser-id37-docker-worker-smoke.json`, `browser_id37_docker_worker_smoke.py`, `browser-id122-docker-studio-smoke.json`, `browser_id122_docker_studio_smoke.py`.


## ID 122 — real 69-page mobile Studio export and performance optimization

The first mobile/4× CPU test exposed a bug in the attempted batch optimization: `createStudioPageSlot` still appended through an out-of-scope `stack` binding, so the page count updated but no page canvas was created. Fixed the factory to accept an append target, then time-sliced construction into 16-slot batches with zero-delay yields, computed the initial width once, and committed one `DocumentFragment` only if the load epoch remains current. With the real 5,456,746-byte, 69-page `C:/Users/mdham/Downloads/notes.pdf`, two 390×844 Chromium 4× CPU performance rounds exported all pages and preserved text/order. Load-to-first-page: 4.21–4.60s; export: 0.73–1.17s; end-to-end: 5.49–5.67s. The longest tasks were 436–446ms, below the prior 1,096ms peak, though still above 250ms. A separate two-round check deleted page 2 and verified the live-stack fallback recreated and rendered it. No overflow or browser errors; the test also passed at 1× CPU. Bumped current app/PWA assets to v84/v10. Hardware profiling remains open. Evidence: `browser-id122-mobile-69page-studio-perf.json`, `browser-id122-mobile-69page-studio-export.json`, `browser_id122_mobile_69page_studio_export.py`, `tests/test_launch_audit_v23.py::test_studio_bulk_page_stack_uses_one_layout_measurement_and_fragment`, `browser-id357-mobile-scan-pwa.json`.

ID 37 follow-up — browser-local Page Numbers: added Page Numbers to the worker's supported operation set and wired position, format, starting page/number, and mark color through the UI dispatcher. Two fresh 44-route Chromium rounds content-checked 14 local workflows (including the generated Page Numbers PDF), with zero job posts for local operations. Separate two-round option coverage used Header-left, `{n}`, start number 7 and start page 2; it verified preserved source text, page 1 unnumbered, page 2 numbered 7, and zero API posts/page errors. Updated truthful privacy copy and cache versions to app v85, shell v11, PDF runtime v15, worker v17. The focused regression passed as part of fresh full suite run 1 (582 passed, 109.57s, 4 existing deprecation warnings); run 2 is underway. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser-id37-page-number-options.json`, `pytest-final-run1.log`.

Final v23 continuation verification: after Page Numbers integration, full suite passed twice at 582 tests (109.57s and 106.21s; 4 existing Starlette/httpx warnings each). JS syntax, Python compilation, and CRLF-aware diff checks passed. Rebuilt local production-mode Docker image `sha256:3f46c6172318c2edaad5377fbab595e30e90ef729a46d786a363db24d4904fcb`; four-worker health was `ok`. Chromium content-checked Fill Forms and Metadata PDF/JSON output in the image with zero API job posts and no page errors. Container used synthetic-only credentials and tmpfs, then stopped. Docker lint flagged `PAPERPLANE_REQUIRE_AUTH=false` as a sensitive-looking environment variable name; no secret value was included. Evidence: `pytest-final-run1.log`, `pytest-final-run2.log`, `browser-id37-docker-worker-smoke.json`.

ID 122 Studio follow-up: current organizer thumbnail rendering now builds its card DOM in bounded time slices using `scheduler.yield()` with `setTimeout(0)` fallback and rejects stale render epochs. Two 4× CPU mobile Chromium rounds waited for all 69 organizer cards, exercised Select All/Invert and page-slot fallback, and verified all 69 exported pages' text/order with no overflow/page errors. Organizer construction measured 45–66ms, but full load-to-first-page was 4.63–6.21s and longest tasks were 544–961ms; this is not a verified performance improvement and remains partial. `pytest-id122-thumbnail-slicing-run1.log` passed 583 tests; run 2 underway. Evidence: `browser-id122-mobile-69page-studio-export.json`.

ID 37 follow-up — browser-local Crop PDF: added PDF-Lib crop-box changes with margin validation, connected the Crop UI fields to local worker options, disclosed the workflow in privacy/support copy, and bumped the worker/runtime/app/PWA cache versions. Two independent Chromium rounds scanned all 44 routes and content-checked 15 local workflows. The crop output preserved both page text markers and measured 270×160pt per page after margins of left 10, top 15, right 20, bottom 25 on 300×200pt pages; zero `/api/jobs` posts occurred during local operations. ID 37 remains PARTIAL (15/41 workflows; 26 remain). Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser_id37_id242_local_processing.py`.

ID 37 follow-up — browser-local Watermark PDF text: enabled text-only watermarking in the local PDF worker, using the selected color, opacity, and a contrasting outline. Registered each generated ExtGState in its page resources after the first browser run exposed a PDF-lib operator argument error. Three separate Chromium runs now downloaded valid four-page output for 0°/90°/180°/270° source pages; tests checked original markers, selectable watermark strings, rendered selected-color pixels, and centered placement, with zero server job posts and no browser errors. Image watermarks still use server processing after explicit upload consent. Cache revisions: app 93, runtime 19, worker 21, shell 20. ID 37 count is 16/41 local; 25 workflows remain. Evidence: `browser-id37-watermark-round1.json`, `browser-id37-watermark-round2.json`, `browser-id37-watermark-round3.json`, `browser_id37_local_watermark.py`.

Post-Crop full regression and production-image check: two sequential current-source full-suite runs passed 583 tests (180.08s and 150.46s, 4 existing deprecation warnings each). The initial run exposed three stale expectations for the new truthful local-processing disclosure; fixed the older tests and FAQ route so they match. Latest production-mode local Docker build `sha256:971fb2ec8c8a17df78dbccc3fb66de5db879e4e510a86b0f98e24452b754a5d6` passed four-worker `/api/health`, and Chromium content-checked Forms, Metadata PDF/JSON, and Crop output (270×160pt with text retained). Zero `/api/jobs` and page errors; tmpfs only, container stopped. Docker linter still warns about the non-secret `PAPERPLANE_REQUIRE_AUTH=false` environment variable name. Evidence: `pytest-id37-local-crop-run1.log`, `pytest-id37-local-crop-run2.log`, `browser-id37-docker-worker-smoke.json`.


Deployment hardening follow-up — Railway volume ownership: added `scripts/container_entrypoint.py` to prepare `/data` and optional `/backups` when mounted root-owned, skip symlinks, reject non-absolute/protected paths, and then drop to UID/GID 1001 before exec. A cold production-image run against a root-owned mode-0755 `/data` tmpfs showed 1001:1001 ownership and PID 1 UID 1001, returned health `ok` with four workers, and passed Chromium Forms/Metadata/Crop/Watermark downloads with zero job POSTs. Image: `sha256:077e8846fe141bbae3b9c805bb7b97f7094ffda8c5feade98b578de4699dc154`; the temporary container was stopped. First run exposed a PATH lookup mistake (`execv`); changing to `execvp` fixed it. The repo environment template now disables test payments by default. Current full suite: 584 passed twice (`pytest-id101-env-template-run1.log`, `pytest-id101-env-template-run2.log`).

ID 37 current-source repeat: two rounds of the updated 44-route/16-operation harness passed with zero route failures, all local output content checks, zero local job submissions, explicit fallback consent checks, and zero page errors. Watermark downloaded two-page PDFs retained both source markers and selectable stamp text. Evidence: `browser-id37-local-text-roundfinal1.json`, `browser-id37-local-text-roundfinal2.json`. Coverage is 16/41; 25 workflows remain.


ID 37 browser-local Compare update (2026-11-19): added a client-side selectable-text comparison path for two PDFs, producing a content-checked .txt diff without uploading source files. The UI states that browser mode does not compare layout, images, or scanned text; per-file page/character and combined-line limits plus a frontier-work budget route oversized jobs to server mode. Two current-source Chromium rounds verified filename and headers, preserved context, insertion and replacement markers, six diff reconstruction cases (empty, insertion, deletion, replacement, repeated lines, unchanged), work-limit handling, zero /api/jobs posts, and zero page errors. Focused regressions passed (4 tests). Initial full-suite run found one stale regression assertion expecting the old supported-operation set; updated the assertion and all privacy/help-copy lists to include Compare PDF text. The first rerun found two further stale cross-copy assertions (sidebar/settings support and FAQ parity); updated those references, then the full suite passed twice at 599 tests with four existing deprecation warnings (`pytest-id37-local-compare-final-run1.log`, `pytest-id37-local-compare-final-run2.log`). Evidence: browser-id37-local-compare.json, browser_id37_local_compare.py, 	ests/test_launch_audit_v23.py::test_compare_supports_browser_local_selectable_text_diff.


ID 37 current-source production-image parity (2026-11-19): rebuilt app.js v112 / shell v42 into paperplane-v23-audit:codex-current, image ID sha256:e31b7c4b3a994a49553a736601f7279a0fc42ce364219922b8e9c3b7cfd955e6. The isolated production container became healthy, ran PID 1 as UID/GID 1001, and had tmpfs /data at 1001:1001 mode 0755. Two browser rounds against this exact image repeated the Compare local-output/content checks, six sequence reconstructions, work cap, zero API job posts and no page errors. The container was stopped; no production credentials, data or payment were used. Evidence: docker-id37-local-compare-build.log, browser-id37-local-compare-docker.json.

ID 37 separate local-server evidence: two local Chromium rounds on the same final harness produced `browser-id37-local-compare-local.json`, distinct from the Docker-image rounds above. Both verified the downloadable `.txt` line diff and six reconstruction cases, with no job submissions or page errors.


Current-source regression after ID 37 local Compare: reran all 44 tool routes at 320/390/820/1366 px for two Chromium rounds (352 checks, zero failures/page errors), reran the P0 suite as round 45 (60 cases, zero page errors), and verified v42 offline shell cache/reload twice with app.js v112 and styles v54. The production image sha256:e31b7c4b3a994a49553a736601f7279a0fc42ce364219922b8e9c3b7cfd955e6 was healthy and ran UID/GID 1001; its local Compare download checks passed twice. Two current full-suite runs passed 599 tests each. The worktree remains uncommitted.


Current v112 production-image Studio regression (ID 122): exact image sha256:e31b7c4b3a994a49553a736601f7279a0fc42ce364219922b8e9c3b7cfd955e6 reached healthy status; PID 1 was UID/GID 1001. Two 390×844, DPR-3, 4× CPU Chromium runs uploaded the 69-page notes.pdf fixture and downloaded 69-page exports with exact text/order preserved, zero overflow and no page errors; end-to-end times were 6.56s and 6.44s. This verifies that the current app v112 image retained Studio functionality; it does not close ID 122's >250ms long-task target or physical-device validation. Container stopped after run. Evidence: browser-id122-docker-codex-final-v112.json.

## Current-source follow-up — ID 37 PDF-to-Markdown (2026-11-19)

The browser-local Markdown path was added for selectable text and simple structural formatting. It extracts per-page text and title, applies basic heading/list inference, and includes explicit limits. A real 69-page ML lecture PDF contains math/font glyphs that the lossy Markdown mapper must not silently corrupt; the product detects those operators and asks before server upload. A local browser run confirmed the consent dialog appears, Cancel closes it, no download is offered, and no `/api/jobs` request occurs. Two rounds passed against the 69-page source locally and two against the rebuilt production-mode Docker image. The synthetic Markdown fixture downloaded twice on each runtime and content checks passed. Docker digest: `sha256:7aa08981efb9ef04409db30c296b59fc6982bac3e8412d8c9d9279bba9bc397b`; app.js v113/shell-v43; container UID 1001, `/data` tmpfs, stopped after testing. Full pytest passed twice at 600 tests (four existing deprecation warnings each). ID 37 coverage is 24/41; 17 workflows remain server-only. Evidence files are listed in FINAL-REPORT.md.


## Latest live provider recheck — IDs 1 and 2 (2026-11-19)

On the deployed site, two Chromium rounds translated synthetic 10-page PDFs into Spanish and Hindi. All four requests returned HTTP 200; each downloaded file retained all 10 page markers, had expected target-language content on all 10 pages, contained no source-English marker, and produced zero page errors (`browser-live-id1-translation-matrix.json`). A fresh live 69-page summary run returned HTTP 200 in explicit `offline_extractive` mode, preserved the page-24 cancellation and 900000 spending cap and the page-69 deadline, cited Pages 1–69, and had zero page errors (`browser-live-id2-69page-provider.json`). This is current evidence that the live fallback works safely and the translation provider is currently responsive; provider-backed summary synthesis and sustained provider stability remain unverified.


## Latest live AI smoke — IDs 1 and 5 (2026-11-19)

A fresh public 5-page PDF smoke found Executive Brief capability advertised, but the summary API returned HTTP 200 in `offline_extractive` mode rather than provider synthesis. Spanish translation attempt 1 passed content checks (5/5 translated pages, no source phrase); attempt 2 returned honest HTTP 422 because coverage fell below the 50% safeguard. Both Hindi attempts returned HTTP 429. There were zero page errors. Evidence: `browser-live-ai.json`. Together with the independent 10-page Spanish/Hindi matrix passing all four requests, this shows provider availability is currently variable; do not mark IDs 1 or 5 as production-provider verified.


## Live retest — ID 314 summary PDF UI (2026-11-19)

The current public browser loaded `/assets/app.js?v=91` (local candidate is v113). A 69-page synthetic fixture loaded and the enabled Generate Executive Brief control sent `POST /api/ai/summarize`; the UI remained “Generating brief…” with no API response observed during the harness’s 180-second response wait. A follow-up diagnostic recorded the request, disabled button, “Generating” badge, no page errors, and the stale asset version. This does not prove whether the live backend is merely slow or stalled, and it does not exercise the local fixed UI. ID 314 stays FIXED LOCALLY, with live verification open until the current candidate is deployed and retested. Evidence: `browser-live-id314-diagnostic.json`, `browser-live-id314-diagnostic.png`; the first 180-second attempt stack was printed to the execution log, but did not save a result JSON.


## Current local regression — ID 314 Executive Brief PDF download (2026-11-19)

On the live local server at port 8501, two fresh Chromium runs uploaded the exact synthetic 69-page fixture, generated the Executive Brief, and clicked the visible Download PDF control. Both downloads opened in PyMuPDF as readable 4-page PDFs and contained the Executive Summary heading plus checked findings for source pages 1 and 69; sizes were 6,890 and 6,891 bytes, with zero browser errors. This verifies the local app.js v113 candidate; the separate public site probe loaded stale app.js v91 and did not respond within 180 seconds. Evidence: `browser-id314-summary-pdf-current-round3.json`, `browser-id314-summary-pdf-current-round4.json`.


## ID 1 implementation — bounded Retry-After handling (2026-11-19)

Self-found resilience gap: `_provider_request` retried `429`/5xx responses but truncated all upstream Retry-After hints to five seconds, regardless of a translation call's 90-second total budget. It now honors numeric or HTTP-date Retry-After up to 30 seconds and dynamically divides the remaining timeout across remaining attempts, reserving time for follow-up requests before sleeping. Focused tests passed; a fake-clock test proves a 30-second cooldown and subsequent request stay inside the 90-second budget. Two controlled local Chromium rounds injected HTTP 429 + `Retry-After: 30`, then downloaded content-checked 10-page Spanish PDFs with all 10 translated markers, no source markers, HTTP 200, and zero browser errors. Full suite passed twice at 602 tests, four existing warnings each. Rebuilt production-mode Docker image booted healthy with four workers on UID 1001 and `/data` owned by 1001. The current live provider still produced 429s in separate probes; this code change improves bounded retries but does not prove stable external provider operation. Evidence: `tests/test_ai_workflows.py::test_provider_retry_after_is_honored_within_total_timeout_budget`, `browser-id1-retry-after-ui-round1.json`, `browser-id1-retry-after-ui-round2.json`, `pytest-id1-retry-after-run1.log`, `pytest-id1-retry-after-run2.log`, `docker-id1-retry-after-runtime.json`.


## ID 37 additional browser-local workflow — PDF-to-Word (2026-11-19)

Implemented a local selectable-text PDF-to-Word path. It uses the existing 500-page/2M-character/20K-line PDF.js guard and unsupported-font/math fallback; DOCX is a standards-readable UTF-8 ZIP package with headings, paragraph text and page breaks. UI states that local output does not preserve images, exact positioning or tables; complex layouts can use the server tool. Against app.js v115, two local-server Chromium rounds and two rounds on the rebuilt production-mode Docker image downloaded DOCX files that passed ZIP integrity and Python `python-docx` parsing: 50 paragraphs, 11 page breaks, all 12 synthetic page markers, and accented text; no server job posts or page errors. The complex real Deutsche Bahn 12-page excerpt triggered the safe consent prompt twice; cancel generated zero jobs/downloads/errors. Full suite passed twice at 603 tests. Offline worker v45 cached app.js v115 and CSS v54, then served two successful offline reloads. Docker image `sha256:b9f6b9e18da777ddfa4016d5a51d090da4fac381d827778e4e6804c4bb3cf6c6` booted healthy, all application processes UID 1001, `/data` owned by UID 1001, and container removed. ID 37 coverage moves from 24/41 to 25/41; 16 other workflows remain server-only. Evidence: `browser_id37_local_pdf_to_word.py`, `browser-id37-local-pdf-to-word.json`, `browser-id37-local-pdf-to-word-docker.json`, `browser-id37-local-pdf-to-word-real-fallback.json`, `browser-id37-service-worker-v115-offline.json`, `docker-id37-word-runtime.json`, `pytest-id37-browser-word-final-run1.log`, `pytest-id37-browser-word-final-run2.log`.

ID 42 visual mobile layout regression (2026-11-19): screenshot inspection of `/ai-chat` showed a blank band between app navigation and the chat card. Browser geometry measured the empty document-context topbar at 118px on 320/390/820 CSS px (and 82px on desktop) despite no visible content. Conditional CSS now removes only the empty bar when no context/connection controls are shown. On local source and the rebuilt production Docker image, Chromium measured 0px empty bar and 12px chat gap at 320/390/820; 1366 also has a collapsed bar while its explanatory section remains visible. Uploading a synthetic 2-page PDF retains a visible 162px document strip with 12px gap, exact filename, no horizontal overflow, zero browser errors. The complete pytest suite passed twice at 604 tests.


### ID 161 follow-up — soft-mask image compression

Source inspection showed that most images in the supplied 69-page `notes.pdf` use separate soft masks and the prior implementation skipped those image streams. Updated compression to recombine base image + soft mask, downsample within preset dimensions, and replace with optimized PNG only when the combined payload shrinks. Conflicting image/mask references are skipped to avoid changing shared resources incorrectly. A deterministic synthetic regression test confirms the output retains alpha via a PDF soft mask, downsamples image dimensions, retains text, and renders within a small RGB difference. Two current local Chromium runs against the supplied file downloaded 69-page outputs of 2,820,672 bytes from 5,456,746 bytes (48.3% smaller), preserved all 92,651 text characters, mean visual difference 0.178/255, max 1.342/255, and showed the 100 KB target warning. The historical provider/live `notes_test.pdf` remains untested because that exact source is unavailable; item stays PARTIAL. Evidence: `browser-id161-download-notes-compress.json`.


ID 161 was also rerun in the rebuilt production-mode Docker image `sha256:d0352418d4c2aaf1fd1c5fb1f73a5c17c4f7050c157081015f815768e10da233`. The container became healthy and ran six Python application processes as UID 1001. Two Chrome rounds downloaded identical 2,838,978-byte outputs from the 5,456,746-byte, 69-page source; all page text/order remained exact, rendered mean RGB difference was 0.178/255 (max 1.342/255), and the 100 KB limit warning was visible. Container was stopped and removed. Evidence: `browser-id161-docker-notes-compress.json`, `docker-id161-softmask-runtime.json`.


### ID 122 follow-up - DPR 1 mobile rendering trial

Added a test-only browser init override for `devicePixelRatio=1` and ran the exact 69-page Studio flow twice at 4x CPU throttling. Each run preserved all page text/order and exported valid output. First-page readiness was 7.76s/6.20s; the 344x487 canvas contained 1,297 nonwhite pixels (visible title and author); 48/45 long tasks exceeded 50ms with maxima 475/480ms. The existing 1.5x baseline had 42/42 tasks with maxima 482/402ms and readiness 7.40s/7.08s. DPR 1 lowers sharpness and did not reliably improve responsiveness, so this was rejected as a product change. ID 122 remains PARTIAL. Evidence: `browser-id122-mobile-69page-studio-export_dpr1_trial.json`, page-one canvas screenshots.


### ID 42 live deployment recheck (2026-11-19)

Read-only Chromium at `https://paperplane.qd.je/ai-intelligence` confirmed the live origin still serves app.js v91 and styles.css v51. At 320, 390, and 820 CSS px, the document and connection controls are hidden yet the AI topbar occupies 118 px; chat begins 12 px below it. At 1366 px the same topbar is 91 px. The page returned HTTP 200 at all widths, no horizontal overflow or page errors. This reproduces the deployed visual defect and confirms the local CSS v55 fix is not yet live. Evidence: `browser-live-id42-ai-layout-2026-11-19.json`, `browser-live-ai-390-2026-11-19.png`, `browser-live-readonly-2026-11-19.json`.


### ID 258 Cashfree TEST probe recheck (2026-11-19)

The local probe ran with configured sandbox credentials, verified an unpaid INR 1.00 order by read-back, loaded the Cashfree checkout modal, and exited 0 without submitting payment. A read-only GitHub Actions API lookup found four scheduled `main` runs (Nov 15-18) all failed at the `Create unpaid test order and verify checkout drop` step. The latest run used SHA `03436d90d9fc233eedf3a614eaa5de4f520137ca`; public metadata identifies the failed probe step. Browser log access revealed the cause: GitHub Actions lacks `CASHFREE_APP_ID` and `CASHFREE_SECRET_KEY`; no values were read. ID 258 stays PARTIAL pending owner secret configuration and post-commit alert verification. Evidence: `browser-id258-local-cashfree-sandbox-probe.json`.


ID 258 code follow-up: the scheduled workflow now grants only `contents: read` plus `issues: write` and runs an alert step only after failure. `scripts/alert_cashfree_probe_failure.py` searches open issues before creating one, assigns/mentions the repository owner, and links the failed run; it never handles payment data or submits a payment. Focused mocked tests cover issue creation, deduplication, run-link construction, assignment, and least-permission wiring. The live alert was not triggered: that would require committing/pushing the change and a future failure run, which is outside this authorized task. GitHub's run-log endpoint explicitly returns 403 `Must have admin rights to Repository`; owner notification and token policy remain unverified.


## ID 2 — content-checked Executive Brief PDF download (2026-11-19)

Extended the current-source Chromium harness to click Download PDF after the 69-page offline fallback appears, save the downloaded artifact, reopen it with PyMuPDF, and verify its text rather than only the API/UI result. Two independent Chromium rounds downloaded the Executive Brief PDFs (each 4 pages, 10,203 extracted characters); both outputs retained the honest Offline Analysis disclosure, page-69 decision fact, and page-69 citation. The 390/820/1280/1920 px layout checks passed in both rounds and neither browser reported errors. The full suite passed twice at 607 tests (four existing deprecation warnings each): `pytest-id2-summary-pdf-download-run1.log`, `pytest-id2-summary-pdf-download-run2.log`. ID 2 remains PARTIAL because provider-backed synthesis has not been proven on the deployed source and the live UI still runs an older app bundle; deployment and live retest are outside this workspace task. Evidence: `browser-id2-69page-summary-download-final1.json`, `browser-id2-69page-summary-download-final2.json`, `browser_id2_69page_summary.py`, both `browser-id2-summary-download-final*.log` logs, and `id2-final1-v23-id2-69-pages_executive_brief.pdf` / `id2-final2-v23-id2-69-pages_executive_brief.pdf`.


## Additional ID 2 bug — Unicode Executive Brief PDF export (2026-11-19)

A controlled current-source browser test returned a successful Hindi/emoji summary, then reproduced `WinAnsi cannot encode` in the PDF download handler: no file downloaded and Chromium reported an uncaught page error. Updated `downloadSummaryPdf` to preserve the complete original string in a UTF-8 TXT fallback and show a clear warning whenever the built-in PDF font or runtime cannot render it. Two local Chromium rounds and two rounds on the rebuilt production-mode image downloaded TXT with the expected Hindi/emoji content, visible fallback warning and zero page errors. The regular 69-page English Executive Brief PDF also passed content checks in two local and two production-image rounds. Updated app asset to v116 and offline shell to v47; two offline browser reloads confirmed cached app.js v116 and CSS v55. Two full suites passed 607 tests each, four existing warnings per run. The isolated image `sha256:4d831e49507f4880b29502e5d1ee12788d85b63feafec240240b69e7938a1e88` was healthy with four workers and six UID-1001 Python processes, then stopped and removed. Item 2 stays PARTIAL due provider-backed and post-deployment checks. Evidence: `browser_id2_unicode_summary_pdf.py`, local/Docker `browser-id2-unicode-summary-pdf-*.json`, local/Docker `browser-id2-69page-summary-download-*.json`, `browser-id357-service-worker-v47-offline.json`, `docker-id2-summary-unicode-v116-runtime.json`, and `pytest-id2-unicode-pdf-fallback-run1.log` / `run2.log`.


## ID 258 — fail-fast sandbox-secret preflight (2026-11-19)

The scheduled Cashfree probe previously installed Playwright and Chromium before discovering the repository TEST secrets were missing. Added a credential-presence preflight before dependency installation; it emits only a generic error and exits nonzero without logging any credential value, so the existing deduplicated owner alert runs promptly. The workflow-contract regression passed. A container-shell check exercised both branches: missing vars returned exit 1 with only the generic error, and dummy TEST vars returned exit 0 without echoing either value. The full suite passed twice at 607 tests (four existing deprecation warnings each): `pytest-id258-preflight-final-run1.log`, `pytest-id258-preflight-final-run2.log`. No GitHub workflow was triggered and no issue/payment was created. ID 258 remains PARTIAL pending owner configuration of `CASHFREE_TEST_APP_ID` / `CASHFREE_TEST_SECRET_KEY`, a pushed workflow run, and verified owner notification. Evidence: `.github/workflows/cashfree-sandbox-probe.yml`, `cashfree-preflight-controlled-runtime.json`, `tests/test_launch_audit_v23.py::test_cashfree_sandbox_workflow_alerts_once_on_failure_with_minimum_permissions`.


## ID 28 — current v116 production-image catalog (2026-11-19)

Rebuilt the current source image `sha256:4d831e49507f4880b29502e5d1ee12788d85b63feafec240240b69e7938a1e88` and exercised the full 44-operation catalog with Chromium. The first broad pass reported outer-harness timeouts for Remove and PDF-to-Word after 339 seconds, although the second round completed all 41 expected outputs. Retested those two operations in two isolated rounds on the same image and then on a fresh container; all four operation attempts completed and passed content validation. Re-ran the entire catalog in a separate two-round session: both rounds completed 41 validated outputs, blocked the unsafe HTML SSRF input, reported Summary/Translate unavailable without provider credentials, and had zero browser errors. Production image health was OK, four workers active, app processes UID 1001; disposable containers were stopped and removed. The initial two timeouts were not reproduced in the targeted or full rechecks; the initial attempt remains recorded rather than hidden. Evidence: `browser-id28-v116-current-image-catalog.json`, `browser-id28-v116-current-image-catalog-recheck.json`, `browser-id28-v116-remove-word-retry.json`, both Docker runtime JSON files.


## ID 2 — real `notes.pdf` Executive Brief export (2026-11-19)

Uploaded the available 69-page `notes.pdf` through the current AI Intelligence UI on the local server and on the rebuilt production-mode Docker image, two Chromium rounds per runtime. All four requests returned 200 in `offline_extractive` mode, generated 26,000-character briefs with citations 1–69, retained source vocabulary and page-69 citation text, and had zero page errors. The real file includes ligature glyphs that the built-in PDF font cannot encode, so all four Download PDF clicks produced the exact UTF-8 TXT fallback with the explicit unsupported-font warning. Docker image `sha256:4d831e49507f4880b29502e5d1ee12788d85b63feafec240240b69e7938a1e88` was healthy with four workers and six UID-1001 Python processes; the container was stopped and removed. This verifies real-file fallback behavior locally and in the production image, but provider-backed synthesis and live deployment behavior remain unproven, so ID 2 remains PARTIAL. Evidence: `browser-id2-notes-summary-local.json`, `browser-id2-notes-summary-docker.json`, `browser_id2_notes_pdf_download.py`, `docker-id2-notes-summary-runtime.json`.


## ID 42 — fixed mobile navigation and keyboard-focus clearance (2026-11-19)

Screenshot review led to a browser regression around the persistent mobile bottom bar. Current mobile CSS now gives the document root and `.main-area` a safe-area-aware `scroll-padding-bottom` of 76px; `web/index.html` references styles.css v56 and the service-worker cache advances to v49, precaching that exact CSS URL. A controlled 80-section AI summary made the PDF download action available. Two real Chromium rounds on the local server and two on the rebuilt production-mode image checked the focused download button at 320×844, 390×844, 390×600, 820×600, and 820×432: all returned HTTP 200, had no horizontal overflow/page errors, and kept the focused target above the bottom bar. Two local offline reloads confirmed shell v49 served app.js v117 and styles.css v56 with the new 76px scroll clearance. Health reported `ok`, four workers, and six Python processes under UID 1001; the test container was stopped. The complete suite passed twice at 609 tests, with four existing Starlette/httpx warnings per run. This is a local accessibility/layout hardening; ID 42 remains partial because the owner-directed screenshot-5 reference is unavailable and production assets remain stale. Evidence: `browser-id42-fixed-nav-focus.json`, `browser-id42-fixed-nav-focus-docker.json`, `docker-id42-fixed-nav-runtime.json`, `browser-id357-service-worker-v49-offline.json`, `pytest-id42-mobile-nav-focus-run1.log`, and `pytest-id42-mobile-nav-focus-run2.log`.


## ID 27 — current stylesheet responsive recheck (2026-11-19)

After styles.css advanced to v56 for fixed mobile navigation focus clearance, re-rendered all 44 tool routes at 320, 390, 820, and 1366 CSS px for two rounds. All 352 checks returned HTTP 200 without visible horizontal overflow or page errors. Evidence: `browser-id27-current-source-scroll-guard-v56.json`. ID 27 remains partial for the separate native zoom and owner-screenshot comparisons recorded above.


## Current P0 regression sweep after mobile v56 update (2026-11-19)

The P0 Chromium harness completed round 51 against the current local source after the CSS v56 and shell v49 changes: all 60 discriminating checks passed with zero failures or browser page errors. Evidence: `browser-p0-round51.json`. This local rerun does not close the provider, deployed-live, or owner-only conditions in the relevant P0 item rows.


## ID 27 — read-only live operation-route layout sweep (2026-11-19)

Checked the live site in real Chromium, all 44 operation routes at 320, 390, 820, and 1366 CSS px over two rounds. All 352 requests returned HTTP 200; no page/body overflow, visible child overflow, topbar overlap, or page errors were observed. The live document references app.js v91 and styles.css v51. This is live-layout evidence for the currently deployed assets, not verification of the v117/v56 local candidate; native Chrome zoom and owner screenshot/physical-device comparisons remain open. Evidence: `browser-id27-live-layout-2026-11-19.json`, `browser_id27_live_layout.py`.


## ID 4 — exact owner Drive file retest (2026-11-19)

Read the exact owner Drive `/view` test link from the user-supplied v23 checklist and ran it through the live Cloud Import UI twice in separate Chromium contexts. Both API responses were HTTP 400 because Google returned `image/png`, not PDF; the UI displayed a safe error, imported zero files, and had no page errors. The link was not copied into the script, JSON evidence, or report. Current-source local P0 round 51 independently imported the direct public PDF twice with content validation and rejected this owner link twice for the same image/PDF mismatch. The correct public PDF source is still needed to verify the intended owner document. Evidence: `browser-id4-live-owner-drive-2026-11-19.json`, round-specific redacted JSONs, `browser-p0-round51.json`.

Also tested five standard `drive.google.com/uc` and `drive.usercontent.google.com/download` parameter variants against the same file through the current local safe-fetch implementation. Every variant resolved to the same `/download` endpoint and returned exactly 35,874 bytes with an `image/png` MIME type and PNG signature, not `%PDF-`; changing the URL form cannot repair the source. The file ID and owner URL were omitted from the evidence. Evidence: `browser-id4-drive-url-variants-2026-11-19.json`, `browser_id4_drive_url_variants.py`.


## ID 101 — redacted audit-artifact scan after current rechecks (2026-11-19)

The latest Gitleaks v8.24.2 run scanned the updated 14.96 MB `reports/launch-audit-v23` tree using `--no-git --redact=100`; it reported no leaks. This targeted scan did not inspect local `.env`, TLS private-key material, or Git history. Evidence: `gitleaks-id4-followup.json`.


## AI provider availability check (2026-11-19)

Imported the application's current AI configuration and checked only the boolean returned by `_current_bluesminds_api_key()`. The result was false; no provider request or credential output occurred. This explains why provider-backed local generation could not be tested in this environment. Evidence: command `python -c "import ai_engine; print('local_provider_available=' + str(bool(ai_engine._current_bluesminds_api_key())))"` returned `local_provider_available=False`.


## ID 90 — bounded live concurrent Merge check (2026-11-19)

Used four separate fresh guest Chromium contexts on the live site to submit one generated one-page PDF Merge job each at the same time. All four returned HTTP 202, completed, and downloaded HTTP 200 PDFs whose page count and unique per-context text marker were verified (4/4). No page errors occurred; no account login, real OTP, or payment was used. The check establishes a bounded concurrent live job pass, not sustained production load. The separate live login-code response-header issue was not exercised because its discriminating path would send an OTP email. Evidence: `browser-id90-live-concurrency-2026-11-19.json`, `browser_id90_live_concurrency.py`.


## Passive live HTTPS and exposure check (2026-11-19)

Repeated the read-only TLS/header check against the current live host. HTTP redirected to HTTPS, HTTPS returned 200, the certificate expires Jan 29, 2027, HSTS/CSP/nosniff/frame/referrer/permissions headers were present, and all nine common secrets/backup probes returned JSON 404. The script retained headers and status/length only, not response bodies. This is not a substitute for a full penetration test. Evidence: `security-passive-live-check.json`, `security_passive_live_check.py`.


## ID 1 — current live translation provider recheck (2026-11-19)

Re-ran the live 10-page Spanish/Hindi matrix against `https://paperplane.qd.je/` with a synthetic, non-sensitive fixture. Round 1 returned HTTP 504 with `Retry-After: 5` for both languages. In round 2, Spanish returned HTTP 200 and the downloaded PDF retained all ten expected Spanish translation markers and all ten source-page markers, with no source English left. Hindi returned HTTP 422 with only 20% block, segment, and source-character coverage; no output was offered. All four cases had zero browser page errors. The coverage rejection behaved safely; intermittent upstream availability/coverage remains, so ID 1 stays PARTIAL. No payment was attempted. Evidence: `browser-live-id1-translation-matrix.json`, `browser_live_id1_translation_matrix.py`.

The current local bounded-retry, Retry-After, failed-batch repair, and concurrency-cap regressions were then rerun: 5 passed (`pytest-id1-live-recheck-focused.log`). This supports the candidate code behavior under controlled failures, but does not upgrade the mixed live-provider outcome.


## ID 258 — current public Actions state (2026-11-19)

Fetched the repository's public GitHub Actions workflow list and the last ten run records for “Daily Cashfree sandbox checkout probe.” The four scheduled runs on Nov 15–18 all concluded failure; the latest was `44357454438` at `2026-11-18T17:19:52Z`. No newer run is available to test the uncommitted failure-alert logic. This was a read-only API request; no run, issue, payment, or secret access occurred. Evidence: `github-id258-workflow-runs-2026-11-19.json`.


## Current-source P0 Chromium rerun (2026-11-19)

Reran `python reports/launch-audit-v23/browser_p0.py` against the current local source. It completed 60 checks with no failures and no page errors (`browser-p0-round52.json`). This is local candidate evidence; it does not close live/provider/deployment or owner-only branches for the P0 items.

## Current-source full-suite and ID 122 follow-up (2026-11-19)

Two sequential `python -m pytest -q` runs on the current app.js v117 / styles.css v56 / shell v49 workspace each passed 609 tests with four existing Starlette/httpx deprecation warnings (`pytest-continuation-2026-11-19-run1.log`, `pytest-continuation-2026-11-19-run2.log`). For the ID 122 discriminating run, 390×844 Chromium at DPR 3 and 4× CPU throttle imported the real 69-page `notes.pdf`, exercised page-40 navigation, slot recovery, organizer actions, and export, then compared lazy-catalog against eager-catalog control. Both preserved page text/order and had no page errors, but maxima were 483/630ms and 468/402ms respectively; the <250ms target remains unmet. Current production-mode Docker v117 rounds also preserved 69-page text/order in 7.84s/8.34s. This is evidence of functional correctness and a reproducible performance gap; ID 122 remains PARTIAL pending responsiveness and physical-device checks.


## Final artifact scan after Watermark follow-up (2026-11-19)

Gitleaks v8.24.2 rescanned approximately 15.02 MB of current v23 audit artifacts with `--no-git --redact=100`; exit status was 0 and no leaks were found (`gitleaks-current-source-final-2.json`). Git history and ignored runtime secrets were not scanned.
## Current Docker catalog intermittent Watermark stall (2026-11-19)

On image `sha256:b3a5c5c0da22de2de0eec8a65824ef8c18be68550a4a3707e65525fc55c91d47`, one two-round 44-operation Chromium catalog run passed 41 content-checked outputs in round 1, then timed out its Watermark job after 340.67s in round 2. A direct database observation 443.3s after submission still showed `processing`, progress 20, and no error; browser page errors were zero. The same image then passed 20 isolated Watermark submissions in fresh Chromium contexts, each returning a two-page PDF with `AUDIT_WATERMARK` on both pages, and a subsequent full catalog passed 41 outputs in each of two rounds. Direct local processing of the same synthetic PDF took 0.084s. This one intermittent job stall is unresolved rather than dismissed; ID 28 remains PARTIAL. Evidence: `browser-id28-watermark-stall-observation.json`, `browser-id28-watermark-repeat.json`, latest successful `browser-id28-v117-current-image-catalog.json`.

## ID 28 current-source concurrent processing probe (2026-11-19)

Five rounds of eight concurrent synthetic 20-page Watermark jobs were run against `server.process`. All 40 outputs retained all source page markers and each unique watermark; the maximum job runtime was 2.47 seconds. The probe did not run through queued HTTP jobs and did not reproduce the previously observed processing stall. It therefore adds evidence without closing ID 28. See `repro_id28_concurrent_watermark.py` and `id28-concurrent-watermark-stress.json`.


## ID 28 queued-browser concurrency rerun (2026-11-19)

Current production-mode Docker image `sha256:b3a5c5c0da22de2de0eec8a65824ef8c18be68550a4a3707e65525fc55c91d47`, four workers, synthetic source, tmpfs storage, and no provider credentials: four Chromium rounds submitted four Watermark jobs concurrently. All 16 completed, downloaded valid two-page PDFs, preserved both source markers and their unique watermark, and raised zero browser errors. Each wave completed in 0.38–0.45s. A first eight-job upload wave received the expected rate-limit HTTP 429; the bounded test was rerun at the configured four-worker level. The intermittent historical job stall remains unexplained, so the item is not closed. Evidence: `browser-id28-concurrent-watermark.json`, `browser_id28_concurrent_watermark.py`.


## Current full-suite recheck (2026-11-19)

Following the new ID 28 audit harness, ran the current complete suite twice sequentially: 609 passed on each run, with four existing Starlette/httpx deprecation warnings per run. The second run output is captured in `pytest-id28-concurrency-followup-run2.log`. No product-source files changed during this continuation.


**Self-found DOM XSS hardening (2026-11-19):** A targeted source review found `key_prefix` from `/api/developer/keys` interpolated unescaped into HTML in both the Settings and Developer API-key lists. Both paths now use `escapeHtml`; added regression coverage and bumped app.js to v118 and PWA shell to v50. Chromium injected a synthetic `<img onerror>` prefix into both list renderers: the payload remained visible text, created zero image nodes, did not execute, and produced zero page errors. Two offline Chromium rounds then verified shell v50 loaded app.js v118 and styles.css v56 with HTTP 200 and zero page errors. The entire suite passed twice at 610 tests, four existing deprecation warnings per run (`pytest-id-security-xss-run1.log`, `pytest-id-security-xss-run2.log`). This is an extra codebase hardening fix; it does not change the v23 register counts or resolve its remaining live/owner gates. Evidence: `browser-security-api-key-prefix-xss.json`, `browser-id357-offline-v50-smoke.json`, `tests/test_launch_audit_v23.py::test_developer_api_key_prefix_is_escaped_before_html_rendering`.


**Follow-up AI extraction DOM hardening (2026-11-19):** The source review found two more provider-controlled values entering the invoice extraction HTML as raw text: line-item `quantity` and `source_pages`. Both are now encoded with `escapeHtml`; added a regression test. Real Chromium invoked the production extraction renderer with a synthetic `<img onerror>` payload in both fields: payloads remained text, zero image nodes were created, no handler ran, and the page had no errors (`browser-security-extraction-values-xss.json`). App.js is now v119 and the offline shell is v51; two offline Chromium rounds loaded the exact cached app/styles successfully (`browser-id357-offline-v51-smoke.json`). P0 browser matrix passed 60/60 with zero page errors (`browser-p0.json`). The complete suite passed twice at 611 tests, four existing warnings per run (`pytest-id-extraction-xss-run1.log`, `pytest-id-extraction-xss-run2.log`). This is extra self-found hardening and does not close the other open v23 list items or owner gates.


**Self-found authentication and extraction DOM hardening (2026-11-19, latest candidate):** Replaced password-recovery response HTML interpolation with DOM nodes and `textContent`; a development reset link is rendered only for a same-origin root URL with a `reset_token` query. Chromium verified a hostile message stays text, a `javascript:` reset URL is suppressed, and a valid same-origin synthetic reset link remains clickable; zero page errors (`browser-security-password-reset-response-xss.json`). Together with the previous API-key prefix and AI-extraction quantity/source-page escaping fixes, this hardens three independent response-rendering paths. Candidate cache versions are app.js v120 / shell v52. Two PWA offline rounds loaded v120/v52 and CSS v56 with HTTP 200; current-source P0 matrix passed 60/60, zero errors (`browser-id357-offline-v52-smoke.json`, `browser-p0.json`). Full test suite passed twice at 612 tests, with four existing deprecation warnings each (`pytest-id-reset-xss-run1.log`, `pytest-id-reset-xss-run2.log`). These extra fixes do not change the v23 list counts; the remaining PARTIAL/BLOCKED and owner/live gates remain open.


**Password recovery response safety follow-up (2026-11-19):** Removed the last identified reflected HTML sink in the forgot-password client. Server-provided status text now uses `textContent`; a development reset link is accepted only when the parsed URL is same-origin, uses the root path, and includes `reset_token`. Chromium tested hostile markup, a `javascript:` URL, and a valid same-origin token URL; hostile content remained inert and the valid link remained available. Latest app.js v120 / PWA shell v52 passed two offline Chromium reloads (HTTP 200, no errors), the current P0 matrix (60/60, no errors), and the full suite twice (612 passed each; four existing deprecation warnings). Evidence: `browser-security-password-reset-response-xss.json`, `browser-id357-offline-v52-smoke.json`, `browser-p0.json`, `pytest-id-reset-xss-run1.log`, `pytest-id-reset-xss-run2.log`.


ID 97 and ID 106 current-candidate browser follow-ups (2026-11-19): ID 97's forgot-password flow was rerun against app.js v120 twice; the generic response remained truthful, a same-origin development reset link appeared, and each password reset completed with HTTP 200 and zero page errors. No real email was sent; provider-backed delivery stays PARTIAL. ID 106's transient 502-after-acceptance scenario was rerun against current app.js v120 for standard and >10 MiB chunked uploads. Both retry loops preserved one idempotency key and one job, returned 202/200, and content-checked a valid rotated PDF with zero page errors. The live production client remains stale and the historical long-processing stall is still open. Evidence: `browser-id97-password-reset-app120-2026-11-19.json`, `browser-id106-idempotent-submit-retry-app120-2026-11-19.json`.


## 2026-11-19 — ID 122 current app.js v120 mobile rerun

The real 69-page `notes.pdf` was uploaded in two fresh local Chromium rounds at 390×844, DPR 3, with 4× CPU throttling. Both exports contained 69 pages with exact source text/order, no horizontal overflow, and zero page errors. First-page readiness was 11.13s / 8.67s; 57 / 52 long tasks exceeded 50 ms and the maxima were 857 ms / 488 ms. The Studio canvas remained 1.5× (516×730 backing pixels for 344×487 CSS pixels). Evidence: `browser-id122-mobile-69page-studio-exportcontinuation-20261119.json`.

A temporary `RenderTask.onContinue` yielding candidate used `scheduler.yield()` with `setTimeout(0)` fallback. The same flow completed with all page text/order preserved and no browser errors, but readiness was 10.74s / 8.16s and maximum long tasks were 1041 ms / 510 ms (13 / 8 tasks above 250 ms). This noisy A/B did not show a repeatable improvement; the experimental code was reverted. Evidence: `browser-id122-mobile-69page-studio-exportyieldtrial-20261119.json`.


## 2026-11-19 — Current v120 production-image browser catalog and Studio export

Built the current working tree as `paperplane-v23-audit:continuation-20261119` (image ID `sha256:41be655d8f0d2fd038327839109917c57bdaa00c17114b4d0c9b9570b28bb0cf`). An isolated production-mode container with disposable tmpfs `/data`, four workers, and dummy local-only auth/session values became healthy (`/api/health` HTTP 200); the application worker ran as UID 1001. Two mobile 69-page Studio Chromium rounds at 4× CPU slowdown downloaded 69-page PDFs preserving every source page's extracted text and order, with a visible 1.5× canvas, zero horizontal overflow, and zero browser errors (7.51s/7.61s). A separate two-round production-image catalog pass completed and content-checked 41 workflows each; the SSRF case was blocked, two provider-only operations were unavailable without credentials, and there were no browser errors. The disposable container was stopped; no persistent data volume was mounted. Evidence: `browser-id122-docker-codex-final-v120.json`, `browser-id28-v117-current-image-catalog-continuation-v120-20261119.json`.

The catalog pass did not reproduce or explain the previously observed single Watermark job stalled at 20%; keep that reliability item partial. The Studio export verifies functionality and container startup but does not meet the 250ms mobile responsiveness target or replace physical-device validation.


### ID 28 current v120 concurrent Watermark browser run

Rebuilt-image browser regression used the current v120 image digest and a disposable production-mode container. Four rounds of four simultaneous Watermark submissions completed (16/16), each returning a valid two-page PDF with the two source markers and its own unique watermark; zero browser errors. The container used disposable tmpfs and dummy local-only auth values and was removed by the harness. This does not explain the earlier isolated job that remained at 20%; keep ID 28 PARTIAL. Evidence: `browser-id28-concurrent-watermark-v120-20261119.json`, harness `browser_id28_concurrent_watermark.py`.


## 2026-11-19 — ID 122 v121 implementation, local and Docker verification

The Studio page stack created 69 slots via `innerHTML` then queried every canvas to assign the first-page ID. Replaced that per-slot parse/query path with explicit DOM construction while preserving the loading element text/role, canvas class/ARIA, page-1 ID, CSS dimensions, and page-slot markup. Four fresh local 390×844/DPR3/4× CPU Chromium rounds completed the full 69-page export flow with exact text/order, thumbnails for pages 1 and 40, select-all/invert, same-page selection, missing-slot recovery, page-40/back navigation, 390px document width, and no errors. The two run pairs measured 7.58/8.61s and 7.09/8.14s to first page; total time 14.20–14.63s (prior v120 baseline 17.02–19.26s). Each v121 run still had six tasks over 250ms; maxima were 468, 560, 579, and 806ms. Thus this is a repeatable workflow/runtime improvement, not closure of the 250ms target.

Built image `paperplane-v23-audit:domslots-v121-20261119`, sha256 `6fa1e57df6879c317849e13b8fbe49d264796f603887d1a556618bb37c5f4891`. It became healthy, reported four workers, served `/api/health` 200, and ran as UID 1001. Two mobile Chromium exports preserved exact 69-page text/order and visible canvas content, zero horizontal overflow, zero errors (13.08s / 12.10s). Shell v53 cached app.js v121 and CSS v56 and served both offline in two local and two production-image rounds (HTTP 200, zero errors). P0 matrix passed 60/60; current full suite passed twice, 612 tests each. The isolated container was stopped and removed; no persistent volume, provider credentials, or payment was used. Evidence: `browser-id122-mobile-69page-studio-exportdomslots-v121-20261119.json`, `browser-id122-mobile-69page-studio-exportdomslots-repeat-v121-20261119.json`, `browser-id122-docker-codex-final-v121.json`, `browser-id357-offline-v53-smoke.json`, `browser-id357-offline-v53-docker-smoke.json`, `browser-p0.json`, `pytest-domslots-v121-run1.log`, `pytest-domslots-v121-run2.log`.

## 2026-11-20 — Fresh full-suite rerun

Re-ran the full suite twice sequentially against the current working tree using isolated temporary data directories, dotenv disabled, credential environment removed, and no production endpoints. Both `python -m pytest -q` runs passed all 613 tests with four existing warnings (158.22s and 143.84s). This refreshes test evidence only; it does not close the outstanding partial items or change the release verdict. Evidence: `pytest-domslots-v121-run1.log`, `pytest-domslots-v121-run2.log`, `pytest-domslots-v121-summary.json`.

## 2026-11-20 — Full suite and P0 browser recheck

The full suite was run sequentially twice: 613 passed in each run, four existing warnings per run. The current local Chromium P0 harness was then rerun against a fresh isolated server: 60 checks, zero page errors. Evidence: `pytest-domslots-v121-run1.log`, `pytest-domslots-v121-run2.log`, `pytest-domslots-v121-summary.json`, `browser-p0.json`. This refreshes verification and leaves the 30 PARTIAL and 1 BLOCKED items open; it does not change the HOLD verdict.

The report/register contract test was rerun after the latest code and evidence updates: `python -m pytest -q tests/test_launch_audit_v23.py` passed 98 tests with four existing warnings.

## 2026-11-20 — Self-found admin signup-chart injection sink

Review found the admin signup chart wrote API-derived date and count values into an HTML string. Although the normal backend builds these values from timestamps and database aggregates, the rendering sink relied on that invariant. Updated the renderer to escape the date for both text and title contexts, normalize counts to finite nonnegative integers, cap display to the latest 14 points, and bumped the cache key to `admin.js?v=18`. A controlled local Chromium response injected a hostile date and count; the rendered label remained text, zero injected elements appeared, no handler executed, the bar height normalized to 6%, and the browser reported no errors. The same Chromium run checked 320/390/820/1366px widths with no document/body overflow. `node --check web/assets/admin.js` and focused pytest regressions passed. This is defense-in-depth and does not change the v23 register count. Evidence: `browser-admin-chart-xss.json`, `browser_admin_chart_xss.py`.

## 2026-11-20 — Post-fix complete-suite verification

After the admin signup-chart hardening, the full suite was run sequentially twice under the isolated, credential-stripped, dotenv-disabled harness. Both runs passed all 614 tests with four existing warnings: pytest reported 138.92s and 127.95s (harness durations 201.62s and 132.49s). Evidence: `pytest-domslots-v121-run1.log`, `pytest-domslots-v121-run2.log`, `pytest-domslots-v121-summary.json`.


## 2026-11-20 — Self-found command-palette DOM injection

- Injected hostile API-shaped operation metadata into the current-source Chromium command palette. Before the fix, operation key, label, description, and category were raw HTML interpolation points. After escaping each field, the payload was inert, generated no elements or event, ordinary entries rendered, and there were no browser errors or 390px overflow.
- Advanced app.js to v122 and service-worker shell to v55. The offline shell and CSS were confirmed cached and rendered over two offline reloads. Full P0 matrix: 60 checks, zero page errors.
- Regression and full suite evidence: `test_command_palette_escapes_operation_metadata_before_html_rendering`; two sequential complete runs passed 615 tests each with four existing warnings. See `browser-command-palette-xss.json`, `browser-id357-service-worker-v55-offline-local.json`, `browser-p0.json`, and `pytest-domslots-v122-run1.log` / `pytest-domslots-v122-run2.log`.


## 2026-11-20 — Operation catalog DOM-injection hardening

- Follow-up sink inventory found raw operation metadata in `renderSidebarTools` and `renderHomeToolsGrid` as well as the command palette. Escaped keys for data attributes and dynamic labels, descriptions, and prerequisite badges for text context.
- Current local Chromium injected hostile key/label/description/category/prerequisite markup into all three renderers; no image elements or handler execution, all expected text and controls preserved, zero page errors, and no 390px overflow (`browser-command-palette-xss.json`).
- Current candidate app.js v123 and shell v56 passed two offline reload rounds, the 60-check P0 matrix, and two complete suites of 615 passed each (four existing warnings each).


## 2026-11-20 — Selected operation label injection in Run button

- Self-analysis traced the operation label into `updateButton()` for both unavailable and normal enabled states. The label now passes through the HTML escaper. Expanded Chromium test used hostile operation metadata in both UI states, with zero injected elements or handler execution; visible hostile label remained text.
- Full regression evidence is current app.js v124/shell v57: browser injection checks passed, offline PWA reload 2/2, P0 60/60, and full pytest twice at 615 passed each with four existing warnings.


## 2026-11-20 — v124 production-mode image check

Built current source as `paperplane-v23-audit:codex-v124` (`sha256:a5df4a859eed7a2969ef601a43cb783169eadde1d33b41e322406070022d2fde`). Four-worker production container became healthy; `/api/health` was `ok`, app/workers UID 1001, `/data` and `/tmp` disposable tmpfs. Real `notes.pdf` 69-page mobile export completed twice with exact text/order, cards/page 1/page 40 thumbnails and DPR3/4× CPU layout checks, zero errors. Production-image hostile metadata was tested in four UI paths across 320/390/820/1366px, no markup execution/injected nodes or overflow. Container stopped/removed after evidence collection. No payment submitted. Artifacts: `docker-v124-runtime-smoke.json`, `browser-id122-docker-codex-final-v124.json`, `browser-command-palette-xss-docker-v124.json`.


## 2026-11-20 — Current production-image offline PWA check

The v124 Docker image cached its v57 shell and exact current app/styles/organizer assets; two Chromium contexts then disabled networking and navigated to `/` successfully (HTTP 200, CSS applied, 390px layout, zero errors). Exact image was disposed after the run. This supplements the local-server offline checks but does not prove native Android/iOS install or camera behavior. Evidence: `browser-v124-docker-offline-pwa.json`.

## 2026-11-20 — Self-found server watermark image guard

- Reproduced the server watermark path receiving client-provided base64 image data and converting to RGBA without checking compressed byte length or decoded pixel dimensions.
- Added strict PNG/JPEG data-URL and base64 checks, a 25 MiB encoded/decoded byte bound before temporary file creation, and a 20-megapixel decoder bound before RGBA conversion.
- Focused tests passed for over-limit pixels, over-limit bytes, invalid base64, unsupported MIME and a comma-missing truncated data URL. Final `python -m pytest -q` passes are recorded as 617 tests each, four existing deprecation warnings each (`pytest-watermark-guard-run1.log`, 134.12s; `pytest-watermark-guard-run2.log`, 131.68s).
- Chromium exercised two separate local-server rounds. Each round confirmed an adversarial 24MP PNG and a truncated data URL fail with actionable job errors, then uploaded a valid PNG image watermark, downloaded HTTP 200, and verified source PDF text plus embedded watermark color pixels. Zero page errors. Evidence: `browser_id361_watermark_image_guard.py`, `browser-id361-watermark-image-guard.json`.
- This hardening may reduce memory spikes for huge malicious/accidental watermarks, but it does not establish the cause of the historically observed ID 28 20% stall; that item remains PARTIAL pending its discriminating reproduction/performance test.
- Rebuilt `paperplane-v23-audit:codex-v126` (`sha256:8194d2cc2d76145f3550f7a053cced5ed6b347e5a4d63b3531f59d0b0068a6fc`); the disposable production-mode image reached healthy status and Chromium repeated both invalid-input rejections plus the content-checked successful download in two rounds with zero errors (`browser-id361-watermark-image-guard-docker-v126.json`). Container and tmpfs data were removed.
- ID 28 current-image discriminating follow-up: two fresh four-worker v126 production-image browser catalog rounds each completed 41 supported content-checked outputs; SSRF probe was blocked; two provider-only features were unavailable with no credentials; zero other failures/page errors. Watermark completed in both; the intermittent multi-minute processing state was not reproduced, so ID 28 remains PARTIAL with root cause unresolved (`browser-id28-v117-current-image-catalog-v126-2026-11-20.json`). Container and tmpfs data were removed.
- ID 42 current mobile visual recheck: screenshots at 320/390/820/1366px were inspected. The full-page screenshot's fixed-bar overlay prompted a real focused-action check: 2 Chromium rounds × 5 phone/tablet viewport-height profiles loaded the PDF, generated a controlled brief, focused Download PDF, and confirmed its full rectangle remained above the fixed nav. 10/10 pass, 76px scroll padding, no overflow/errors (`browser-id42-fixed-nav-focus.json`). No CSS change was needed. Device and owner-image comparisons remain open.
- Current-source P0 discriminating matrix reran twice in Chromium (rounds 61 and 62): 60 checks each, zero browser page errors. Direct public-PDF import returned a content-checked one-page PDF twice; the exact owner Drive `/view` URL still returned HTTP 400 with `image/png` twice, so ID 4 remains PARTIAL pending a working PDF URL/source. Evidence: `browser-p0-round61.json`, `browser-p0-round62.json`, current roll-up `browser-p0.json`.


## 2026-11-20 — Bound Watermark and Page Number job completion

- Self-analysis of ID 28 found that image Watermark and the per-page text overlay/Page Numbers paths bypassed the converter timeout wrapper. A slow or stuck operation could therefore leave the job at its initial 20% `processing` state indefinitely.
- Added a 180-second bound around both rendering paths. On timeout, the shared wrapper removes partial output and `run_job` records a terminal failed result; the retry message advises using fewer pages or a smaller file.
- Added deterministic regressions for slow image Watermark, text Watermark, and Page Numbers handlers. All 3 controlled cases confirmed timeout, terminal exception, and no partial output. Windows testing then exposed a file-lock cleanup edge case when a timed-out converter still held the temporary PNG; cleanup now retries in a daemon helper after the converter releases the handle, and the regression asserts the temporary file is eventually removed. Focused regression selection passed 6 tests.
- Re-ran `browser_id361_watermark_image_guard.py` against two isolated current-source local servers: invalid oversized and malformed image watermarks failed with actionable messages; a valid image Watermark completed and its PDF download passed source-text and watermark-pixel checks in both Chromium rounds; zero page errors. Evidence: `browser-id361-watermark-image-guard.json`.
- Limitation: Python threads executing native converters cannot be forcibly cancelled safely by `Future.cancel()`. The user-facing job now terminates within the configured bound, but a truly hung native worker can continue in the background until it exits. The historical ID 28 stall's root cause is still unknown, so ID 28 stays PARTIAL and deployment readiness is not established.
- After the change, the full suite passed twice sequentially: 621 passed in each run, four existing warnings (`pytest-watermark-timeout-run1.log`, `pytest-watermark-timeout-run2.log`; machine-readable summary `pytest-watermark-timeout-summary.json`). Current-source P0 browser matrix was refreshed at 60/60 checks with zero page errors (`browser-p0.json`). `git diff --check` and Python compilation also passed.


## 2026-11-20 — Killable Watermark worker boundary

- The previous timeout only bounded the caller; its thread could continue native PDF work. Replaced that path with `watermark_job_worker.py` and a `multiprocessing` spawn child for image/text watermarks and Page Numbers. The parent waits 180 seconds, terminates then kills if needed, joins the child, deletes partial output, and returns an actionable terminal error. Temporary image deletion occurs after process termination, avoiding the prior Windows locked-handle cleanup race.
- `server.overlay` now delegates to the worker's single overlay implementation to keep direct utility tests and child output behavior aligned. Page-number parsing, page range, font, color, opacity and placement behavior remain in the worker.
- Focused backend checks passed 14 tests; explicit timeout cases passed 6/6. Chromium against isolated local Uvicorn submitted a real image Watermark job with a 1ms test deadline, verified a terminal failed job with the “worker was stopped” message, no output name, and zero page errors (`browser-id28-watermark-terminal-timeout.json`). Two further Chromium rounds against separate current-source servers verified malformed-image rejection and valid image Watermark downloads with source text and expected watermark pixel content (`browser-id361-watermark-image-guard.json`).
- Full suite after process isolation passed twice: 621 passed each, 4 warnings (`pytest-watermark-process-run1.log`, `pytest-watermark-process-run2.log`; summary `pytest-watermark-process-summary.json`).
- Residual: local tests now prove hard timeout containment and the two-round catalog's Watermark output. The historical 20%-stalled single job has not been reproduced, so ID 28 remains PARTIAL until the original trigger is identified.


## 2026-11-20 — Python 3.12 production-image worker verification

- Built current source as `paperplane-v23-audit:codex-v127`, digest `sha256:d00001b0bf50a34ac4263b4c1c83003010cb95449e9407db0a0fd6e6a4e4a252`. Production-mode container health returned `ok`; four application workers ran as UID 1001 after the mount-preparation entrypoint dropped root privileges.
- Two Chromium rounds against the actual image each rejected oversized and malformed watermark images and completed a valid image-watermark download; both downloads retained source text and the expected watermark pixel. Zero browser errors.
- A separate Python 3.12 in-container probe as UID 1001 applied a 1ms test deadline, observed the worker stop, and confirmed terminal timeout with no output or temporary PNG left. This validates process termination on the deployment runtime.
- The disposable container and tmpfs data were removed. No payment or persistent data was used. Evidence: `docker-id28-watermark-process-v127.json`, `browser-id361-watermark-image-guard.json`.


## 2026-11-20 — Final suite after worker-result cleanup

After adding unconditional partial-output cleanup for worker crashes/pipe errors, the latest full test suite passed twice sequentially: 621 passed in both runs, four existing warnings (`pytest-watermark-process-final-run1.log`, `pytest-watermark-process-final-run2.log`; `pytest-watermark-process-final-summary.json`). The process-worker browser timeout and normal success rounds passed on this code.


## 2026-11-20 — Final Docker v128 rebuild after output-cleanup change

- Rebuilt the final worker implementation as `paperplane-v23-audit:codex-v128`, digest `sha256:e31bfee2fc32ec2128473b176e06eebd114d6510885a2dc6c5ab3d15399e5ec1`. Production-mode health was `ok`; all four app workers ran as UID 1001.
- Two actual-image Chromium rounds passed invalid-image handling plus content-checked valid watermark downloads. A Python 3.12 probe executed as UID 1001 forced the timeout path and confirmed the child stopped, job error was terminal, and no partial output or temp image remained.
- Removed the disposable container and tmpfs. Evidence: `docker-id28-watermark-process-v128.json`, `browser-id361-watermark-image-guard.json`.


## 2026-11-20 — Reproduced and closed the stuck-worker behavior locally

- Strengthened the timeout regression from timing out during process startup to a real blocked child: the controlled process entered the watermark worker function, opened and held the temporary watermark file, wrote its PID/start time marker, and slept beyond the 1.5-second test deadline.
- Real local Uvicorn + Chromium submitted the job through `/api/jobs`; status became `failed` with retry text and no output name. The marked PID was verified absent with psutil after timeout, and the temporary PNG was removed. Zero browser page errors. Evidence: `browser-id28-watermark-terminal-timeout.json`; worker fixture `watermark_timeout_test_worker.py`.
- This directly reproduces the indefinite-worker mechanism under controlled conditions and proves the worker process can be killed; the production 180-second deadline bounds actual jobs. ID 28 is now FIXED LOCALLY. Post-deploy check remains: rerun the same 44-operation catalog with the historical Watermark input/profile and confirm no job stays at 20% beyond 180 seconds.


## 2026-11-20 — Final v129 image confirmation after blocked-worker reproduction

- Built the final candidate as `paperplane-v23-audit:codex-v129`, digest `sha256:2001f466a1e1f1488e4311ab504242f87916775eacb0c04958f590353ff2e05c`. Production health returned `ok`; four app workers ran at UID 1001.
- Two Chromium rounds on the final image passed malformed/oversize rejection and valid content-checked watermark download. A Python 3.12 probe as UID 1001 triggered a short deadline; the child stopped and no output or temporary image remained. The disposable container was removed.
- Final full test suite passed twice at 621 tests per run, four existing warnings; see `pytest-watermark-release-summary.json`. Evidence: `docker-id28-watermark-process-v129.json`.


## ID 122 — 69-page Studio page-stack observer-margin comparison

On current local source, the 69-page `notes.pdf` mobile Chromium harness passed twice at 390×844, DPR 3, 4× CPU slowdown with the production `120% 0px` page-stack observer margin: page text/order and all 69 cards were preserved, thumbnails 1/40 rendered, selection/navigation/slot recovery/export passed, and there were zero page errors or horizontal overflow. A test-only `300px 0px` override also passed the same browser workflow twice, but did not produce a repeatable performance improvement: readiness was 10.13s/6.76s vs 8.80s/7.84s; >50ms tasks were 52/48 vs 64/48, and worst tasks were 871/489ms vs 585/454ms. No product setting changed; ID 122 remains PARTIAL because main-thread responsiveness and low-end physical-device behavior are unverified. Evidence: `browser-id122-mobile-69page-studio-export_current_v129.json`, `browser-id122-mobile-69page-studio-export_margin300_trial.json`.

## ID 122 — Mobile page-stack observer implementation and production-image verification

Follow-up comparison of the same 69-page source found that an exact 0px mobile page-stack observer margin improved both post-change rounds over the paired current-source 120% baseline: first-page readiness 7.56s/6.76s vs 8.80s/7.84s, long tasks over 50ms 51/41 vs 64/48, and worst tasks 558ms/427ms vs 585ms/454ms. Implemented 0px only for mobile while retaining 120% desktop prefetch; app.js advanced to v127 and service-worker shell to v60. Local Chromium preserved every page's text/order, all 69 cards, page-1/page-40 thumbnails, selection, navigation, missing-slot recovery and export with no browser errors/overflow. Current P0 Chromium rounds 68 and 69 each passed 60/60 with zero page errors. Local mobile Scan-to-PDF and offline shell passed 2/2. A fresh v130 Python 3.12 production-mode image reached healthy status with four UID-1001 workers and tmpfs `/data`/`/tmp`; two image-backed Studio rounds preserved all 69 pages and confirmed both page observers at 0px on mobile. Two additional image-backed Chromium contexts verified shell v60/app v127 cache content then loaded the root offline with HTTP 200 and CSS active. Full pytest passed twice at 622 tests per run (four existing warnings each). The 250ms maximum long-task target is still missed; keep ID 122 PARTIAL. Evidence: `browser-id122-mobile-69page-studio-export_app127_mobile_root0.json`, `browser-p0-round68.json`, `browser-p0-round69.json`, `browser-id357-mobile-scan-pwa-v130.json`, `browser-id122-docker-codex-final-v127.json`, `browser-v130-docker-offline-pwa.json`, `pytest-current-v131-summary.json`.

## ID 37 — Current browser-local operation coverage inventory

Recomputed local support from the current `server.OPERATION_SLUGS` and the browser's `CLIENT_SIDE_SUPPORTED_OPERATIONS` plus `CLIENT_SIDE_IMAGE_OPERATIONS`, instead of relying on the historical 26/41 workflow number. Current source has 44 operation routes: 25 declare browser-local handling and 19 are server-only. The server-only routes are `ai_chat`, `ai_extract`, `annotate`, `compress`, `excel_to_pdf`, `html_to_pdf`, `mask_aadhaar`, `ocr`, `pdf_to_excel`, `pdf_to_pdfa`, `pdf_to_powerpoint`, `powerpoint_to_pdf`, `protect`, `redact`, `repair`, `summarize`, `translate`, `unlock`, and `word_to_pdf`. No unsupported operation was falsely switched to local mode. ID 37 remains PARTIAL; these routes require either a real privacy-preserving browser implementation or an explicit user-requested server workflow, plus content-checked browser evidence before coverage can be called complete.

| ID 37/current 44-operation catalog in production image (2026-11-20) | Rebuilt and started the current v133 production-mode Docker image with temporary synthetic values and tmpfs data; ran two Chromium rounds through all 44 operation paths using content-checked downloads. | Both rounds: 41 successful outputs, two AI-provider-only routes unavailable without credentials, SSRF blocked, zero failed operations and zero browser errors. OCR and PDF/A ran with the Docker-bundled dependencies. Dynamic Aadhaar suffix verification passed in both rounds. Container health was `ok`, four app workers UID 1001; container stopped and removed. Evidence: `browser-id28-v133-current-image-catalog-catalog-v133-2026-11-20.json`, `browser-id28-current-image-continuation-catalog-v133-2026-11-20.log`, `docker-id28-v133-runtime-catalog-v133-2026-11-20.json`. |

| ID 101 and ID 246 current security recheck (2026-11-20) | Ran fully redacted Gitleaks v8.24.2 across the current 113.63 MB worktree, pip-audit against requirements, v133 image exclusion checks, and passive live TLS/header/exposed-path checks. | Gitleaks reported 23 matches, all under ignored local `.env`/TLS key paths, archived `.tmp` audit material/docs, or generated Python bytecode; no current tracked application source. `.env` and `deploy/certs/privkey.pem` are not tracked and neither is in the v133 Docker image; values were not inspected. Pip-audit found zero known CVEs. Live HTTP→HTTPS, TLS, root, HSTS, nosniff, frame, referrer, permissions and nine path probes passed. Live CSP is still missing `base-uri` and `frame-ancestors`, already present in local Nginx config; recheck after deployment. Certificate expires 2027-01-29. Evidence: `gitleaks-v134-redacted.json`, `security-passive-live-check.json`, `docker-id28-v133-runtime-catalog-v133-2026-11-20.json`. |

| Self-found Translate result blob URL lifecycle (2026-11-20) | Real Chromium rendered three synthetic translation results, replaced the second with another AI result, then cleared the result panel. The first URL was revoked when replaced, the second when the other AI result replaced it, and the third on clear; zero page errors. Production-mode Docker v135 was healthy with four UID-1001 app workers; Docker-backed Chromium repeated the lifecycle regression and downloaded a valid one-page marker PDF with zero page errors, then the container was removed (`browser-id363-translation-object-url-lifecycle-docker-v135.json`, `docker-id363-translation-lifecycle-runtime-v135.json`). Two offline rounds loaded app.js v129 from PWA shell v62 and root navigation returned HTTP 200. Current-source P0 round 72 recorded 60 checks, zero page errors. | Fixed locally; content behavior unchanged. Regression evidence: `browser-id363-translation-object-url-lifecycle.json`; `browser-id357-service-worker-v62-offline-local.json`; `browser-p0-round72.json`. The current v135 production image passed a two-round 44-operation catalog (41 content-checked outputs each, two AI provider routes unavailable without credentials, SSRF blocked, zero failures/errors; OCR/PDF-A passed) and excluded the ignored local env/TLS key. Full suite initially exposed eight stale cache-version test assertions; expectations updated to app.js v129/shell v62. Two subsequent sequential full-suite runs passed 625 tests each, four existing warnings (`pytest-current-v137-summary.json`, `pytest-current-v137-run1.log`, `pytest-current-v137-run2.log`). Register remains 323 FIXED LOCALLY, 29 PARTIAL, 1 BLOCKED. |


| Self-found deployment guide/runtime drift (2026-11-20) | Compared docs with `.env.example`, `config.py`, actual `/api/health`, and the v135 production-mode Docker health response. Guide incorrectly said `PAPERPLANE_JOB_TTL_SECONDS=86400` and documented an obsolete health schema/version; replaced with 7200 seconds, current health JSON keys, validated HTTPS probe, and accurate UID/port behavior. Added a test matching guide TTL/health keys to runtime contract. | Focused regression passed; two sequential full-suite runs passed 626 tests each, four existing warnings (`pytest-current-v138-summary.json`, `pytest-current-v138-run1.log`, `pytest-current-v138-run2.log`). Deployment docs/test changed; no application runtime behavior or register status changed. |

## ID 27 current candidate retest (2026-11-20)

`browser_id27_local_1024_regression.py` was rerun against the current local source. Chromium loaded all 44 operation routes twice at a 1024px viewport (88 checks); every route returned HTTP 200, no topbar elements overlapped, document width remained within viewport, and there were no page errors. Result: PASS. Current assets: app.js v129, styles.css v56. Evidence: `browser-id27-local-1024-regression.json`. The live app and physical-device/owner visual comparisons remain unverified until deployment and owner input.

## ID 1 fresh live provider retest (2026-11-20)

`browser_live_id1_translation_matrix.py` ran against `https://paperplane.qd.je` using a generated 10-page synthetic PDF. Spanish and Hindi each ran twice in Chromium. All four returned 422 because only 20% of blocks/segments/characters were translated; the UI offered no download and Chromium recorded zero page errors. Evidence: `browser-live-id1-translation-matrix.json` plus four screenshots. Safety guard behaved correctly; translation function did not. Retest after owner deployment of current source.

## Current-asset Studio and P0 verification (2026-11-20)

Executed `browser_id122_mobile_69page_studio_export.py` using the real 69-page `C:/Users/mdham/Downloads/notes.pdf`, Chromium mobile viewport 390px, DPR3, and 4× CPU throttling. Two runs preserved all pages/text order, organizer thumbnails, page selection/navigation, and downloaded export content; document width was 390px and page errors were zero. Readiness was 8.49s / 7.81s; maximum >50ms tasks were 887ms / 433ms. This confirms functionality on latest app.js v129 but fails the 250ms performance target; ID 122 remains PARTIAL. `browser_p0.py` then passed 60 checks with zero page errors in round73. Evidence: `browser-id122-mobile-69page-studio-perf-app129-current-20261120.json`, `browser-p0-round73.json`.

## ID 122 content-visibility counter-trial (2026-11-20)

Injected `content-visibility:auto` only in the Playwright page before loading the real 69-page PDF. Both 4× CPU rounds retained content/export, width 390px, and zero page errors, but regressed readiness to 12.10s/10.14s, totals to 19.62s/17.11s, >50ms tasks to 53/51, and max tasks to 943ms/988ms. Compared with current v129 baseline (8.49s/7.81s; 13.60s/12.67s; 37/40 tasks; max 887ms/433ms), the trial is worse and was rejected; no product CSS was changed. Evidence: `browser-id122-mobile-69page-studio-perf-contentvis-auto-trial-20261120.json`.

## Current v129 responsive matrix (2026-11-20)

`browser_id27_narrow_zoom_layout.py` ran on current app.js v129 / styles.css v56. It loaded all 44 tool routes at 1280, 1100, 1024, 901, 900, 683, 512 and 320px in two rounds: 704 checks, zero failures/page errors. It checked document width, visible overflow, topbar overlap, bounds, and scrolling. Evidence: `browser-id27-narrow-zoom-layout.json`. Native physical-device and live/deployed checks remain open.

## ID 97 current asset recheck (2026-11-20)

Ran `browser_id97_password_reset.py` on an isolated temporary database with current app.js v129. Both Chromium rounds received the generic forgot-password response, opened the local development reset URL, changed the disposable account password, and received reset HTTP 200; zero page errors. No external email was sent. Evidence: `browser-id97-password-reset-app129-current-20261120.json` and request/completion screenshots. Real provider inbox delivery remains unverified.

## ID 90 eight-context live concurrency extension (2026-11-20)

Extended the existing bounded live Chromium harness with a validated `PAPERPLANE_ID90_COUNT` setting (1–8) and ran four- and eight-context rounds of synthetic one-page Merge jobs against `https://paperplane.qd.je`. All twelve returned HTTP 202, completed, and downloaded HTTP 200 PDFs; every output had a valid PDF signature, exactly one page, and its unique source marker (12/12). No browser page errors. This verifies only short synthetic bursts, not sustained load or the OTP response-header/email path; ID 90 remains PARTIAL. Evidence: `browser-id90-live-concurrency-4-2026-11-20.json`, `browser-id90-live-concurrency-8-2026-11-20.json`.

## ID 122 async thumbnail encoding and stale-document regression (2026-11-20)

Profiled current app.js v129 / page_organizer.js v16 on the real 69-page `notes.pdf` in 390×844 mobile Chromium at 4× CPU throttle; synchronous canvas `toDataURL()` encoding appeared among the hot frames along with PDF.js text/layout work. Updated organizer previews to asynchronous JPEG `toBlob()` object URLs, revokes their cached URLs when the PDF is replaced/closed, and rejects pending thumbnail work when its source document or render epoch has changed. Two current-source Chromium rounds confirmed all 69 page texts/order, all organizer cards, page-1/page-40 thumbnails, selection, navigation, valid content-preserving exports, and 390px width; zero page errors. Each round verified six visible previews used Blob URLs, a deliberately delayed stale document did not repopulate the replacement cache, and all cached thumbnail URLs were revoked on document clear. Timing was mixed: readiness 9.28s/7.07s and maximum long task 676ms/677ms versus prior v129 data-URL baseline 8.49s/7.81s and 887ms/433ms. Do not claim a repeatable responsiveness gain; ID 122 remains PARTIAL pending the 250ms target and physical-device check. Evidence: `browser-id122-mobile-69page-studio-perf_toblob_lifecycle.json`, `browser-id122-mobile-69page-studio-perf_profile_current_v129deep.json`.

The v136 production-mode Docker image (`sha256:51b65ece66ac87c14b9ad283628e5682b23b1cf209867af25f478f67b647799e`) reached health `ok`, four workers, and app PID 1 UID 1001. Two current-image Chromium exports preserved exact text/page order for all 69 pages, page-1/page-40 thumbnails, a visible 1.5× mobile canvas, 390px document width, and zero page errors. Two v63 offline-shell rounds loaded app.js v129, page_organizer.js v17 and styles.css v56 at HTTP 200 while offline. Current P0 round 74 passed 60/60. Full current-source pytest passed 627 tests twice (four pre-existing deprecation warnings each). The v136 44-operation catalog passed twice: 41 content-checked downloads each, two provider-only routes unavailable, one SSRF case blocked, zero other failures/page errors; container stopped and removed. Evidence: `browser-id122-docker-codex-final-v129-v136.json`, `docker-id122-v136-runtime.json`, `browser-id357-service-worker-v63-offline-local.json`, `browser-p0-round74.json`, `pytest-current-v139-summary.json`, `browser-id28-v136-current-image-catalog-catalog-v136-2026-11-20.json`, `docker-id28-v136-runtime-catalog-v136-2026-11-20.json`.

## ID 357 current-source Scan-to-PDF and PWA affordance recheck (2026-11-20)

Repeated the current app.js v129 / shell v63 mobile flow in two fresh 390×844 touch Chromium contexts. The manifest and icons returned correct content, worker scope was `/`, shell references matched v63/v129, and the environment camera chooser remained rear-facing. Simulated the browser-controlled `beforeinstallprompt` event with accepted and dismissed user-choice outcomes; the install action appeared only after the event and hid after use. Each run downloaded a valid one-page Letter PDF through browser-local processing, made zero `/api/jobs` POSTs, loaded the root offline with HTTP 200, had no horizontal overflow, and produced zero page errors. This does not prove a native install prompt or real camera sensor on physical Android/iOS devices; ID 357 remains PARTIAL. Evidence: `browser-id357-mobile-scan-pwa-v140.json`, `browser_id357_mobile_scan_pwa_v140.py`.

## ID 357 latest mobile PWA and scan test (2026-11-20)

Ran the current-source `browser_id357_mobile_scan_pwa_v140.py` against a fresh isolated server in two touch-enabled 390×844 Chromium contexts. Manifest content type and icon PNGs passed, service worker scope was `/`, shell v63 referenced app.js v129, and camera input requested the environment-facing capture. Both accepted/dismissed install-event simulations showed and consumed the install action as expected. Each camera-file chooser run created and downloaded a valid one-page Letter PDF locally with zero `/api/jobs` posts; the offline root returned HTTP 200, width fit the viewport, and there were no page errors. Playwright emulates the install event and camera-file selection; this is not evidence from a native prompt or physical camera. Evidence: `browser-id357-mobile-scan-pwa-v140.json`.

## Fresh live deployment fingerprint (read-only, 2026-11-20)

The public root returned HTTP 200 and still references app.js v91, page_organizer.js v14, and styles.css v51. `/api/health` returned HTTP 200 but `job_ttl_hours` is 24 while the current local candidate and deployment documentation specify 2 hours. The expected candidate app.js v129 / organizer v17 / styles v56 is not deployed. This check called only `/` and `/api/health`; no user/account/job endpoints or mutations. Evidence: `browser-live-assets-readonly-2026-11-20.json`, `browser_live_asset_recheck_20261120.py`.

## ID 101 full reachable-history and prepared-mirror verification (2026-11-20)

Gitleaks v8.24.2 with `--redact=100` scanned all 45 source commits (~158.10 MB) and reported 33 pattern matches across seven paths. The two `paperplane-admin-fallback` matches are in historical `server.py` commits `8dd50e6` and `1596e5d`; the source history still contains the compromised admin fallback. A separate read-only full-history scan of the isolated sanitized preparation mirror reported the same detector counts, but both admin-fallback rows correspond to the literal `[REDACTED]` marker inserted by the existing purge script. Independently extracted the original historical value in memory and scanned all 3,959 mirror Git objects and all commit messages: zero occurrences. `git fsck --full --no-reflogs` passed; the mirror has no remote and ten refs. Secret/match fields are excluded from `gitleaks-full-history-redacted-2026-11-20.json`. Other historical `curl-auth-header` and `generic-api-key` detections remain metadata-only and need owner classification; this scan does not assert they are production credentials. The sanitized mirror is still based on committed history only, predates uncommitted v23 work, and is not publish-ready. No source history, protected mirror, remote, or production credential was modified.

## ID 122 repeated low-end mobile Studio profile (2026-11-20)

Repeated the real 69-page `notes.pdf` workflow twice in 390×844 Chromium with DPR 3 and 4× CPU throttling on the current app.js v129 / organizer v17 candidate. Both exports preserved all 69 pages and exact text/order, rendered the first and fortieth organizer previews, recovered the tested missing-page-slot case, kept document width at 390px, and had zero page errors. Scroll selection read eight page-slot rectangles. First-page readiness was 6.88s and 9.39s; maximum observed tasks were 655ms and 635ms. Thus the <250ms target still fails and ID 122 remains PARTIAL. Evidence: `browser-id122-mobile-69page-studio-exportcurrent_v129deep_followup_20261120.json`.

The attempted `rootMargin=0px` browser-injected comparison was invalid as an A/B test: current organizer source already initializes its Studio IntersectionObserver at `0px 0px`, and the harness only replaces the historical `120% 0px` setting. Its output is retained as `browser-id122-mobile-69page-studio-export-interceptor-noop-20261120.json` and is not used as comparative evidence. No product code changed based on this trial.

## ID 122 PDF.js incremental-render counter-trial (2026-11-20)

Instrumented the test page only so each PDF.js `RenderTask.onContinue` resumes through `requestAnimationFrame` (or a zero-delay timeout while hidden); no application file was changed for this trial. Both 69-page exports retained exact page/text order, with zero page errors. Under 4× CPU throttling, first-page readiness was 11.91s/9.57s, total workflow 20.06s/16.53s, long-task counts 61/44, and maxima 551ms/497ms. Against the immediately preceding current-source run (6.88s/9.39s readiness, 14.08s/15.78s total, maxima 655ms/635ms), changes were mixed and total time regressed in both rounds; the <250ms target still fails. Rejected this continuation override; it is not enabled in the product. Evidence: `browser-id122-mobile-69page-studio-exportpdfjs_raf_continuation_trial_20261120.json`.

## ID 101 detector false-positive refinement (2026-11-20)

The prior 33-match history scan identified two non-secret detector hits after sanitization: the literal `[REDACTED]` replacement in the prepared mirror and a synthetic fallback string assembled in the ID 101 regression test. Added narrowly scoped custom-rule allowlists for that exact marker line and the exact test fixture file; added a regression proving a real Compose fallback is still detected, the fixture path is scoped, and only a `[REDACTED]` admin line matches the marker allowlist. Focused ID 101 tests passed (3). Repeated fully redacted scans: current source history reports 32 total matches, including two historical admin-fallback hits; the prepared mirror reports 30 matches and zero admin-fallback hits. The original value remains absent from all 3,959 mirror objects/commit messages; `git fsck` passes, with no remote. The 30 remaining default-rule findings in historical docs/evidence still need owner classification. Current structured metadata: `gitleaks-full-history-redacted-2026-11-20.json`; pre-refinement baseline retained as `gitleaks-full-history-pre-allowlist-redacted-2026-11-20.json`.

## ID 101 latest verification after Gitleaks config change (2026-11-20)

Focused secret-scanner regressions passed 3/3. Sequential complete pytest runs both passed 628 tests with four existing Starlette/httpx deprecation warnings each: `pytest-id101-full-suite-20261120-run1.log` (155.66s) and `pytest-id101-full-suite-20261120-run2.log` (146.50s); summary: `pytest-id101-full-suite-20261120-summary.json`. The `.gitleaks.toml` allowlist change therefore has fresh full-suite coverage. It does not rewrite source history, rotate credentials, classify historical docs/evidence matches, or make the uncommitted candidate mirror publish-ready.

## ID 122 verified PDF.js incremental-yield trial (2026-11-20)

A corrected browser harness now proxies the actual loaded `window.pdfjsLib` and asserts the test hook intercepted the Studio document/page/render calls. Two valid continuation-trial rounds preserved the exact 69-page export, with zero page errors; the probe verified 16 page-render tasks and 42/47 PDF.js incremental `onContinue` callbacks. Readiness was 7.86s/8.49s, total workflow 14.49s/14.92s, and maximum tasks 538ms/471ms. A fresh no-override baseline was 7.69s/7.62s readiness, 15.41s/13.97s total, and 613ms/735ms maxima. Maxima improved in these paired rounds, while task counts were 50/45 versus 49/42 and end-to-end time was mixed. The 250ms goal remains substantially unmet, and the result is not sufficient to justify a product change. Prior `pdfjs_raf_continuation_trial` and `pdfjs_raf_continuation_verified` files were invalid/under-recorded injections; only the verified2 artifact is used as valid trial evidence. No render-yield override is enabled in product code. Evidence: `browser-id122-mobile-69page-studio-exportpdfjs_raf_continuation_verified2_20261120.json`, `browser-id122-mobile-69page-studio-exportcurrent_baseline_20261120b.json`.

### Latest ID 101 full-suite confirmation (2026-11-20)

After tightening the marker allowlist and its regression assertion, the current full suite passed twice sequentially at 628 tests, with four existing deprecation warnings each: `pytest-current-v140-run1.log` (149.72s) and `pytest-current-v140-run2.log` (150.55s). Summary: `pytest-current-v140-summary.json`. No production endpoints or credentials were used.

## Current-source P0 and full-suite recheck (2026-11-20)

Ran the complete P0 Chromium harness twice against fresh isolated current-source servers. Each run finished all 60 asserted scenarios with zero browser page errors; the evidence JSONs are `browser-p0-continuation-20261120-round1.json` and `browser-p0-continuation-20261120-round2.json`. Then ran the full pytest suite twice sequentially in clean credential-free environments; both passed **628 tests**, each with four existing deprecation warnings (`pytest-current-v139-run1.log`, `pytest-current-v139-run2.log`, `pytest-current-v139-summary.json`). These are verification refreshes only; they do not resolve the remaining provider, deployment, owner, mobile-device, or Studio responsiveness gaps.

## ID 122 redundant mobile toolbar layout reads (2026-11-20)

The current 69-page mobile CPU profile traced repeated `getBoundingClientRect()` samples through `syncStudioMobilePagesPanelPosition`, including duplicate calls around Organize/Annotate transitions. Updated these transitions to apply mode/ribbon/batch-bar state first, suppress the page-organizer's intermediate layout sync, then perform one final sync. New app.js v130 / page_organizer.js v18 are cached by shell v64. Two fresh 390×844 Chromium runs opened a PDF, switched both modes, and confirmed exactly one toolbar geometry read per transition, valid panel top positioning, no horizontal overflow, and no browser errors (`browser-id122-toolbar-geometry-batching.json`). The pre-change app.js v129 69-page profile recorded max long tasks of 524ms and 851ms; the current app.js v130 profile is documented below and still does not resolve the PDF.js responsiveness target. Offline shell v64 passed two offline-navigation rounds, loading app.js v130, organizer v18 and styles.css v56 (`browser-id357-service-worker-v64-offline-local.json`). Post-fix checks passed: P0 60/60 twice, responsive routes 704/704, current production image v137 two content-checked 69-page exports, and the full suite 628 tests twice. ID 122 remains PARTIAL because the 250ms responsiveness target is unmet.

## ID 37 browser-processing capability matrix (2026-11-20)

Added and ran a Chromium capability-gating audit against an isolated current-source local server. All 44 tool routes were loaded at desktop 1366px and phone 390px (88 checks). For each route, the actual `state.operation`, client-side mode, browser toggle disabled/checked state, accurate on-device or temporary-upload disclosure, HTTP 200, viewport fit, and absence of job posts/page errors were verified. The 25 declared browser-local workflows were on-device with the toggle enabled, including forced-local photo tools; all 19 server-only workflows explicitly disclosed upload/temporary processing and had the browser toggle disabled. This confirms the current UI does not advertise local processing on unsupported routes; ID 37 remains PARTIAL because those 19 operations still have no browser-local implementation. Evidence: `browser-id37-browser-processing-capability.json`, runner `browser_id37_browser_processing_capability.py`.


## ID 122 current app.js v130 69-page profile (2026-11-20)

Repeated the exact 69-page mobile Chromium workflow against app.js v130 / organizer v18 at 4× CPU throttle after the toolbar geometry change. Both runs preserved all page text/order, selection, organizer thumbnails, page-40 navigation, missing-slot recovery, and content-checked export at 390px with zero errors. First-page readiness was 9.75s/7.83s; long tasks over 50ms were 52/50, with maxima 985ms/630ms. The responsiveness result did not improve consistently and remains far above the 250ms goal; no performance-ready claim is made. Full call-path evidence is in `browser-id122-mobile-69page-studio-export-app130-final-20261120.json`.

## ID 122 mobile Studio scroll lock after mode changes (2026-11-20)

A self-found browser regression showed that switching Annotate/Organize queued `jumpToStudioPage` and held the scroll observer lock while PDF.js re-rendered the preserved page. In two 390×844 Chromium rounds, after mode toggles, page 40 became visible but `state.studio.currentPage` stayed 1 with a 19,443px canvas scroll offset; this was an actual navigation-state defect. Removed the mode-change page jump in app.js v131, since changing ribbon state must not move the user's canvas or override their next scroll. Repeated both rounds: Page 40 became active, the return to Page 1 worked, and Studio downloads preserved exact text/order for all 69 pages (5,535,231 bytes); each transition performed exactly one toolbar geometry read, with no overflow or page errors (`browser-id122-mobile-mode-navigation.json`). Production-image v138 ran the same mode transitions in two 4× CPU mobile Chromium rounds, navigated to page 40, and downloaded 69-page PDFs with exact text/order; health was OK, all four workers used UID 1001, and no browser errors/overflow occurred (`browser-id122-docker-codex-final-v131-v138.json`, `docker-id122-v138-runtime.json`). Shell v65 loaded app.js v131, organizer v18 and styles v56 offline in two rounds (`browser-id357-service-worker-v65-offline-local.json`).

A separate v131 69-page performance profile at 4× CPU throttle preserved all pages/content, thumbnails, selection, missing-slot recovery, page-40 navigation and export in both rounds. First-page readiness was 8.86s/6.53s, tasks over 50ms were 46/43 and maxima were 592ms/640ms. This still misses the 250ms target; no readiness claim is made (`browser-id122-mobile-69page-studio-export-app131-final-20261120.json`).

After this source change, current-source P0 passed twice (60/60 each), the 44-route responsive matrix passed 704/704, and the complete suite passed 628 tests twice with four existing warnings each. The first suite rerun caught one outdated source-contract assertion that required the removed mode jump; the assertion was updated to require the no-jump contract and the repeated full suite passed (`browser-p0-app131-round1-20261120.json`, `browser-p0-app131-round2-20261120.json`, `browser-id27-narrow-zoom-layout.json`, `pytest-current-v139-summary.json`, `pytest-current-v139-run1.log`, `pytest-current-v139-run2.log`).


## ID 122 selection-triggered layout synchronization follow-up (2026-11-20)

Profiling and instrumented Chromium rounds showed `PageOrganizerView._updateBatchToolbar` recalculated Studio toolbar geometry on each checkbox update even when the bar remained visible. It now syncs layout only when the bar's visibility changes. Two local 390×844 rounds measured one geometry read for each Annotate/Organize transition, zero additional reads across three selected-card updates, and exactly one read when clearing selection. All checks had zero page errors and no horizontal overflow (`browser-id122-toolbar-geometry-batching.json`). The current 69-page mobile profile preserved every page's text/order, all 69 cards, select/invert, Page 1/40 thumbnails, navigation, slot-recovery, and content-checked exports. Under 4× CPU throttle readiness was 8.07s/7.19s; long-task maxima were 560ms/594ms, so the <250ms criterion remains unmet (`browser-id122-mobile-69page-studio-export-app132-final-20261120.json`).

The app.js v132 / organizer v19 candidate passed P0 Chromium twice (60/60 each), the 44-route/eight-width responsive matrix twice (704/704), and shell v66 offline navigation twice. Fresh suite runs each passed 629 tests with four existing warnings. A rebuilt Docker image v139 (sha256 `3a77974683de68e5198252cc1bc04c4557e0ce7000404eff2c2ad8fca65bc58d`) repeated the Studio layout-transition and 69-page content/order export checks in two 4× CPU Chromium rounds, then passed all 44 catalog routes twice: 41 content-checked outputs, two provider-only operations unavailable without credentials, one safe SSRF rejection, zero other failed operations/page errors. The disposable container was removed. Evidence: `browser-id122-docker-codex-final-v132-v139.json`, `docker-id122-v139-runtime.json`, `browser-id28-v139-current-image-catalog-catalog-v139-2026-11-20.json`, `docker-id28-v139-runtime-catalog-v139-2026-11-20.json`, `pytest-current-v141-summary.json`, `browser-p0-app132-round1-2026-11-20.json`, `browser-p0-app132-round2-2026-11-20.json`, `browser-id27-narrow-zoom-layout.json`, `browser-id357-service-worker-v66-offline-local.json`. ID 122 remains PARTIAL; the performance threshold and physical-device checks are open.


## ID 122 overlay-stack mutation observer hot path (2026-11-20)

The current 69-page CPU profile sampled `syncOpenOverlayStack` scanning the document during a MutationObserver callback. Source analysis found the cached overlay array had no consumers: the Escape handler recomputed visibility immediately before selecting the topmost overlay. Removed that unused cache and full-body observer while keeping the Escape-time current-state scan and z-index/DOM ordering. Two real Chromium rounds opened both Settings and Auth overlays and confirmed Escape closes Auth first, then Settings; no page errors (`browser-id122-overlay-escape-stack-v133.json`). The 69-page 4× CPU profile no longer includes `syncOpenOverlayStack` in sampled call paths and preserved content/order/export; timings were mixed at 8.62s/8.54s readiness, 543/413ms max long tasks (`browser-id122-mobile-69page-studio-export-app133-overlay-profile-20261120.json`). Thus ID 122 remains partial on the <250ms target.

Final candidate app.js v133 / organizer v19 / shell v67 verification: P0 60/60 twice, responsive matrix 704/704, offline shell 2/2, full suite 630 passed twice. Production image v140 passed health and two 69-page exports, then all 44 catalog routes twice (41 content-checked results, 2 provider-only actions unavailable, SSRF safe block, no other failures/page errors); both containers were removed. See `browser-p0-app133-round1-2026-11-20.json`, `browser-p0-app133-round2-2026-11-20.json`, `browser-id27-narrow-zoom-layout.json`, `browser-id357-service-worker-v67-offline-local.json`, `pytest-current-v142-summary.json`, `docker-id122-v140-runtime.json`, `browser-id122-docker-codex-final-v133-v140.json`, `browser-id28-v140-current-image-catalog-catalog-v140-2026-11-20.json`, `docker-id28-v140-runtime-catalog-v140-2026-11-20.json`.

## Self-found high-zoom Studio drawer layout (2026-11-20)

A full 69-page Studio run at a 320×225 CSS viewport exposed that the mobile Pages drawer could sit below the toolbar and leave only 20px for the thumbnail list. The drawer now pins to the safe-area top, overlays the bottom dock in short-height viewports, and compresses its page-action row so the page list can render. The browser regression was extended to close the drawer before invoking Studio export, matching the visible Done control's real interaction. Two Chromium rounds with the real 69-page `notes.pdf` preserved all text/page order, rendered thumbnails for pages 1 and 40, passed selection/invert/navigation/slot-recovery checks, and downloaded content-checked PDFs with no 320px overflow or page errors (`browser-id122-mobile-69page-studio-export-app135-shortheight-final.json`). PWA shell v70 cached app.js v135, CSS v57 and organizer v19 offline in two rounds (`browser-id357-service-worker-v70-offline-local.json`). Full suite passed 631 tests twice (`pytest-current-v144-summary.json`); P0 rounds 87 and 88 passed all 60 checks without page errors (`browser-p0-round87.json`, `browser-p0-round88.json`). Docker v142 ran four workers, was healthy, and passed two content/order-checked 69-page Chromium exports (`docker-id122-v142-runtime.json`, `browser-id122-docker-codex-final-v135-v142.json`). This fixes the short-height drawer defect but does not meet ID 122's separate <250ms long-task target or replace physical-device verification.


## ID 122 toolbar-position geometry cache (2026-11-20)

- The app.js v133 69-page profile showed toolbar position synchronization as a hot path. A controlled 390×844 run at 4× CPU throttle correlated one drawer-open geometry read with a 192ms long task. Changed mobile Studio to cache the toolbar bottom from ResizeObserver and use a deferred one-frame fallback when no cached measurement exists. App.js is now v134 and the shell is v68.
- Two local Chromium rounds with a four-page fixture verified zero sync geometry reads during Annotate, Organize, Select All, repeated selection, and clear actions. Pages-panel top stayed aligned with the toolbar at 390, 820, and 683px; there was no horizontal overflow or page error (browser-id122-toolbar-geometry-batching.json). The 69-page trace confirms the old syncStudioMobilePagesPanelPosition read path is absent from sampled hot paths (browser-id122-mobile-69page-studio-export-app134-toolbar-cache.json).
- The 69-page 4× CPU rounds preserved exact page text/order, all 69 cards, page 1/40 previews, select/invert, slot recovery, navigation, and content-checked downloads. Readiness was 7.20s/8.57s and maximum long tasks 613ms/503ms, so the <250ms threshold is still unmet and timing is mixed; ID 122 remains PARTIAL. A 4× cause probe recorded zero toolbar geometry reads on drawer open and no browser errors (browser-id122-studio-toolbar-sync-cause.json).
- Full suite: 631 passed twice sequentially, four existing deprecation warnings per run (pytest-current-v143-summary.json). Current P0 rounds 85 and 86 each passed 60 assertions with zero page errors; responsive layout passed 704/704; PWA shell v68 passed two offline loads. The v141 four-worker production image passed two exact 69-page exports and the 44-operation catalog twice (41 content-checked outputs, two provider-only actions unavailable without credentials, SSRF safely blocked, zero other failures/page errors); containers were removed. Evidence: browser-p0-round85.json, browser-p0-round86.json, browser-id27-narrow-zoom-layout.json, browser-id357-service-worker-v68-offline-local.json, docker-id122-v141-runtime.json, browser-id122-docker-codex-final-v134-v141.json, browser-id28-v141-current-image-catalog-catalog-v141-2026-11-20.json, docker-id28-v141-runtime-catalog-v141-2026-11-20.json.
- The v23 item counts remain 323 FIXED LOCALLY, 29 PARTIAL and 1 BLOCKED. This local interaction improvement does not clear ID 122's performance target or its physical-device/deployment checks. No commit, push, deployment, account mutation, or payment was performed.


## ID 45 mid-size Studio toolbar layout closure (2026-11-20)

Two full Chromium rounds over 320/390/683/820/901/1366px confirmed the Studio save banner is absent, no viewport overflows, footer stays hidden until scrolling and reveals afterward, and the actual tool-control rows fit the target. The 901px breakpoint exposed five control rows despite the earlier 1366px fix; CSS now keeps the primary and secondary ribbon groups in horizontal scroll containers from 901–1023px. At 901px, local Chromium measured four visible control rows, 439px ribbon viewport widths, and 704/695px content widths; all buttons remain in their groups and horizontally scrollable. Production Docker v143 independently measured all 33 buttons in three rows in two 901px rounds, with no horizontal document overflow, hidden initial footer, and no page errors. Full suite passed 632 twice; current-source P0 rounds 89 and 90 passed all 60 checks with no page errors; the 44-route/eight-width layout matrix passed 704/704; shell v71 offline passed twice. ID 45 is FIXED LOCALLY. Evidence: `browser-id45-footer-visibility-matrix.json`, `browser-id45-docker-toolbar.json`, `browser-p0-round89.json`, `browser-p0-round90.json`, `browser-id27-narrow-zoom-layout.json`, `browser-id357-service-worker-v71-offline-local.json`, `pytest-current-v145-summary.json`, `docker-id122-v143-runtime.json`, `browser-id122-docker-codex-final-v135-v143.json`.

## ID 106 current-app idempotent retry regression (2026-11-20)

Re-ran the real Chromium retry harness against the current app.js v135 candidate for both standard job submission and the >10 MiB chunk-commit route. In each case the browser injected a controlled client-visible 502 after the server accepted the initial request. The retry reused the same idempotency key and job ID, returned 202 then idempotent 200, created exactly one job and one replay record, and downloaded a valid rotated PDF with its source marker intact. There were zero page errors (`browser-id106-idempotent-submit-retry_app135_current.json`). This confirms current local client/server behavior; the deployed proxy's historical long-processing stall still needs a post-deploy check, so ID 106 remains PARTIAL.

## ID 312 current responsive Studio retest (2026-11-20)

The prior device-layout evidence targeted an older stylesheet. Re-ran its real Chromium harness against the current source in two rounds at 820×1180, 390×844, 360×800, and 320×740 (8 viewport checks total). In all cases the first page stayed below the toolbar and cleared the fixed bottom dock, document width matched the viewport, mobile ribbons fit vertically and scrolled horizontally to the last tool, and there were no page errors. The current result refreshes browser evidence but does not emulate physical safe-area insets or satisfy the physical-device/live comparison requirement; ID 312 remains PARTIAL. Evidence: `browser-id312-studio-tablet-layout.json` and `id312-studio-{width}-round*.png`.


## ID 312 safe-area emulation follow-up (2026-11-20)

Chrome DevTools safe-area emulation at 30px top and 20px bottom uncovered a local regression hidden by the default zero-inset desktop emulation: the general mobile `main-area` offset was correct, but two later, higher-specificity Studio selectors reset it to a hard-coded 64px. Enabled `viewport-fit=cover`, made the fixed topbar height/padding and workspace offset consume the top inset, and changed both Studio overrides to use the inset. Current Chromium browser rounds at 820×1180, 390×844, 360×800 and 320×740 measured topbar padding 30px, main offset 94px, bottom-dock padding 20px, canvas below the toolbar and above the dock, reachable mobile ribbon ends, and no overflow or page errors. Offline PWA shell v73 cached app135/styles59 and reloaded the same viewport declaration in two offline rounds. Physical iOS/Android behavior remains to be checked on actual hardware. Evidence: `browser-id312-studio-tablet-layout.json`, `browser-id357-service-worker-v73-offline-local.json`, focused test `test_studio_mobile_pages_position_reuses_resize_observer_geometry_cache`.

## Current safe-area candidate verification (2026-11-20)

After adding `viewport-fit=cover` and making the topbar/Studio offsets safe-area-aware, the full suite passed twice at 632 tests per run with four existing warnings (`pytest-current-v146-summary.json`). P0 rounds 91 and 92 passed all 60 checks each with no page errors. The 44-route/eight-width matrix passed all 704 checks. ID 312's 30px-top/20px-bottom safe-area emulation passed twice at 820×1180, 390×844, 360×800 and 320×740; measured topbar inset 30px, main offset 94px, dock bottom padding 20px, no overflow, all mobile controls reachable, no page errors. PWA shell v73 loaded the current root offline with CSS v59 and viewport-fit meta in two rounds. Evidence: `pytest-current-v146-summary.json`, `browser-p0-round91.json`, `browser-p0-round92.json`, `browser-id27-narrow-zoom-layout.json`, `browser-id312-studio-tablet-layout.json`, `browser-id357-service-worker-v73-offline-local.json`. Actual iOS/Android safe-area behavior still needs physical-device confirmation.

## Safe-area short-height Studio final regression (2026-11-20)

The safe-area 320×225 run initially left the first organizer card one CSS pixel inside the scroll root; the 1% visibility threshold prevented its thumbnail from rendering. Compacted only the short-height drawer's scroll padding/subnav and used two columns. Two current-source Chromium runs with the real 69-page PDF, 4× CPU throttle and emulated insets (30px top/20px bottom) now rendered the page 1 and page 40 thumbnails, preserved all text/order, selection/invert, navigation, slot recovery and downloaded a content-checked 69-page output. Document width stayed 320px; no page errors. Max long tasks remain 854ms/874ms, above ID 122's target (`browser-id122-mobile-69page-studio-export_safearea_v74.json`).

Final candidate suite passed 632 tests twice (`pytest-current-v147-summary.json`); P0 rounds 93/94 each passed 60/60 with no errors; the 44-route responsive matrix passed 704/704; ID312 safe-area layout passed two rounds across four viewport sizes; shell v74 offline passed twice with app135/styles60. ID312 still requires actual iOS/Android confirmation and ID122 still misses its performance threshold. Counts remain 323 fixed locally, 29 partial, 1 blocked; release remains HOLD.

## ID 90 login-code header and bounded concurrency closure (2026-11-20)

Ran the real local login challenge route in Chromium with `server.send_otp_email` replaced by a controlled success stub before startup. The harness captured the generated code internally without delivering email, then verified the response had no `dev_otp`, no code in any header or body, and no authenticated account cookie; the challenge returned 200/`otp_required`, zero page errors, zero mail network calls (`browser-id90-otp-header-local.json`). This provides the direct local-browser check missing from the earlier unit-only evidence. The reported small concurrency failure also did not recur in 4- and 8-guest live bursts: 12/12 unique-marker PDFs completed and downloaded. ID 90 is now FIXED LOCALLY for its specified leakage and bounded-concurrency regressions; this is not a sustained peak-load claim.

## Self-found Studio toast overlap and accessibility fix (2026-11-20)

A visual review of the safe-area Studio screenshot showed the file-loaded success toast covering PDF content at 320px. A follow-up geometry check found the first attempted placement also ignored the fixed Studio command dock. The toast now uses the actual `#studio-mobile-dock` boundary, appears only in the clear gap below a rendered page, and keeps a loaded-page success announcement visually hidden but in the live region when no non-overlapping gap exists. Landscape pages keep a visible toast in the measured clear gap. All toasts now expose status/alert semantics with polite/assertive live announcements. Two Chromium rounds each at 390×844 and 320×740 checked portrait and landscape fixtures, page/canvas/dock geometry, success and error announcements, and zero page errors (`browser-self-found-studio-toast.json`; screenshot `self-found-studio-toast-landscape-320-round2.png`). The offline shell v77 cached app.js v137, styles.css v61, and organizer v19; two offline reloads returned HTTP 200 with no page errors (`browser-id357-service-worker-v77-offline-local.json`). Focused regression passed. The isolated sequential full suite passed twice, 633 tests per run with four existing warnings (`pytest-current-v150-summary.json`, `pytest-current-v150-run1.log`, `pytest-current-v150-run2.log).

Final v137/v61/shell-v77 verification completed: the full suite passed 633 tests in each of two sequential credential-stripped runs (four existing warnings); P0 rounds 95/96 each passed all 60 assertions with zero browser errors; the 44-operation route matrix passed 176 responsive route views with zero failures; and the 30px/20px safe-area layout matrix passed two rounds at 820×1180, 390×844, 360×800 and 320×740. Current evidence: `pytest-current-v150-summary.json`, `browser-p0-round95.json`, `browser-p0-round96.json`, `route-layout-matrix.json`, `browser-id312-studio-tablet-layout.json`. Physical-device and live checks remain out of scope for these local results.

## Reproduction follow-up: Studio toast overlap and current candidate (2026-11-20)

Self-found Studio bug: loaded-PDF success and error toasts could cover the active page. The first geometry fix missed the fixed mobile dock and the subsequent no-gap behavior failed the desktop P0 check; both were corrected. Current `showToast()` uses measured page/dock bounds and desktop side clearance, or hides the visual toast when no non-overlapping placement exists while retaining accessible status/alert announcements. Chromium success/error geometry checks passed twice at 390×844 and 320×740 in portrait and landscape; current P0 rounds 99/100 each passed 60/60 with zero page errors. Current production image v146 repeated the eight mobile combinations. Evidence: `browser-self-found-studio-toast-v2.json`, `browser-self-found-studio-toast-docker-v146.json`, `browser-p0-round99.json`, `browser-p0-round100.json`.

Current local candidate verification: 633 tests passed in each of two sequential credential-stripped runs; responsive matrix 704/704; safe-area browser matrix passed twice over 820×1180, 390×844, 360×800 and 320×740; offline shell v79 passed twice. Fresh strict production-image catalog recheck completed 41 content-checked operations per round, reported two provider-only operations unavailable, blocked the SSRF case, and had zero failures. One earlier run recorded a 359.314-second Markdown timeout; its root cause is unknown despite a successful repeat and 7.881-second standalone converter probe. Keep it visible as a reliability risk. Fresh redacted Gitleaks scans of `web/` and the v23 artifact tree found zero findings; history and ignored runtime secrets are outside scope. Release remains HOLD. Evidence: `pytest-current-v153-summary.json`, `browser-id27-narrow-zoom-layout.json`, `browser-id312-studio-tablet-layout.json`, `browser-v146-docker-offline-pwa.json`, `browser-id28-v146-current-image-catalog-catalog-v146-recheck-2026-11-20.json`, `probe-id28-markdown-runtime-v146.json`, `gitleaks-v153-web-redacted.json`, `gitleaks-v153-artifacts-redacted.json`.


## v142 and v147 current-candidate regression follow-up (2026-11-21)

A current P0 reproduction found first-frame/resize placement of the Studio restore toast could overlap the variable-height toolbar. Synchronously positioning it and observing toolbar/page/dock geometry fixed the reproduced case. Current P0 rounds 103/104 passed 60/60 each, zero errors, with restore toasts below the desktop and mobile toolbars and no button overlaps. Full-suite v156 passed 635 tests twice; the current-source route matrix passed 704/704; v82 service worker loaded offline twice. The real 69-page PDF resize harness passed twice at 390/320/820/390px. A v147 production-mode image with four UID-1001 workers passed health, content-checked 69-page export, toolbar and toast checks; its strict 44-operation catalog passed twice (41 verified completed outputs, 2 expected provider-only unavailable, 1 SSRF blocked, no other failures/page errors). ID122's latest 4× CPU mobile profile still exceeded the 250ms target (633ms/472ms) and remains partial. Evidence: `browser-p0-round103.json`, `browser-p0-round104.json`, `pytest-current-v156-summary.json`, `browser-id27-narrow-zoom-layout.json`, `browser-id122-canvas-area-width-cache.json`, `browser-id122-mobile-69page-studio-export_v142_final_20261120.json`, `browser-id28-v147-current-image-catalog-catalog-v147-recheck-2026-11-21.json`, `browser-v147-docker-offline-pwa.json`, `docker-id122-v147-runtime.json`.

Fresh Gitleaks v8.24.2 scans (100% redaction) on 2026-11-21 found zero findings in the current `web/` tree (3.21 MB) and v23 audit artifacts (31.40 MB). Git history, ignored `.env`, and TLS key material were not scanned. Evidence: `gitleaks-v157-web-redacted.json`, `gitleaks-v157-artifacts-redacted.json`.

## Read-only production recheck and provider smoke (2026-11-21)

The live site still serves app.js v91, organizer v14, CSS v51; health returns 200/ok, four workers and 24-hour TTL. Real Chromium visited 44 routes × seven widths × two rounds (616 checks); all 88 layout failures were topbar overlap at 1024px, with no JS errors. Local v142 passes the 704-check responsive matrix; deployed behavior remains open until the owner deploys and we repeat this matrix live.

Public five-page synthetic AI probe: `/api/ai/capabilities` returned available, but summary mode was `offline_extractive` with citations 1–5, not provider synthesis. Spanish attempts returned safe HTTP 422 at 36%/32% translation coverage; Hindi attempts returned HTTP 429 twice. No invalid PDF was emitted and the browser had zero page errors. No real payment was made. Keep IDs 1, 2 and 27 PARTIAL for deployed/provider retest. Evidence: `browser-id27-live-layout-2026-11-21.json`, `browser-live-ai-2026-11-21.json`.

Post-recheck Gitleaks v8.24.2 scan of the updated 31.73 MB artifact tree found zero findings with 100% redaction (`gitleaks-v158-artifacts-redacted.json`); Git history and ignored runtime secrets remain out of scope.

## ID 1 — bounded translation repair follow-up (2026-11-21)

Reproduction: controlled provider failed the initial 10-segment batch with HTTP 504. Pre-fix four-request repair ceiling could only cover eight of ten IDs. Fix: allow up to 16 small repair requests while missing segments make progress and the document deadline remains. Focused pytest passed 2/2, including a multi-round one-segment partial recovery case. Two real local Chromium rounds on `/translate-pdf` verified five repair requests, HTTP 200, 100% text/character coverage, correct order and translation of all ten page markers, source text removed, content-checked PDF downloads, and zero browser errors. Full suite passed 636 tests twice (`pytest-current-v158-summary.json`); browser evidence: `browser-id1-failed-batch-repair.json`. Live translation remains unresolved (Spanish 422, Hindi 429), so ID 1 stays PARTIAL pending post-deploy/provider retest.

## ID 25 — PDF/A production image re-verification (2026-11-21)

Earlier reproduction found Windows host lacked Ghostscript and the requirement had only dependency-gating UI evidence. The v147 production-mode Docker Chromium catalog now completes PDF-to-PDF/A in both rounds. Validated each exact downloaded 69-page artifact: strict PDF parse, PDF/A-1b XMP (part 1, conformance B), GTS_PDFA1 sRGB output intent, embedded non-empty 3-channel ICC profile, Ghostscript 10.05.1 producer, and page 1/69 markers. ID 25 was already FIXED LOCALLY in the item register; this strengthens that status without changing counts. Evidence: `browser-id28-v147-current-image-catalog-catalog-v147-recheck-2026-11-21.json`, `id25-current-v147-pdfa-structure.json`, and `verify_id25_current_docker_pdfa.py`.

Latest v23 artifact Gitleaks recheck: v8.24.2 scanned 31.76 MB with 100% redaction and reported no leaks. Git history, ignored `.env`, and TLS private-key material were out of scope. Evidence: `gitleaks-v159-artifacts-redacted.json`.

## Current production-image verification v148 (2026-11-21)

Built current source as `paperplane-v23-audit:codex-v148` (`sha256:7e4a1db49661f38cf4f9d5230e565dce119c40693dec092f9add43072ab444d0`). Its health check returned `ok` with four workers. Both Chromium 44-operation catalog rounds produced 41 content-checked downloads; Summarize/Translate were unavailable without provider credentials, the unsafe SSRF URL was blocked, and there were no other failed operations or browser errors. The exact two PDF/A downloads passed strict PDF/A-1b/ICC/page-marker checks. The isolated v148 container was stopped/removed; `paperplane-visible-v141` was verified healthy and left unchanged. No live production request or real payment was made. Evidence: `docker-build-v148.log`, `docker-id28-v148-runtime-catalog-v148-recheck-2026-11-21.json`, `browser-id28-v148-current-image-catalog-catalog-v148-recheck-2026-11-21.json`, `id25-current-v148-pdfa-structure.json`.

Gitleaks v8.24.2 post-v148 artifact rescan: 32.38 MB, 100% redacted, no leaks (`gitleaks-v160-artifacts-redacted.json`). Git history, ignored `.env`, and TLS private-key files are excluded.

## ID 106 live replay retest (2026-11-21)

Replayed one synthetic one-page guest Merge submission to `https://paperplane.qd.je` with the same hidden idempotency key. First response 202; replay 200 and `idempotent=true`, same job; one completed content-checked download; zero page errors. One temporary production guest job was created. ID 106 remains PARTIAL because the deployed client is app.js v91 and the historical long-processing stall remains unverified. Evidence: `browser-id106-live-idempotency-2026-11-21.json`, `browser_id106_live_idempotency_20261121.py`.

Latest post-ID106 evidence Gitleaks scan: 32.39 MB, 100% redacted, no findings (`gitleaks-v161-artifacts-redacted.json`); no Git history or ignored runtime secrets were scanned.

## v148 current-image 69-page Studio browser check (2026-11-21)

Two real Chromium rounds on disposable v148 production-mode container uploaded 69-page `notes.pdf` at 390×844 with 4× CPU throttle, rendered organizer thumbnails for pages 1 and 40, performed mode/selection actions, and downloaded outputs preserving all page text/order. Each output 5,535,231 bytes, with no browser errors. Run times were 17.79s/18.94s; this check did not instrument long tasks, so ID122's 250ms target remains open. Evidence: `browser-id122-docker-codex-final-v142-v148.json`, `docker-id122-v148-studio-runtime.json`.

Post-v148 Studio evidence artifact recheck: Gitleaks v8.24.2 scanned 32.41 MB with 100% redaction and found no leaks (`gitleaks-v162-artifacts-redacted.json`). Git history, ignored `.env`, and TLS keys remain excluded.

## ID 37 processing disclosure and compression feasibility (2026-11-21)

Settings/privacy copy omitted browser-local PDF-to-Word even though the browser toggle supports it. Updated static and dynamic support inventories, bumped app.js to v143 and the service-worker shell to v83. Two Chromium rounds (1366px and 390px) confirmed Settings lists PDF-to-Word (text-first), the PDF-to-Word browser toggle is enabled and selected, its text-first/image/layout/table limitations are visible, and Compress stays in server mode with local processing disabled; no overflow or page errors. Separately measured a browser-only pdf-lib load/save probe against `C:/Users/mdham/Downloads/notes.pdf`: two rounds preserved 69 pages and exact extracted text but reduced bytes only 0.193%. This is not sufficient to expose as PDF compression and does not establish preservation of unsupported PDF structures. Evidence: `browser-id37-processing-disclosure.json`, `browser-id37-local-compress-probe.json`; harnesses: `browser_id37_processing_disclosure.py`, `browser_id37_local_compress_probe.py`.
## Post-disclosure verification (2026-11-21)

The first full-suite run after the UI copy/cache update found stale v142/v82 source expectations and static supported-operation fixtures, plus a home/FAQ answer mismatch. Updated the regression expectations and matching server FAQ. The related test files then passed 140/140. Final sequential isolated full-suite run v160 passed twice at 636 passed / 4 existing warnings each (`pytest-current-v160-summary.json`, `pytest-current-v160-run1.log`, `pytest-current-v160-run2.log`).
## ID 37 current-source Docker recheck (2026-11-21)

Built current source as production-mode image v150 (`sha256:ce6c9b11f426043bc73a05efb9640a02d2b0638c63ab5d29f3feeb93a5c5b04a`). A disposable container reached healthy status with four workers. Desktop/mobile Chromium rounds verified the PDF-to-Word support/limitation disclosure and server-only Compress toggle. Two additional browser rounds downloaded valid 12-page text-first DOCX packages (50 paragraphs, 11 page breaks, all 12 page markers and accented text), with zero job posts or page errors. Test container was stopped and removed; synthetic credentials and tmpfs only, no provider credentials or payment. Evidence: `docker-id37-v150-runtime.json`, `browser-id37-processing-disclosure-v150-docker.json`, `browser-id37-local-pdf-to-word-v150-docker.json`, `docker-build-v150.log`.

## 2026-11-22 — ID 357 offline large-file regression

Disposable v152 production-mode Docker browser check, two rounds, 390px mobile viewport, network disabled. Cold offline Merge downloaded a content-checked two-page PDF and posted zero server jobs. Real 69-page `notes.pdf` opened in Studio offline; OffscreenCanvas worker remained active; page 40 canvas rendered. Zero page errors. Evidence: `browser-v152-docker-offline-pwa.json`, `docker-v152-offline-runtime.json`, `docker-build-v152.log`. Native camera/install remains a physical-device follow-up; no status promotion.

## 2026-11-22 — current-image catalog and smoke-script security correction

Disposable production-mode v152 image, 4 workers, all 44 operations in two Chromium rounds: 41 downloaded outputs passed content checks per round; SSRF probe was blocked; two provider-only operations unavailable with no provider credentials; zero page errors. The temporary container was removed. Corrected the legacy local smoke script's hardcoded password, API-key logging, mutating behavior, and unsupported Cloud Sync success claim. New version is restricted to loopback read-only health/integrations/catalog GETs; current local server exposed 44 operations. Focused tests 4/4 and full suite 642/642 twice. Evidence: `browser-id28-v148-current-image-catalog-current-v152-2026-11-22.json`, `docker-v152-current-catalog-runtime.json`, `pytest-current-v163-run1.log`, `pytest-current-v163-run2.log`.


## 2026-11-22 — Railway dynamic port and Docker health check

v153 exposed a Dockerfile health check hardcoded to 8501 even though the app honored Railway's injected PORT. Recorded the app/health-host 200 responses, unhealthy Docker status, and catalog pass in `docker-v153-railway-health-repro.json`. Updated the Dockerfile check to use `PORT` first. Rebuilt v154: app health 200, Railway health host 200, Docker health healthy, then two complete 44-operation browser rounds (41 content-checked downloads each, expected SSRF block, two provider-only skips, zero page errors). Full suite: 646 passed twice, four warnings per run. Disposable container removed. Evidence: `docker-v154-railway-runtime.json`, `browser-id28-v148-current-image-catalog-current-v154-railway-2026-11-22.json`.


## 2026-11-22 — Studio thumbnail encoder A/B trial and live layout check

Worker-side OffscreenCanvas.convertToBlob trial on a real 69-page PDF passed the content and interaction workflow in two Chromium rounds, but measured max long tasks 582/643ms and slower exports; change reverted. The live Paperplane root/health/assets now return 200, but read-only 1024px `/merge-pdf` still overlaps workspace tabs and right controls. Evidence: `browser-id122-mobile-69page-studio-export_offthread_blob_20261122.json`, `browser-live-assets-readonly-2026-11-22.json`, `browser-live-1024-layout-2026-11-22.json`.


## 2026-11-22 passive live security recheck

Read-only checks confirmed HTTP redirects to HTTPS; the HTTPS response has CSP, HSTS, `nosniff`, frame, referrer and permissions policies. Single GETs to `/.env`, `/.git/config`, `/.git/HEAD`, `/server-status`, and `/phpinfo.php` returned 404 with no sensitive markers in the sampled response. Gitleaks v8.24.2 scanned 35.46 MB of v23 audit evidence with `--no-git --redact=100` and found no leaks; a separate scan of the repaired local smoke script also found none. `pip-audit --strict` returned no known dependency vulnerabilities. These checks do not include `.env`, TLS private-key files, or Git history and do not clear the pending history/credential owner action. Evidence: `security-live-passive-readonly-2026-11-22.json`, `gitleaks-v163-artifacts-redacted.json`, `gitleaks-v163-smoke-script-redacted.json`, `security-pip-audit-v163.json`.


**ID 27 current-source compact-width recheck (2026-11-22):** Reran the full Chromium layout matrix against the current local source at 8 widths × 44 operation routes × 2 rounds (704 checks). Every route returned HTTP 200; zero overlaps, horizontal/visible overflow, outside-header controls, or browser errors were detected. This confirms the local candidate layout after the latest asset changes; the live deployment still serves the older CSS and retains the 1024px overlap. ID 27 remains PARTIAL pending deployment and live retest. Evidence refreshed: `browser-id27-narrow-zoom-layout.json`.


**Current-source P0 browser recheck (2026-11-22):** Repeated the complete local Chromium P0 harness twice against the current worktree. Both independent runs passed all 60 assertions with zero browser page errors (`browser-p0-round106.json`, `browser-p0-round107.json`; latest consolidated output `browser-p0.json`). This current-source check complements the 646-test full-suite runs recorded for the same candidate. It does not clear live deployment drift, provider credentials, physical-device, owner-review, or other explicitly partial gates.


**Current production-image volume and browser verification (2026-11-22):** Rebuilt the current source as Docker candidate `paperplane-v23-audit:codex-v155` (`sha256:777c6337c02876a78327ba12c5308dfb39bd72289a25ae496a5c511d941e70a9`). A disposable mode-0755 root-owned named volume was attached; the entrypoint prepared `/data` and its migration marker as UID/GID 1001, then ran PID 1 as UID 1001. With `PORT=18538` and `PAPERPLANE_PORT=8501`, `/api/health` returned 200/`ok` and Docker health reached `healthy`. A separate 18502 image-backed Chromium round content-checked seven local workflows (Forms, Metadata, Crop, Watermark and Scan/JPG conversion variants), had zero API job submissions and zero page errors. The container and named volumes were removed; dummy secrets, TEST payments disabled, and no production data were used. Evidence: `docker-v155-root-volume-runtime.json`, `docker-v155-browser-runtime.json`, `browser-id37-docker-v155-content-smoke.json`.

**Current candidate regression recheck (2026-11-22):** The 353-item audit's current-source compact-width matrix passed 704/704 route/viewport checks, and the P0 Chromium matrix passed twice at 60/60 each with zero page errors (`browser-p0-round106.json`, `browser-p0-round107.json`). The isolated complete pytest suite passed sequentially twice at 646 tests each, four existing warnings per run; environment credentials and dotenv loading were disabled (`pytest-current-v155-summary.json`, `pytest-current-v155-run1.log`, `pytest-current-v155-run2.log`). These local results do not close the report's live deployment, provider, owner-only, or physical-device gates.


**Self-found frontend loading/performance follow-up (2026-11-22, app.js v146 / shell v87):** Removed eager global loading of Google Identity Services and Cashfree. Google auth configuration is now requested only when the sign-in dialog opens; GIS is requested when that dialog is opened, while Cashfree is requested only after a signed-in user starts checkout. A controlled real-Chromium round proved zero auth-config or third-party SDK requests at initial page load, then one mocked auth-config/GIS request on sign-in and one mocked Cashfree SDK request on sandbox checkout; the checkout API and SDK were stubbed and no payment was submitted (`browser-id365-lazy-third-party-sdks.json`). Added a permanent frontend contract and updated the Cashfree contract to enforce lazy loading. The focused frontend/v23 modules passed 130 tests. The complete credential-stripped suite then passed twice at 647 tests each, four existing warnings per run (`pytest-current-v158-summary.json`, run1 and run2).

The fresh 69-page mobile Studio workflow on app v146 preserved exact page text/order, rendered page 1/40 organizer thumbnails, kept selection/navigation/slot recovery, and content-checked exports in both rounds with zero page errors (`browser-id122-mobile-69page-studio-export_lazy_sdk_v146_followup.json`). Maximum long tasks were 538ms and 905ms; the <250ms target remains unmet and ID 122 remains PARTIAL. The offline shell v87 cold-cache merge passed twice with marker-preserving PDF downloads and zero job submissions/page errors (`browser-id357-offline-local-merge.json`). The current-source P0 browser matrix passed twice after correcting the harness to measure the settled toast position rather than its entrance animation: 60/60 in each round, zero page errors (`browser-p0-round109.json`, `browser-p0-round110.json`). The earlier transient geometry assertion had an empty overlap list and sampled the toast while its 250ms animation was still moving; this measurement-only timing has been fixed in `browser_p0.py`.

A Docker production image build command for tag `paperplane-v23-audit:codex-v158` exited successfully, but the Docker Desktop Linux engine stopped responding before image inspection or container-backed browser verification. Therefore this client revision has local Chromium evidence and a build invocation, but no verified v158 runtime claim. Earlier v155 root-owned-volume/UID-drop and seven-workflow Docker evidence remains valid only for v155. No commit, push, deployment, or payment occurred.

**Self-found Studio restore-toast resize fix (2026-11-22, app.js v150 / shell v91):** A 390px Studio layout check found that feedback toast positioning could retain the desktop location after viewport resize because repeated layout notifications cancelled a two-animation-frame debounce. Reduced the scheduler to one animation frame, observe Studio activation and root size changes, and hide the live toast when there is no safe gap between the rendered PDF and the mobile dock. Two independent current-source Chromium P0 rounds passed 60/60 with zero page errors; both measured desktop toast placement clear of toolbar/PDF and mobile toast at 1×1 visually-hidden size with no PDF/dock overlap (`browser-p0-round112.json`, `browser-p0-round113.json`, consolidated `browser-p0.json`). The current app v150/shell v91 offline local-merge smoke passed twice with marker-preserving, content-checked two-page PDFs and zero `/api/jobs` posts or page errors (`browser-id357-offline-local-merge.json`). The focused frontend/v23 tests passed 130/130 and the isolated full suite passed 647/647 twice, four existing warnings per run (`pytest-current-v150-summary.json`, `pytest-current-v150-run1.log`, `pytest-current-v150-run2.log`). This closes the resize/toast regression only; it does not change the 324/28/1 register or clear the ID 122 performance, live, provider, legal, owner, Docker-current-image, and physical-device checks.

**Fresh production-image catalog verification (2026-11-22, v159):** Built `paperplane-v23-audit:codex-v159` from app.js v150 / service-worker shell v91 (image ID `sha256:57ad564523e1ecd4e78aaa6a658820a193956eb5325c4a33c9f7cf0e38ea99b4`). Production-mode runtime health returned `ok`; the app ran four workers as UID/GID 1001 with tmpfs data storage and disposable dummy secrets. Two full Chromium catalog rounds each accounted for all 44 operations: 41 downloaded outputs were content-checked, two provider-only actions were unavailable without credentials, the SSRF case was blocked, and there were zero other failures or browser page errors (`browser-id28-v159-current-image-catalog-current-v159-2026-11-22.json`, `docker-v159-current-catalog-runtime.json`). The initial full-catalog attempt had one job remain at 20% until the runner timeout; the same fixture/image conversion then passed twice in isolation with two-page color-pixel checks, and a clean full-catalog rerun passed both rounds. No real payment, production data, commit, push, or deployment occurred. This closes the current-image catalog check for this candidate but leaves the report's 28 partial and 1 blocked register entries, including live/provider/owner/legal/physical-device checks and ID 122 performance, unresolved; verdict remains HOLD.

**ID 122 app v150 mobile recheck (2026-11-22):** Repeated the exact 69-page, 5.46 MB `notes.pdf` workflow in two fresh 390×844, DPR-3 Chromium contexts under 4× CPU throttle on the updated source. Both rounds preserved exact page text/order and all 69 organizer cards; pages 1 and 40 rendered, selection/navigation/slot recovery passed, and the 69-page export was content-checked with zero page/console errors or horizontal overflow. First-page readiness was 8.40s and 5.84s; export took 1.46s and 1.03s. Maximum main-thread long tasks were 853ms and 318ms, still above the 250ms target. The toast fix did not regress functional PDF output, but this does not close ID 122 or clear its performance/physical-device gate. Evidence: `browser-id122-mobile-69page-studio-export_app150_shell91_followup_20261122.json`.

**ID 27 current-source responsive recheck (2026-11-22, app v150 / shell v91):** Re-ran all 44 operation routes at eight viewport widths across two Chromium rounds on the latest local source. All 704 route/viewport cases returned HTTP 200 and had zero topbar overlaps, clipped/outside controls, horizontal or visible overflow, or page errors (`browser-id27-narrow-zoom-layout.json`). This confirms the current local layout only; the deployed site remains on app.js v91/styles.css v51 with the separately recorded 1024px overlap, so post-deploy live closure is still required.


2026-11-22 — ID 122 follow-up: `browser_id122_mobile_69page_studio_export.py` on app v151/shell v92 completed both 4× CPU mobile rounds with content/order checked 69-page exports, zero browser errors, and no overflow. Readiness was 5.83s/8.39s, maximum main-thread tasks 409ms/663ms; <250ms remains open. `browser_id122_render_request_dedupe.py` confirmed that an overlapping non-forced same-page request reuses the in-flight render while `force:true` still schedules a follow-up render. Full pytest passed 647 twice; P0 Chromium passed 60/60 twice; cold-offline local merge passed twice on app151/shell92. The first full suite pass after cache-version bump exposed 11 stale source-version assertions; updated them and reran all tests cleanly. Docker v159 remains app150/shell91 and has not been rebuilt for this candidate.


2026-11-22 — Built exact app v151/shell v92 production image `paperplane-v23-audit:codex-v160` (`sha256:ec3fe9739ad317cbf83df81586bb1c363c0af01d8093e3e2ad1a1a18034d64a6`). Production health passed with four UID-1001 workers; current-image offline merge/PWA and two real 69-page Studio Chromium exports passed. All page text/order was preserved, no errors/overflow; 4× CPU long-task maxima remained 502ms/311ms, so ID 122 is not closed. The disposable container was removed.


2026-11-22 — Latest-candidate broad retest: v151/shell v92 current-source Chromium layout matrix passed 704/704 cases across 44 routes × 8 widths × 2 rounds. Exact v160 production Docker image passed the two-round 44-operation catalog (41 content-checked outputs, two provider-only actions unavailable without credentials, one SSRF request blocked, zero other failures/page errors). The historical isolated 20% stall did not recur; its original trigger remains unknown. Docker container was removed.


2026-11-22 — Final candidate refresh: app.js v152/shell v93 with 16-page Studio stack batches. Full suite 647 passed twice; current P0 60/60 twice; layout matrix 704/704; cold-offline local merge passed twice. Exact v161 production image digest `sha256:231cc30ca94616db5024d40084827e2a1410e57e04d890036ab3d1be98611fd2` passed health, four UID-1001 worker check, Docker offline PWA/local merge, two 69-page Studio exports, and two 44-operation catalog rounds (41 checked outputs, 2 provider-only unavailable, SSRF blocked, no other failures/errors). Docker Studio long-task maxima were 420ms/328ms; ID 122 is still partial. A batch-4/scheduler.yield experiment was reverted after 9.40/14.11s readiness, one 47.91s export, and 594/1445ms maxima.


2026-11-22 module-script compatibility trial (rejected): Changed app.js to type=module to reduce the single classic-script parse task. The real 69-page Studio workflow passed after adding temporary exports for harness-facing helpers, but the broader P0 browser harness then failed at its summary flow because another formerly classic-script global, `showSummaryDeskResult`, was undefined (earlier pass first stopped on `setActiveStudioPage`). This exposed implicit global coupling; the trial was reverted to the previously verified classic-script app.js v152/shell v93. No module trial result is counted as a release pass. The batch-16 Studio renderer and explicit verified deduplication remain. Browser logs: `browser-id122-module-v152-shell94-run.log`, `browser-id122-module-v152-shell94-rerun.log`, `browser-id122-mobile-69page-studio-exportmodule_v152_shell94_rerun_20261122.json`; P0 console exception was `showSummaryDeskResult is not defined`.

2026-11-22 ID 122 bitmap transfer candidate: replaced main-thread 2D drawImage(ImageBitmap) copy with itmaprenderer.transferFromImageBitmap for Studio worker output. A 2D canvas clone is allocated only if the worker path fails, because canvas context types cannot be changed after selection. Bumped app asset to v153 and shell to v94. Pending full mobile 69-page browser regression/performance measurement; candidate is not accepted until fallback and output-content checks pass.

2026-11-22 ID 122 follow-up: worker-failure injection reproduced a second-page fallback bug after bitmaprenderer had already rendered that canvas. In the globally disabled-worker branch, canvas.getContext('2d') returned null because the canvas retained its bitmaprenderer context; PDF.js then threw Cannot read properties of null (reading 'canvas'), with a secondary enderTasks page error. Added one guarded 2D-context acquisition helper that reuses an existing 2D context or clones the bitmaprenderer canvas and validates a fresh 2D context before rendering. Bumped app to v154/shell v95. This is a self-found failure-path fix; it remains pending browser recheck.

2026-11-22 ID 122 slot-replacement follow-up: the worker-failure browser probe then showed jumpToStudioPage(2) could accept a deduplicated promise that belonged to a detached slot and leave the newly recreated page blank. The navigation now verifies the current live slot canvas has data-rendered=true and force-renders if a stale queued result returned success. App/cache advanced to v155/shell v96. Verify normal worker, worker-disabled, and injected-failure runs before accepting.
