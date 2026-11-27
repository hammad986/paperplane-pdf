## v22 continuation — 2026-11-16

### Current result

**NOT READY for deployment.** The working copy has concrete v22 fixes and passes the local regression suite twice, but the 309-item elite list is not closed. Several P0 acceptance checks still fail or lack the required live/provider/production-image evidence. This report does not claim the requested 100% result.

No commit, push, deployment, real payment, production credential rotation, or action against either prohibited mirror was performed. The checked-out branch is `main` at `172afcc`; the prompt requested `launch-audit-v21`, which does not exist locally. No branch was created.

### v22 implementation completed in this pass

| Item / issue | Change | Verification |
|---|---|---|
| ID 1 translation diagnostics and fallback reporting | Provider connection checks now try the configured fallback and report when it handled the request. Translation failures preserve safe upstream status classes, including HTTP 429, without exposing provider response bodies or credentials. | `tests/test_ai_workflows.py`; full suite twice. Live four-job Spanish/Hindi reproduction still failed on the deployed provider, so ID 1 remains open pending provider correction and two clean runs per language. |
| ID 241 page-number template | The literal UI format `Page {n} of {total}` now substitutes both tokens rather than dropping `{total}`. | Six-page content test verifies page 1 and page 6; browser output content check from the existing local tool catalog. |
| ID 283 destructive compression | Image streams with alpha, palette transparency, or CMYK are preserved. Compressed output is rendered and screened for a large newly black region; if detected, the readable source is returned with a preservation warning. The intended Under-100-KB default was not changed. | Both Under-100-KB and Balanced run against a generated five-page, 16.1 MB mixed-page image PDF. All rendered output pages retained dimensions and visual luminance; the result is recorded in `reports/launch-audit-v22/compression-render-check.json`. Existing regression tests also check image color and searchable text. This local controlled sample does not close all image-heavy production inputs. |
| ID 299 payment data disclosure | `/api/billing/status` no longer returns `cashfree_order_id`, including for an account with an order ID. | New endpoint regression test verifies the private order ID is absent from both JSON fields and response text. |
| ID 309 raw-pixel Scan-to-PDF dimensions | Scan-to-PDF now offers A4, US Letter, and original printed size at 200 DPI. Images are centered and fitted without stretching; pixel dimensions are not interpreted as PDF points. | Chromium uploaded an image, ran each selection, downloaded the PDF, and checked its page dimensions and image contents. Results: `reports/launch-audit-v22/browser-scan-pages.json`. |
| ID 173 misleading workflow copy | Rotate, JPG-to-PDF, PDF-to-Text, PDF-to-Markdown, Compare, Scan-to-PDF descriptions now match the available controls and actual output. Scan instructions describe the new page-size selector. | Full suite and 176-route local Chromium layout pass. |
| ID 246 server version disclosure | `server_tokens off` was added to both nginx configuration templates. The production template already includes a CSP. | Source inspection only for nginx; this PC has no running Docker engine/nginx, so the built production image and live response headers still need verification. |
| Browser cache | App JavaScript and stylesheet query versions were bumped to `v22` after the local UI/CSS changes. | Local Chromium loaded and exercised the changed Scan-to-PDF page. |

### Verification evidence

- Full pytest suite: **488 passed, 1 existing Starlette/httpx deprecation warning** on each of two sequential runs. Logs: [run 1](</C:/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v22/pytest-v22-run1.log>) and [run 2](</C:/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v22/pytest-v22-run2.log>).
- Local Chrome responsive route matrix: **176/176 route-and-viewport loads passed** across 44 tool routes at 390, 820, 1366, and 1920 CSS pixels, with no route failures or measured horizontal overflow. Evidence: [route-layout-matrix.json](</C:/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v22/route-layout-matrix.json>).
- Local Chrome Scan-to-PDF: A4, Letter, and original-at-200-DPI options all produced downloaded, readable one-page PDFs with the expected physical dimensions. See [browser evidence](</C:/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v22/browser-scan-pages.json>) and screenshots in the v22 evidence folder.
- Local Chrome catalog run: 44 operations attempted; 39 completed, OCR/summarize/translate unavailable in this Windows test environment, one HTML conversion was correctly blocked by the SSRF guard, and PDF/A failed because this host lacks Ghostscript. Evidence: [browser-catalog.json](</C:/Users/mdham/Downloads/pdf_splitter/pdf_splitter/reports/launch-audit-v21/browser-catalog.json>).
- Whitespace/diff check: `git -c core.whitespace=cr-at-eol diff --check` passed. Git emitted only its existing LF/CRLF normalization notice for `tests/test_text_layer_v18.py`.

### P0 status at end of this pass

| ID | Status | Remaining proof or action |
|---|---|---|
| 1 | **NOT FIXED live** | Deployed Spanish and Hindi each failed twice with a generic no-output result. The local code now exposes safe upstream status and tests configured fallback behavior, but the live provider still needs a working quota/key and two consecutive successful content-checked outputs in both languages. |
| 2 | **PARTIAL** | The local offline brief regression now retains the later pages and citations, including page 69, and the 24-page diagnostic passed locally. A live provider-backed 69-page output with the required facts/citations is still unverified. |
| 4 | **PARTIAL** | Direct public PDF Cloud Import passed twice. The exact owner Drive link was not used because prior evidence identifies it as an image response rather than the intended PDF. A correct owner-shared PDF link is still required for that discriminating test. |
| 93 | **LOCAL CONTROLLED TEST PASSED; DEPLOY RETEST OPEN** | Temporary-database process restart and volume checks pass. The formal create-account → platform redeploy → login flow has not been run because it changes/deploys production state. |
| 98 | **CODE GATES PASS; OWNER STEP OPEN** | Production/test environment gates and sandbox tests pass. The real production key configuration and real payment check are owner-only and were not performed. |
| 101 | **CODE-SIDE PREPARATION PRESENT; OWNER STEPS OPEN** | Required admin environment settings, Gitleaks CI, and `scripts/prepare_admin_history_purge.py` exist. The purge script was not executed because it rewrites history; rotate credentials first, then review and execute the prepared purge/force-push from the release owner workflow. |
| 102 | **LOCAL CONTROLLED TEST PASSED; LIVE ADMIN DELIVERY OPEN** | Feedback survives a process restart and appears in the open synthetic admin browser. Delivery into the production admin account remains for the owner/Muse post-deploy retest. |

Owner-only steps remain production credential rotation (ID 101) and the real production payment check (ID 98). The other listed gaps are not owner-only exemptions: they need code/provider fixes or post-deployment acceptance runs before a READY verdict.

### Remaining release blockers

1. The v22 instruction requires per-ID disposition and evidence for all 309 elite-list items. This pass did not complete that matrix; the v21 report still records the broader list as open.
2. Live Translate failed four times during the preceding reproduction. The code diagnostics/fallback changes do not prove the production provider is healthy.
3. Live OCR was accepted with HTTP 202 but did not reach an observed terminal state in the five-minute poll; local OCR does not prove production worker completion.
4. PDF/A was not verified inside the actual production image with a validator. Docker Desktop's Linux engine is unavailable on this PC, and Windows lacks Ghostscript. A WSL-only pass is not production-image proof.
5. The exact Drive-import PDF, live feedback delivery, and formal deployment persistence test remain unverified.
6. The 44-operation browser catalog did not pass every operation: OCR and provider-backed AI operations were unavailable locally, PDF/A failed locally, and only 39 outputs completed. Production tool workflows still need their content-checked post-deploy run.
7. No deployment-readiness self-analysis across every open checklist row was completed; therefore the required loop cannot be reported as complete.

### Files changed in this working copy

- `ai_engine.py` — translation provider fallback/status handling; long-document offline brief path.
- `converters.py` — mixed-page Word support from v21; image-safe compression guard; selected physical page sizes for Scan-to-PDF.
- `server.py` — safe AI connection result; page-number token substitution; payment order ID removal; Scan-to-PDF options and accurate workflow copy.
- `persistence.py` — per-job warning migration and persistence for content-preserving compression fallback.
- `web/assets/app.js` — selected-tool privacy copy and Scan-to-PDF page-size control.
- `web/assets/styles.css` — responsive Settings, Studio/dialog and mobile toast/layout rules from v21.
- `web/index.html` — refreshed app/style asset keys.
- `deploy/nginx.conf.template`, `deploy/nginx-http.conf.template` — hide nginx version tokens.
- `tests/test_ai_workflows.py`, `tests/test_launch_audit_v22.py`, `tests/test_launch_audit_v13.py`, `tests/test_launch_audit_v21.py`, `tests/test_launch_audit_v3_hardening.py`, `tests/test_text_layer_v18.py` — regression coverage and test-startup bound.
- `scripts/browser_v21_catalog.py`, `scripts/browser_v21_layout.py`, `scripts/browser_v21_routes.py`, `scripts/browser_v22_routes.py`, `scripts/browser_v22_scan_pages.py` — local browser acceptance workflows.
- `reports/v21-extracted.txt`, `reports/v22-extracted.txt`, `reports/launch-audit-v21/`, `reports/launch-audit-v22/` — source extraction, reproduction logs, test logs, browser outputs, and audit evidence.

### Modern Web Guidance

- **forms**: The page-size control uses a visible, associated label and a native select, and its choices are tested through the browser. The guide says, “Always associate `<label>` with its input using `for` and `id`.”
- **form-factor-adaptation**: The new control stays within the responsive tool form and its route was checked at 390, 820, 1366, and 1920 px. The guide says to ensure “text and controls are never clipped ... down to 320 CSS pixels.”


