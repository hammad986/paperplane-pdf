# Paperplane v14 audit status

## Verdict

**HOLD.** The code and local regression coverage improved, and the critical local flows listed below passed repeated checks. This work does **not** establish that all 226 audit items are fixed or that the application is deployment ready. Many P1/P2 items still lack item-specific fixes or verification, and several checks require the deployed service or the exact owner-provided inputs.

## Scope and constraints followed

- Work was performed in the Paperplane source worktree based on `e4a2bd3`. Changes remain uncommitted.
- The `paperplane-redacted-v14.git` mirror was not touched. The reviewed mirror was left unchanged during this round; it does not contain the current uncommitted changes and is not ready to publish.
- No deployment, push, production account change, real payment, or credential rotation was performed.

## Local implementation and verification

- **Translation and summary:** translation now batches all extracted text blocks, splits long blocks, retries empty/malformed provider responses, and removes translated source text from the searchable layer. Synthetic Chromium runs translated 3- and 69-page PDFs to Spanish and Hindi; a 69-page summary also rendered. These are controlled-provider checks, not translation-quality evidence from the live provider.
- **False premises and citations:** the browser corrected both the false 100-page claim and unsupported authorship claim for a synthetic 69-page PDF. Three repeated page-specific chat runs produced one supported Page 2 chip and removed duplicate, template, and out-of-range citations.
- **Studio:** synthetic 69-page deletions from 69 to 68 to 67 survived reload; failed-save recovery did not restore stale work. Two broader Chromium rounds also covered reorder, duplicate, extract/download, resize, clear, and reload.
- **Large upload and local tools:** Chromium merged a synthetic 60 MiB, 759-page PDF with another 10-page PDF to 769 pages in server mode, checked end-page text, and verified cancellation of a stalled upload. Local merge and 69-page Remove Pages were tested in Chromium; Remove Pages returned the expected 67 pages and `removed-pages.pdf`.
- **Other browser checks:** the W3C PDF form import, feedback-to-admin refresh, 390px Log In entry, Server Mode, photo dimensions/size and default target, repair behavior, developer-key tier gating, pricing labels, and production-mode sandbox-payment rejection passed in the recorded rounds.
- **Additional bug found and fixed:** rendering AI tool pages called `/api/ai/capabilities`, and those inexpensive GET requests consumed the 12-per-minute provider-call budget. Navigation could exhaust the budget before a user submitted a document. The limiter now counts billable AI POSTs and the provider connection POST. Regression tests cover repeated capability reads and retained POST throttling; the browser flows passed after the fix.
- **44-operation content audit:** two runs completed and checked outputs for 40 operations each; three operations were unavailable because their providers/tools were absent; the deliberately private HTML-to-PDF URL was blocked. No output-content assertion failed.
- **Secret hardening:** the Compose admin-code fallback is fail-closed, and the existing Gitleaks CI workflow plus rules for code and Compose fallbacks remain in place. A history-redaction preparation script exists. Gitleaks and Docker were unavailable locally, so the CI scan was not run. Do not publish the existing reviewed mirror: it excludes these uncommitted changes.

Final full-suite runs after the product-code changes:

- Run 1: **449 passed**, 1 existing Starlette/httpx deprecation warning, 89.12 seconds.
- Run 2: **449 passed**, 1 existing Starlette/httpx deprecation warning, 87.10 seconds.

The expanded browser acceptance suite passed twice with zero page errors. The selected v14 browser flow, including three repeated chat-citation checks and the exact 69-page Remove Pages case, passed in rounds 28 and 29. `git -c core.whitespace=cr-at-eol diff --check` passed.

## Remaining release blockers and verification

- The full 226-item register has not been closed. Local/browser evidence in this report covers only a subset; unresolved P1/P2 items remain. In particular, this work did not repeat the requested regression verification for every do-not-regress item or run every tool through its browser UI twice.
- ID 4 was tested with the public W3C form document, not the owner's Drive link. The Drive-specific check remains: import that exact link through the browser form and verify page count, content, and completion without a modal error.
- IDs 1/2 used controlled provider responses. After deployment, run Spanish and Hindi translation and the 69-page brief against the configured provider; verify output text layers, citations, full page coverage, and retry/timeout behavior.
- ID 98 locally confirmed that production mode rejects sandbox checkout and payment simulation. After deployment, the owner must perform the real payment check and verify the paid entitlement through the signed webhook/order verification flow.
- ID 101 code-side fallback removal and history-purge preparation are present. After review, the owner must rotate the compromised admin credential and coordinate the history rewrite. Do not publish the current reviewed mirror until it contains the reviewed working-tree changes and a fresh secret scan passes.
- ID 102 appeared in the admin browser after local feedback submission. After deployment, confirm the production database volume is persistent and that a submitted feedback item appears in the admin list after an application restart.
- ID 206's browser-side merge passed locally. After deployment, load the deployed page with a clean browser cache and verify the PDF runtime asset exposes `transformLocalPdf`, then merge and split without an `/api/jobs` request in local mode.
- ID 207 passed with a synthetic 60 MiB attachment fixture. The owner's exact 60 MiB input and production worker/proxy path remain unverified; repeat that exact upload after deployment and inspect completion, output page count, and logs.
- The daily synthetic Cashfree sandbox checkout probe (ID 228) is not implemented as a scheduled, owner-alerting check. The existing one-off smoke script does not verify the checkout drop UI or alert on daily failure.

## Owner steps

1. Rotate the compromised production admin credential; never reuse the exposed value.
2. Perform the real production payment check and confirm entitlement activation and persistence.

All other post-deployment checks above are retests of the local code against live configuration and owner inputs, not completed evidence.
