309 items are listed in the v21 checklist; the document separately describes a 310-item tracker.

## ID 2: offline brief drops later pages

The prior implementation created notes in 12-page sections, then passed all notes back through the offline extractor, which retained at most eight early lines. Provider failures could therefore omit later sections. The local regression generates 69 distinct pages, forces the provider to fail, and verifies page 1 and page 69 text and citation appear. The updated fallback retains section notes and extracts one cited line per page. Provider timeout while scheduling a later section also uses the local section fallback.

Verification: `pytest -q tests/test_launch_audit_v21.py tests/test_launch_audit_v13.py tests/test_ai_workflows.py`: 70 passed, 1 warning. This is a controlled test, not a production-provider or browser verification.

Other checklist items and full release verification are not complete in this continuation. Credential rotation and a real payment remain owner actions. No commit, push, deploy, or payment was performed.

## ID 283: compression image corruption

The compressor replaced image stream bytes without replacing the PDF image dictionary, leaving mismatched metadata. It also rasterized entire documents at very low resolution to chase size targets. The image replacement now updates the image object through PyMuPDF, skips images with soft masks, and avoids forced page rasterization and additional aggressive quality passes. When the target cannot be reached, the result reports that it was not achieved. Tests render a red image and check searchable text for both the 100 KB and balanced presets.

Focused tests: 23 passed. A Chromium regression run completed and content-checked two runs each on a 6.1 MB image-heavy input for compression, watermark, and page numbering, as well as the other recorded v20 checks. The full suite passed twice: 480 passed, 1 warning on each run (106.94 s and 109.45 s). These checks do not complete the 309-item audit or establish deployment readiness.

## v21 continuation: browser layout, tool catalog, PDF/A, and regression pass

- Confirmed the attached prompt has **309 elite-list items**; it separately describes a tracker with 310 rows. The full 309-row implementation and evidence matrix is not complete.
- On the local app, Chrome viewport captures found horizontal overflow at 820 px in Settings and a sidebar covering Studio at 820 px. Updated layout rules, modal sizing, and modal/toast stacking; signature/security dialogs are bounded to the viewport with internal scrolling.
- Browser layout matrix: 44 tool routes at 390, 820, 1366, and 1920 px = 176 captures. All returned without horizontal overflow or page errors. Five key views also have before/after captures, and signature dialog bounds/stacking were measured at each width.
- A local browser catalog round exercised all 44 operations. 39 completed with downloaded outputs content-checked; 3 were unavailable (OCR and AI summarize/translate without configured runtimes/credentials); one local-URL HTML conversion was blocked as expected by SSRF protection; PDF/A failed in the Windows host because it has no Ghostscript executable.
- Installed Ghostscript, ICC profiles, and Tesseract in the available WSL Ubuntu environment for runtime checks. Extracted and executed the application PDF/A conversion implementation there: two valid PDF/A outputs reopened and retained source text. This proves the converter/profile logic under Linux; the Windows-hosted API route still cannot invoke the WSL Ghostscript binary directly.
- Added mixed-page Word conversion support for page images and detected tables. Regression checks verify editable text, image media, and table cells.
- Final full suite: 481 passed twice, one existing Starlette/httpx warning each (96.86 s and 109.01 s). One prior run had a 15-second subprocess startup timeout in an existing admin-startup test; raised that test's bound to 45 seconds and the following two full runs passed.
- Remaining checklist rows, provider dependencies, owner credentials/payment, and post-deploy verification remain open; no READY verdict is supported.

## Live production continuation — 2026-11-16

- Tested `https://paperplane.qd.je` in Chromium. Downloaded and verified the public five-page arXiv PDF `2405.12132`, plus a synthetic DOCX for upload coverage.
- 44 production routes × 4 viewports (390, 820, 1366, 1920): 176/176 HTTP 200; no measured horizontal overflow, route exceptions, or page errors. A simple DOM naming check on all 44 routes found no unnamed visible buttons/links, unlabeled visible inputs, or images missing `alt`.
- Live API upload/download jobs completed with content checks for merge, split, rotate, compression, PDF-to-text, PDF-to-Word, Word-to-PDF, AI extract, and summary. Scan-to-PDF also succeeded on retry and retained its raster page. The first scan request returned HTML instead of JSON and is recorded as an observed transient failure.
- Live OCR upload was accepted (202), but the test polling window ended after 300 seconds without observing a terminal status. Runtime capability reports `deu`, `eng`, `fra`, and `spa` packs installed. Local OCR on the same one-page image-only sample completed in 3.93 seconds and extracted 4,651 characters; this does not establish the live job's state.
- Found an overbroad privacy description in the tool desk sidebar. Updated it to name the selected tool and accurately describe browser-local versus temporary server processing. A local Chromium regression confirmed Merge says local/not uploaded and OCR says server upload. The live deployment has not received this change.
- Full suite after the privacy-copy change: 481 passed twice, one existing Starlette/httpx deprecation warning per run. Logs: `pytest-live-continuation-run1.log`, `pytest-live-continuation-run2.log`.
- This is partial live feature coverage, not closure of the 309-row list. Live OCR status, remaining feature flows, owner credential rotation, real payment, and post-deployment retesting remain open. No deployment, commit, push, payment, or credential rotation was performed.

## v22 Phase -1: P0 reproduction before new fixes

Checklist count verified from the previously attached v21 PDF: **309 elite items**. This section records the seven P0s before any new v22 implementation. The working copy is currently `main` at `172afcc` with the prior v21 changes uncommitted; there is no local `launch-audit-v21` branch, and no new branch was created.

### ID 101 — exposed admin credentials / history purge

- **Steps:** Inspected startup configuration, the existing admin-secret workflow, and the repository secret-scanning workflow; ran the targeted `test_101_admin_settings_required_at_startup` cases.
- **Observed:** `server.py:194-202` fails startup if either admin environment setting is missing; no credential fallback remains. `.github/workflows/secrets.yml` runs Gitleaks over incoming history. Targeted test cases prove both settings are required.
- **Cause / remaining gap:** Historical public commits and working live credentials cannot be invalidated in code. Rotation and the post-rotation old-value rejection check require owner-controlled production values. The repository has no prepared secret-redaction invocation artifact yet.
- **Plan:** Add a purge-preparation script that reads old values only from protected environment variables, never prints or stores them, and is run only after the owner commits the code. Keep rotation and force-push as owner steps.

### ID 1 — live Spanish and Hindi translation failures (flaky)

- **Steps:** In Chromium on the live site, uploaded the same three-page public PDF to Translate twice for Spanish and twice for Hindi; waited for job terminal state and inspected each status.
- **Observed:** All four jobs were accepted (202), then failed in 93.6–95.1 seconds with `No text was translated. The translation service did not produce a translated PDF; please retry later.` No translation outputs were created. Evidence: `reports/launch-audit-v21/live-translate-p0.json`. Controlled local content checks independently produce valid three-page Spanish and Hindi outputs twice each: `p0-translate-controlled.json`.
- **Code cause:** `ai_engine.py:1950-1986` isolates and records failed provider batches, but `ai_engine.py:2031-2034` discards their safe failure class when zero blocks translate and raises the generic no-text error. `_call_selected_provider` uses a configured fallback only when fallback credentials are present; production fallback configuration cannot be inspected without owner admin access.
- **Plan:** Preserve and safely surface the aggregate upstream status (429/auth/timeout/invalid response) when every batch fails, retain the existing bounded retries and fallback path, and add tests for primary 429 → fallback success plus failure-status mapping. Live provider acceptance remains open until both languages produce clean downloads twice.

### ID 2 — 69-page Executive Brief coverage / 12-page omission

- **Steps:** Forced provider failure on the exact 24-page diagnostic; placed cancellation on page 18, the ₹900,000 no-spend decision on page 20, and the 15 December 2026 deadline on page 24. Also ran existing controlled 69-page brief tests.
- **Observed:** Current local fallback included cancellation, reference, no-spend marker, amount, deadline, and `[Page 24]`; the 69-page controlled test includes the first and last pages. `summarize_pdf` chunks all pages up to its explicit 120-page product limit at `ai_engine.py:1207-1211,1245-1286`; `tests/test_launch_audit_v21.py:10-25` covers page 69. The live five-page summary passed, but no live 24/69-page full-provider proof was run.
- **Cause / plan:** The old silent 12-page cap is absent. Keep the bounded 120-page ceiling explicit and verify output coverage/citations; production-provider completeness on the 69-page source remains open.

### ID 4 — Cloud Import direct-download / Drive viewer URL

- **Steps:** Chromium posted the v22-corrected W3C `testfiles` PDF URL to the live Cloud Import endpoint twice and content-checked each response. The exact owner Drive link was not fetched because the v22 evidence says it returns an image, not the intended PDF.
- **Observed:** Both direct imports returned HTTP 200, `dummy.pdf`, `application/pdf`, 13,264 bytes, one page. Evidence: `live-cloud-direct-repro.json`. Local controlled Drive confirmation tests preserve the resource key and reject unsafe redirect hosts; `server.py:6131-6189` follows only validated Drive confirmation links and distinguishes HTML/non-PDF content.
- **Cause / plan:** The corrected direct acceptance path is clean twice. The owner-provided Drive URL still cannot prove PDF import until the owner supplies the actual shared PDF link/file. Keep detailed upstream HTTP/content-type errors and SSRF validation intact; do not guess a different owner file.

### ID 102 — feedback submit versus admin delivery

- **Steps:** Ran `test_93_102_account_and_feedback_visible_after_process_restart`; ran the isolated Chromium smoke workflow that submits synthetic feedback and waits for it to appear in the already-open admin tab without a manual refresh.
- **Observed:** Both controlled checks passed. The restart test writes through `/api/feedback` and reads through `admin_get_feedbacks()` after process restart; `scripts/browser_v14_smoke.py` logged `ID 102: submitted feedback appeared in the open admin tab without refresh`.
- **Cause / plan:** No current local split-store failure reproduced. Production admin-list verification would require an authenticated owner/admin session, which the v22 instruction forbids changing; use controlled same-database/restart evidence and retain live verification as an owner/Muse retest.

### ID 98 — Cashfree production payment

- **Steps:** Ran the controlled production-mode gate test `test_98_misconfigured_production_is_never_reported_ready` and the sandbox webhook tests. Did not initiate a live checkout or payment.
- **Observed:** A production environment configured for TEST is rejected with 503; simulation is denied with 403; signed sandbox events are checked with controlled keys. `config.py:149-164` selects the gateway host from `CASHFREE_ENV`; `server.py:3688-3724,3974-3995` gates production and simulation paths.
- **Cause / plan:** Source safely distinguishes environments, but the deployed site still reports sandbox in prior evidence. Only the owner can set real production keys and run the explicitly prohibited real payment. No code change may weaken production payment gates.

### ID 93 — account/database persistence across deployment

- **Steps:** Ran `test_93_102_account_and_feedback_visible_after_process_restart` and `test_93_refuses_to_switch_existing_volume`; inspected the data-directory/volume configuration. Did not create, delete, or modify live accounts and did not deploy.
- **Observed:** A synthetic account and feedback row remain readable from a second process against the same temporary database; mount validation rejects a changed or read-only volume. `config.py:19-24`, `docker-compose.yml:15-30,62-67`, and `server.py:150-184` identify the app data path and verify mounted storage.
- **Cause / plan:** No local code failure reproduced. The exact create-account → platform redeploy → login sequence is a production action and cannot be performed without altering live account data/deploying; prior deployed survival evidence is supporting but not the formal test. Keep the formal production check open for the owner/Muse.

### Regression controls run before v22 edits

- `pytest` targeted P0 group (admin settings, production payment gate, translation retries/refund, 69-page brief, Drive confirmation, restart persistence, volume protection, guest quota, and v21 brief/compression/Word tests): **15 passed, 1 deprecation warning**.
- `python scripts/browser_v14_smoke.py`: controlled Spanish/Hindi 3- and 69-page translations, 69-page brief, Studio deletion/reload, synthetic 60 MiB merge, cancellation, and feedback delivery passed; this is mock-provider/local proof, not live-provider proof.
- `python reports/launch-audit-v18/browser_studio_export.py`: two consecutive Studio exports downloaded and checked all 10 page-order markers.
- `tests/test_launch_audit_v21.py` already verified both image-compression presets preserve the rendered image and searchable text; full suite was also rerun twice before this reproduction phase.

## v22 continuation — implementation and verification (2026-11-16)

### Correction to ID 101 preparation note

The Phase -1 note above said there was no purge-preparation script. That statement was incorrect: `scripts/prepare_admin_history_purge.py` is already present from prior local work. I inspected it: it obtains the historical value from the known commit without printing it, creates a new isolated mirror outside the worktree, redacts commit messages and objects, scans the rewritten mirror, and leaves a warning marker until verification passes. I did not execute it because it rewrites history and the v22 work is uncommitted; credential rotation and any coordinated publish remain owner-controlled. No prohibited mirror was touched.

### New implementation and checks

- ID 1: `ai_engine.py` now exposes safe provider failure classes for fully failed translation batches; `server.py` maps upstream 429 responses to HTTP 429. The provider connectivity check uses a configured fallback and reports `fallback_active`. Regression tests cover primary rate limit → fallback success and failed translation status mapping. The prior live four-job run remains the current live evidence (all four failed); therefore this is a code fix, not a live acceptance pass.
- ID 241: `server.process("page_numbers")` now substitutes `{n}` and `{total}` in the literal format from the UI. The six-page test checks `Page 1 of 6` and `Page 6 of 6` in extracted PDF text.
- ID 283: compression preserves transparent/palette/CMYK image streams and renders the completed candidate to detect large newly black areas. On such a regression it preserves the readable source and flags the unmet target. Both the 100 KB preset and Balanced were run against `compression-mixed-6mb.pdf` (actual 16,115,831 bytes, five mixed image/text pages); both outputs retained page geometry and comparable rendered RGB means. Details: `reports/launch-audit-v22/compression-render-check.json`. This controlled fixture does not prove every color-space or image-mask case.
- ID 299: public billing status no longer serializes a Cashfree order ID. A regression test supplies a user containing a private order ID and verifies it does not appear in the endpoint JSON.
- ID 309: Scan-to-PDF takes `page_size` and supports A4, Letter, or original image dimensions at 200 DPI. A visible native select and accurate instructions were added. Local Chromium uploaded an image and content-checked downloads for each option. Result page sizes were A4 841.89×595.28 pt, Letter 792×612 pt, and original 576×432 pt for a 1600×1200 px input. Evidence: `reports/launch-audit-v22/browser-scan-pages.json`.
- ID 173: removed workflow copy promising unavailable page selectors, ordering controls, highlighted comparison output, and scan controls. Updated Scan copy to describe the new supported paper choices.
- ID 246: added `server_tokens off` to both nginx templates; production nginx template already contains CSP directives. No nginx/Docker runtime is available locally to verify actual response headers.
- App and stylesheet references in `web/index.html` now use v22 cache keys.

### Current browser and suite run

- Local Chromium loaded all 44 operation routes at 390, 820, 1366, and 1920 px: **176 checks, 0 route failures, 0 measured horizontal overflow**. Evidence is in `reports/launch-audit-v22/route-layout-matrix.json`.
- Local Chromium catalog workflow attempted all 44 operations: 39 completed with output validation; OCR, summarize, and translate were unavailable without local runtime/provider credentials; HTML-to-PDF correctly blocked the local URL under SSRF protection; PDF/A could not run because Windows has no Ghostscript executable. See `reports/launch-audit-v21/browser-catalog.json`.
- Full suite: **488 passed, 1 existing Starlette/httpx deprecation warning** twice. Logs: `reports/launch-audit-v22/pytest-v22-run1.log`, `pytest-v22-run2.log`.
- `git -c core.whitespace=cr-at-eol diff --check` passed; Git reports only a CRLF normalization notice for `tests/test_text_layer_v18.py`.

### Self-analysis outcome

The scan-page regression did not change pagination, input handling, or source image proportions in the controlled browser downloads. The route matrix found no viewport overflow after the new page-size control and cache-key update. Billing status regression confirms the order identifier is absent, while checkout still uses the persisted order value internally. Compression's visual guard preserves the owner-selected default, but its synthetic check is narrower than Round 12's supplied 6.34 MiB test file. Translation status handling is improved, but the deployed service failure is still unresolved. No full per-ID loop was completed; deployment readiness therefore remains unproven.

