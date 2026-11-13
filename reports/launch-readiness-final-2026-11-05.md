# Paperplane launch-readiness report — 2026-11-05

## Decision

**Local implementation: the final automated suite and the scripted preflight passed. Production release: NOT SIGNED OFF and NOT DEPLOYED.** The local checkout is still uncommitted. Docker Compose configuration is valid, but Docker Desktop's Linux engine is unavailable, so the current source was not rebuilt into a container. No live deployment, payment, OAuth, cloud-provider operation, or physical-device test was performed.

This report separates route/layout coverage from full tool workflows. Loading every tool page successfully does not mean every upload-to-download journey has been manually verified.

## Final verification

| Check | Result |
| --- | --- |
| `python -m pytest -q` after the final source change | **233 passed, 1 warning, 140.75 seconds** |
| `python scripts/preflight_test.py` | **37/37 passed**; local fixture avoids external email dispatch |
| `python scripts/deploy_production.py --dry-run` | **Passed; config and planned steps only** |
| `docker compose -f docker-compose.yml config --quiet` | **Passed** |
| Python compilation | **Passed** for changed Python modules and affected test modules |
| `node --check` | **Passed** for `app.js`, `editor.js`, and `page_organizer.js` |
| `git diff --check` | **Passed**; Git emitted only Windows LF/CRLF notices |
| Local route/viewport matrix | **440/440** Chromium page loads: 44 routes × 10 widths, with no HTTP failures, uncaught page errors, missing H1s, horizontal overflow, or clipped top-bar controls |
| Responsive theme/layout matrix | **81/81** tested view/group/theme combinations had no measured overflow, overlap, or clipped labels |
| Mobile Studio touch targets | **0 undersized critical targets** at 360, 375, 390, 414, and 768 px; page checkboxes measured at least 44 px |
| Docker image build / container run | **NOT TESTED**; Docker CLI exists, Docker Linux engine does not respond |
| Current production site after these changes | **NOT RECHECKED** |

The single test warning is Starlette's deprecation notice for its current `httpx` integration. The test suite is green; the warning remains to be addressed in dependency maintenance.

### Issues found and fixed during this pass

- The thumbnail upload route referenced `user_id` without declaring the auth dependency, so its handler returned HTTP 422. The route now resolves the optional current user, and its regression test passes.
- The quota display was hidden for the entire auth lookup. It now shows “Checking usage…” during delayed responses, then the static Free fallback after an API failure; it remains visible with JavaScript disabled.
- Changed CSS/JS files still had their previous query-string versions. The HTML now uses fresh cache-busting versions for the stylesheet, app controller, editor, and organizer.
- AI tests still expected provider/model identifiers and an older failure string. Their assertions now match the privacy-safe response and normalized public error contract. The SEO FAQ test now permits the additional grayscale file-size FAQ.
- The earlier preflight script expected an auth token in JSON and triggered a notification attempt. It now uses a local fixture, performs no email dispatch, and avoids unqualified production-certification language.
- The first full test run surfaced these contract mismatches and the thumbnail bug. After fixes, the final complete run passed all 233 tests.

## Requested checks C1–C10

| ID | Status | Result and boundary |
| --- | --- | --- |
| C1 | **FIXED** | Real 69-page local PDF tested at 1366 px and 375 px. Continuous page scrolling, page 2/3/69 visibility, thumbnail jump, previous/next, and number-field jumps kept the counter and selected thumbnail synchronized. The outer page did not scroll. |
| C2 | **PARTIAL** | Executive Brief is visibly disabled with an explanation when AI is not configured. Real summaries from two documents could not be exercised because this workspace has no AI provider configured. |
| C3 | **FIXED** | Home and the requested tool entry points routed to `/tool-desk`, with the requested tool selected. All tool routes also passed the route/layout matrix. |
| C4 | **FIXED — local sample only** | A local 69-page PDF rendered its first page in 0.02 s; a 69-page grayscale output rendered in 0.75 s. Page count and first-page render were still present at 0, 10, 30, and 60 s. This is not a network or production benchmark and did not use the owner's 5.20 MB source file. |
| C5 | **FIXED** | Studio duplicate 69→70, delete one 70→69, delete two 69→67, prevent deleting the last pages, insert blank 67→68, and count consistency passed. A clean extraction produced pages 1 and 3 with matching source text. Delete confirmations explicitly say deletion cannot be undone; Studio does not currently provide Undo for these page deletions. |
| C6 | **FIXED** | In-memory work survived in-app navigation. Reload selected Studio again but cleared the file and showed a notice explaining that the user must choose the source again. This is intentional privacy behavior; file persistence across reload is not provided. |
| C7 | **PARTIAL** | Cloud modal closed on navigation. A non-PDF cloud response was rejected with a clear PDF-only message. Real Google Drive/Dropbox authorization and import were unavailable and were not tested. |
| C8 | **PARTIAL** | The PDF picker accepted a real local file in desktop and 375 px browser contexts. A grounded answer was not verified because the AI provider was unavailable; the error surfaced without a page exception. |
| C9 | **FIXED** | Studio toolbar extracted the current page and selected pages 1 and 3. Both downloads had valid PDF signatures, expected page counts, and matching page text. |
| C10 | **PARTIAL** | Chromium layout passed the 44-route × 10-width local matrix, including phone, tablet, laptop, and desktop widths. Internal Studio zoom values were exercised. Actual browser zoom at 80/125/150%, Firefox/WebKit on the final source, and physical iOS/Android/tablet/laptop devices remain untested. |

### Responsive widths and artifacts

The route matrix covered 320, 360, 375, 390, 414, 768, 1024, 1280, 1366, and 1920 px. Separate light/dark checks covered All Tools, AI, Studio, and selected Merge/OCR/Split pages. The final mobile Studio touch audit covered 360–768 px and checked all 69 visible page checkboxes. The ribbons remain horizontally scrollable on phones so controls are reachable without widening the page.

Evidence is in `responsive-matrix-final-summary.json`, `responsive-verified-36-matrix.json`, `responsive-touch-target-retest.json`, and the corresponding files in `reports/screenshots/`.

## Requested checks R1–R8

| ID | Status | Result and boundary |
| --- | --- | --- |
| R1 | **PARTIAL** | The current checkout is INR-only: checkout sends INR, rejects USD with HTTP 400, plan JSON/schema use INR, and the mocked Cashfree checkout test verifies the Pro amount. Concrete Team/Enterprise plan prices or limits are absent, and no real Cashfree sandbox payment was made. |
| R2 | **FIXED** | API documentation is gated by configuration/environment, and `/docs` redirects to `/developers`. The production-security tests cover the behavior. |
| R3 | **FIXED** | Public AI chat and connectivity responses omit provider/model identifiers. Updated regression checks assert those fields are absent. |
| R4 | **PARTIAL** | Timeout and retry handling is bounded and unit-tested, but no live AI provider was available to verify real latency or upstream behavior. The exact policy is below. |
| R5 | **PARTIAL** | Server merge timeout is 120 s and Nginx proxy read/send timeouts are 900 s. A local 69+69-page merge completed in 0.083 s and produced a valid 138-page PDF. Maximum-duration/proxy-gateway behavior was not load-tested. |
| R6 | **FIXED** | No-JS shows `0 / 100`; while `/api/auth/me` is delayed the quota remains visible as “Checking usage…”; after a simulated 503 it resolves to `0 / 100`. Plan hints resolve to Free 50 MB, paid 500 MB, and 100-file batches. |
| R7 | **FIXED** | Free upload of 50 MiB + 1 byte returned HTTP 413 and left usage at 0. A local authenticated Pro upload of exactly 500 MiB returned HTTP 202; the server received exactly 524,288,000 bytes and PyMuPDF read the uploaded one-page PDF. The Pro test account and job files were removed. This verified upload acceptance, not completion of that large merge job. |
| R8 | **PARTIAL** | Source CSP has no `unsafe-inline` scripts. It retains `style-src 'unsafe-inline'` for current inline styles/runtime style updates and `wasm-unsafe-eval` for PDF.js WASM. PDF.js rendering passed locally under the policy. Real Google Sign-In and Cashfree checkout CSP flows were not exercised. |

### Pricing and currency currently in code

| Plan | Configured amount | Period | Currency |
| --- | ---: | --- | --- |
| Free | ₹0 | Free | INR |
| Exam Pass | ₹19 | 24 hours | INR |
| Student Pro | ₹49 | Monthly | INR |
| Student Pro Annual | ₹399 | Annual | INR |
| Pro | ₹250 | Monthly | INR |
| Cyber Café | ₹299 | Monthly | INR |
| Developer | ₹750 | Monthly | INR |

No Team or priced Enterprise tier is configured. The repository has no active USD checkout path; invoice extraction may recognize USD in uploaded document content, which is separate from subscription currency. The previously discussed `$12` / `$5.99` values are not configured checkout prices. “Enterprise” appears in product wording, but no corresponding limits/price table exists in the current plan model.

### AI timeout policy

| Flow | Timeout | Retry behavior |
| --- | --- | --- |
| Provider sync request | Config default 60 s, clamped 5–120 s | Up to 2 attempts for transient network/HTTP failures; no aggregate 120 s cap across both attempts |
| General direct chat | 35 s | Uses the synchronous provider retry policy |
| PDF chat and summary | 50 s | Uses the synchronous provider retry policy |
| Streaming chat | 50 s default, clamped to 5–60 s | Up to 2 attempts before first content; no restart after content begins |
| Provider connection diagnostic | 12 s per probe | Up to 2 probes |
| Translation call | 6 s | Provider not configured during this audit; live behavior not tested |

The UI clears stale failure content before retrying. A local provider outage/configuration state showed a clear message, but provider timing and retry behavior is evidenced by mocked/unit tests rather than a live service.

## 41-tool workflow ledger

All **41 implemented tool routes** rendered in the local route/layout matrix. The content column below records direct sample-output or workflow smoke, not just route loading. “Not run” means this audit did not execute a complete browser upload/options/download flow for that tool; the 233-test suite may still cover internal functions or APIs.

| Tool | Content/output smoke |
| --- | --- |
| Merge PDF | **PASS** — local 69+69-page merge, 138-page valid PDF; 500 MiB Pro upload accepted |
| Split / extract | **PASS** — range split in preflight; Studio extraction verified 1 page and pages 1/3 with source text |
| Remove pages | **PARTIAL** — Studio page deletion/counts tested; standalone tool output/download not tested |
| Rotate PDF | **PASS** — preflight output page rotation verified at 90° |
| Page Organizer | **PARTIAL** — thumbnail endpoint and Studio duplicate/delete/blank/extract UI tested; complete standalone output flow not tested |
| Scan to PDF | **NOT TESTED** — standalone scan workflow/output |
| Compress PDF | **PASS** — preflight sample reduced 8,033 B to 4,942 B; visual quality review not performed |
| Repair PDF | **PASS** — preflight recovered a two-page sample |
| OCR PDF | **NOT TESTED** — OCR language packs are installed, but a tool output/recognized-text sample was not run in this final audit |
| JPG/PNG to PDF | **PASS** — image-to-PDF preflight output produced |
| Word to PDF | **PASS** — DOCX converted through LibreOffice in preflight |
| Excel to PDF | **NOT TESTED** — output flow |
| PowerPoint to PDF | **NOT TESTED** — output flow |
| HTML to PDF | **NOT TESTED** — output flow |
| PDF to JPG | **PASS** — ZIP bundle produced in preflight |
| PDF to Word | **NOT TESTED** — output flow |
| PDF to Excel | **NOT TESTED** — output flow |
| PDF to PowerPoint | **NOT TESTED** — output flow |
| PDF to PDF/A | **NOT TESTED** — output validation |
| PDF to Text | **PASS** — Unicode text extraction in preflight |
| PDF to Markdown | **NOT TESTED** — PDF input to Markdown output; Markdown-to-PDF is a different flow |
| Edit PDF | **NOT TESTED** — exported edit result |
| Annotate PDF | **NOT TESTED** — exported annotation result |
| Crop PDF | **NOT TESTED** — output bounds |
| Redact PDF | **PASS** — preflight verified target text was removed from the output stream |
| Watermark PDF | **PASS** — preflight applied a watermark |
| Page Numbers | **NOT TESTED** — output numbering |
| Protect PDF | **PASS** — preflight verified AES-256 encryption |
| Unlock PDF | **PASS** — preflight verified password removal |
| Sign PDF | **PASS** — preflight verified a detached signature |
| Compare PDF | **NOT TESTED** — report/output flow |
| Fill PDF Form | **NOT TESTED** — Name/Email/City fields were not filled and re-read in a browser flow |
| PDF Metadata | **NOT TESTED** — edit/readback output |
| AI PDF Chat | **PARTIAL** — picker and provider-error handling tested; real grounded answer unavailable |
| Smart Metadata | **NOT TESTED** — real provider extraction unavailable |
| AI Summarize | **PARTIAL** — disabled honestly with no provider; no real brief generated |
| AI Translate | **NOT TESTED** — real provider/translation output unavailable |
| Exam Photo & Signature Resizer | **NOT TESTED** — image output dimensions not verified |
| Mask Aadhaar Card | **NOT TESTED** — sensitive-region output not verified |
| Convert to Grayscale | **PASS** — 69-page valid output and grayscale integrity regression coverage passed; output size can increase because colored pages are rasterized |
| Flatten PDF Forms | **NOT TESTED** — flattened output/readback |

The preflight directly exercised conversions, security actions, and several Studio outputs; the automated suite adds unit/API coverage. Neither replaces the not-run browser flows above.

## Security, privacy, and integration notes

- The preflight uses a local database-backed session fixture for its authenticated API-key smoke. It no longer signs up a synthetic account or sends notification mail.
- An earlier preflight attempt called registration and triggered a login-notification email attempt to a fabricated test address. Resend rejected it with HTTP 403; **no email was delivered**. That test account was removed. No further outbound email was attempted.
- Local AI capability reports “not configured”; Executive Brief stays disabled, and the chat picker surfaces the provider error.
- Cloud modal dismissal and PDF-only rejection were tested. Real Google Drive/Dropbox credentials and OAuth were not used.
- Cashfree tests stubbed the provider. No real or sandbox payment was created.
- Guest Free upload/quota behavior was tested at the 50 MiB boundary. Signup OTP was covered by automated tests, not by a real email delivery.
- Page-deletion confirmations state that deletion cannot be undone. Keep the source file if the user needs an undo path.
- The sample grayscale input used here was a local 31,568-byte synthetic PDF, not the owner's 5.20 MB file. The local grayscale output was 6,937,511 bytes; this confirms that this conversion path can grow file size. The supplied live-file size delta still needs to be reproduced with that exact file before attributing its cause.
- A previous read-only report dated 2026-11-03 recorded old asset versions and a CSP mismatch on the production domain. That is historical evidence only; current production assets/CSP were not rechecked after these changes.

## Release blockers / next owner actions

1. Start Docker Desktop's Linux engine, then run the actual current-source image build and container smoke. The current dry-run did not build or start containers.
2. Configure the production AI provider, then test grounded chat, two-document summaries, structured extraction, and translation with approved sample documents.
3. Verify Google/Drive/Dropbox and Cashfree **TEST** credentials and callbacks in a non-production environment; do not use live payment credentials for this check.
4. Complete browser upload-to-output smoke for the tools marked **NOT TESTED** above, plus physical phone/tablet and actual browser-zoom checks.
5. Confirm the intended Team/Enterprise plans, limits, and prices or remove ambiguous pricing/plan wording.
6. Deploy through the owner's release process, then verify deployed bundle query versions, CSP, health, uploads, editor, and payment/AI flows against the actual live release.

**Deployment status: NOT DEPLOYED. No production write or release was performed.**

## Evidence files

- `responsive-matrix-final-summary.json` — route/viewport summary.
- `responsive-verified-36-matrix.json` and `responsive-touch-target-retest.json` — theme/layout/touch details.
- `c1-grayscale-live-like-final.json`, `c1-prevnext-final.json`, `c4-render-audit-final-v2.json` — Studio scroll and render timings.
- `c5-batch-regression-rerun.json`, `c9-extract-regression.json`, `c6-reload-notice-final.json` — editing, extraction, and reload behavior.
- `c3-c2-c7-c8-local-final.json` — Tool Desk, AI, and Cloud behaviors.
- `r6-delay-and-cache-version-final.json`, `r7-free-50mb-plus-one.json`, `r7-pro-500mb-local.json` — quota fallback and upload boundaries.
- `merge-69x2-timeout-final.json` — local merge timing and output.
- `deployment_last_run.json` / `deployment_dry_run.log` — dry-run only; no deployed state.
- `screenshots/` — route, viewport, Studio, upload, and interaction captures.
