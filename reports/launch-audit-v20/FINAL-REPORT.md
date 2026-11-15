# Paperplane v20 Engineering Report

## Release assessment

**Not deployment ready.** The v20 checklist contains 298 items. This work did not close every open/to-verify/not-tested item, so a READY verdict would be false. The repository changes and local test evidence are uncommitted on `launch-audit-v20` from `66cd0cd`. Nothing was committed, pushed, deployed, or charged.

The eight P0 code paths received local work and controlled checks. Production-only assertions and some required owner inputs remain outstanding. Other P1/P2 checklist items outside the listed fixes also remain open; the full 298-row acceptance matrix has not been completed.

## Changes completed and locally verified

- **IDs 1 and 2:** Added bounded provider retries/backoff, encrypted optional fallback-provider configuration, per-batch translation failure isolation, safe failed-block logging, explicit translation warnings, 12-page brief chunks, and extractive fallbacks. Controlled Chromium runs checked Spanish and Hindi text layers on synthetic 3-page and 69-page PDFs, plus a 69-page brief. Production-provider quota/outage behavior and the owner’s exact source PDFs remain unverified.
- **ID 4:** Cloud import now preserves safe upstream status and content-type details and logs provider/host/status without logging signed URLs. The exact checklist Drive URL returned `image/png`; the listed W3C URL returned HTML. Both are rejected as non-PDF. Corrected public Drive and W3C PDF URLs imported locally.
- **ID 207:** Replaced the fixed upload percentage with XHR upload events and a named native progress element; added server phase logs. Files over 10 MiB now upload in 5 MiB chunks with per-chunk size/replay checks, session ownership checks, operation validation, rate limiting, expiry cleanup, and delete-on-client-error/cancel cleanup. A local Chromium run uploaded and merged a synthetic 60 MiB, 759-page PDF with a 10-page PDF through the chunked path; the downloaded 769-page PDF and selected page text were checked. XHR progress/cancel UI was also exercised. The owner’s image-heavy fixture was unavailable.
- **ID 292:** Split output is checked against requested page count and page content; Chromium downloaded and checked ranges 1–2 and 1.
- **ID 293:** Flatten bakes annotations/widgets; a downloaded browser result had no active annotation records.
- **ID 294:** A 6.1 MiB image-heavy PDF was run twice each through compress, watermark, and page numbering in Chromium; downloads were content-checked.
- **ID 295:** PDF-to-Word prioritizes editable text and rasterizes only image-only pages at 150 DPI; browser download contained editable text without page-sized raster images. The reported owner 5.7 MiB fixture was not available.
- **ID 296:** Compose trusted proxy configuration includes the observed gateway as an overridable value. Production peer-IP behavior remains unverified.
- **ID 298:** Annotation comments persist to annotation Contents; browser download was checked.
- **ID 299:** Public billing status omits Cashfree configuration/environment details; admin UI omits the database path; lock-screen wording and Nginx server tokens were hardened.
- **ID 301:** Broad document questions sample document text and sparse-text answers are explicit; browser checked a sparse 24-page PDF. OCR runtime is not installed in this host.
- **ID 302:** Spreadsheet fallback derives columns from visual line positions and x-gaps; browser downloaded and checked workbook cells.
- **ID 101 code preparation:** Gitleaks CI workflow is present. An isolated history-purge preparation was generated and object-scanned at `C:\Users\mdham\Downloads\paperplane-history-purge-v20.git`; no remote or repository history was rewritten.
- **Additional browser-discovered issues:** Delayed auth restoration no longer flashes guest controls on Settings; Studio signature/security actions open dialogs without leaving Studio; early paid upload waits for account restoration before applying limits. Evidence is in the browser smoke/regression logs.

## Verification

- Full pytest suite after final source changes: **477 passed twice**, one existing Starlette/httpx deprecation warning. Logs: [run 1](pytest-final-run1.log), [run 2](pytest-final-run2.log).
- Final local Chromium full smoke: [browser-full-smoke.log](browser-full-smoke.log). Includes content-checked 60 MiB + 10-page chunked merge, translation/summary outputs, Studio persistence/reorder, payment gating, feedback display, and upload progress/cancel.
- Final targeted Chromium regressions: [browser-regressions.log](browser-regressions.log). Includes split, flatten, Word, annotations, billing disclosure, sparse chat, Excel columns, and two image-heavy runs each for compression, watermark, and page numbers.
- Python syntax checks and `git -c core.whitespace=cr-at-eol diff --check` passed.
- Reviewed the project’s saved UI screenshots as visual context; the fresh local Chromium runs above are the current interaction/download evidence.
- Earlier 44-operation content audit recorded **39 completed, 1 failed, 1 expected SSRF block, and 3 unavailable**. PDF/A failed in the local runtime because Ghostscript/sRGB profile support was unavailable; OCR and provider-dependent summarize/translate were unavailable in that audit. A Dockerfile ICC-profile provisioning change was added, but Docker Desktop is unavailable here, so the container build and PDF/A conversion still need runtime verification.
- These local results use synthetic/public inputs and controlled providers. They do not prove production-provider, production proxy/database, mail-delivery, deployed-volume, or live-payment behavior.

## Required remaining work

### Owner-only actions

- **OWNER STEP — credentials:** Rotate the compromised admin credentials, review unknown login attempts, and publish/purge the rewritten history and cached views. The isolated purge preparation is not a public history rewrite.
- **OWNER STEP — payment:** Verify production Cashfree credentials and perform the checklist’s small real-payment/entitlement check. No real payment was attempted.

### Deployment-environment checks

- After deployment, verify ID 93 persistence across container replacement and ID 102 feedback write/read through the production database topology.
- Verify ID 296 against production proxy peer logs.
- Supply the intended Drive PDF for ID 4 and the original large/image-heavy owner fixtures for IDs 207 and 295, then repeat their exact checks.
- Verify IDs 1 and 2 with the production AI provider and its real rate-limit/quota behavior.
- Build the Docker image and run PDF/A with the configured Ghostscript ICC profile; the local host did not have Ghostscript or a Docker daemon, and a local Ghostscript install could not proceed without administrator rights.

### Checklist scope still open

Many P1/P2 items in the 298-item list have not been implemented or independently re-run in this round. The 77 prior `verified_fixed`, 12 `to_verify`, and 2 `not_tested` rows were not all revalidated. This report is not release approval; do not publish from it as a READY verdict.

## Modern Web Guidance

- Used native `<progress>` semantics with a programmatic accessible label and polite upload/processing announcements.
- Kept progress updates from moving focus; reduced-motion styling is respected for auth restoration skeletons.
