# Paperplane — Launch Audit v10 — FINAL REPORT

Build: HEAD `1596e5d135637cf36183255970e3a9a11a8614d3` (local branch `launch-audit-v10`) | Date: 2026-11-12 | Verdict: **HOLD**

## Summary

The local codebase received the requested fixes and regression work, and the full test suite passed twice consecutively. The final evidence includes local browser acceptance, two 41-tool content-audit rounds, two 41-route SEO-heading rounds, dependency audit, static Compose validation, and local security-code checks. The release is still **HOLD** because several acceptance gates require the owner's production database, actual mail/provider configuration, exact owner PDFs, and Cashfree production setup. No real payment, production request, owner credential, commit, push, or deployment was used.

Provisional local code-security grade: **7/10**. This is a common-risk code/configuration review, not a penetration test or a guarantee of security. Production TLS, headers, container mounts, and cross-process persistence were not reachable for verification.

## Test and verification record

- Full suite run 1: **381 passed, 0 failed**, one non-blocking Starlette `TestClient` deprecation warning; pytest time 74.14 s, runner wall time 79.02 s. Log: [test-suite-run-1.log](outputs/test-suite-run-1.log).
- Full suite run 2, immediately after run 1: **381 passed, 0 failed**, one non-blocking Starlette `TestClient` deprecation warning; pytest time 75.13 s, runner wall time 79.46 s. Log: [test-suite-run-2.log](outputs/test-suite-run-2.log).
- Structured run record: [test-suite-summary.json](outputs/test-suite-summary.json).
- Browser acceptance: [browser-acceptance.json](outputs/browser-acceptance.json). No page errors. The home shell transferred 848,462 bytes; the PDF engines were absent from initial resources. That is 843,887 fewer bytes (about 49.9%) than the pre-fix 1,692,349-byte run. PDF.js loaded when Studio opened, PDF-Lib remained deferred through Studio and loaded only when requested. The measured desktop navigation was 266 ms to DOMContentLoaded and 281 ms to `load` in the final run.
- Studio acceptance used the repository's 4,980,286-byte, 69-page notes substitute, not the owner's 5.20 MB document. Both reorder directions returned HTTP 200; the 69-, 68-, and 67-page exports matched expected page order and full page text after reload. The 68- and 67-page browser reloads were verified on an empty local database. Export outputs and retention diagnostics are under [outputs](outputs/).
- The Studio toolbar measured 80 px high, two rows, 35 visible controls, 10 px minimum font, and zero off-screen controls at 1920 px. At 390 px the organizer drawer and toolbar had zero overlap, with 28 controls reachable and none outside the viewport.
- Feedback remained visible with no first-card or bottom-navigation overlap at 390 × 667/740/781/844/932; it did not overlap Studio zoom, hid during a dialog, hid after a confirmed synthetic submission, and reopened from Settings. The full matrix with real browser chrome and both themes was not run.
- The local content audit ran two sequential rounds of all 41 catalog tools: each round had 37 completed outputs, 3 unavailable items (OCR, Summarize, Translate), and one expected HTML-to-PDF SSRF-guard block. The opened outputs and limits are in [TOOL-CONTENT-AUDIT.md](TOOL-CONTENT-AUDIT.md) and [tool-content-audit.json](outputs/tool-content-audit.json).
- SEO headings matched all 41 routes in both recorded rounds: [seo-heading-audit.json](outputs/seo-heading-audit.json).
- `pip-audit` checked 58 requirements and found no known vulnerabilities. The local secret-pattern scanner reported 18 generic-assignment matches, all reviewed as test/fixture patterns or a client-side placeholder; no high-confidence provider-key format or private-key block was found. A Git-history secret scan was not available. No secret values are included in audit output.
- `docker compose --env-file .env.example config -q`, changed JavaScript/Python syntax checks, and `git diff --check` passed. Docker Desktop was unavailable for a running-container, mount, backup-restore, or Nginx-response check.

## Per-item status

- ID 1 — AI Translate: **PARTIAL** — provider health/configuration diagnostics and safe unavailable behavior are implemented; no provider key was available, so no Spanish/Hindi translated output was produced.
- ID 2 — Brief/Summarize: **PARTIAL** — safe missing-provider behavior is covered; neither provider-backed small-file output nor the exact owner 69-page brief/summary is verified.
- ID 3 — Studio retention: **PARTIAL** — local 69→68→67 delete/reload/export sequence passed against the 4.98 MB repository substitute; exact owner PDF acceptance remains open.
- ID 4 — Cloud Import: **PARTIAL** — the supplied link is the only link and resolves to a one-page file in the prior local check; the 69-page import remains partial as requested, and the latest DNS attempt failed before fetch.
- ID 5 — AI citation quality: **PARTIAL** — local citation normalization/rendering tests pass; provider-grounded citations over repeated owner-document runs were not possible.
- ID 6 — False-premise handling: **PARTIAL** — local fallback behavior is tested; provider-backed evaluation on the owner document is not.
- ID 7 — Tracker item: **NOT TESTED** — title and acceptance criteria were not included in the supplied tracker detail.
- ID 8 — Remove Pages reliability: **PARTIAL** — two local content-audit rounds opened valid 68-page outputs; exact live first-attempt 502/stall acceptance is not proven.
- ID 9 — Smart Metadata date/fields: **PARTIAL** — local metadata export opens in both rounds; provider-backed 69-page accuracy and exact owner semantics remain unverified.
- ID 10 — AI extraction: **PARTIAL** — local extraction output is available; exact owner-file UI acceptance is not.
- ID 11 — Studio page navigation: **PARTIAL** — local canvas/page-jump behavior was inspected; exact owner-file timing and deployed-browser behavior are unverified.
- ID 12 — AI factual grounding: **PARTIAL** — no provider-backed repeated checks were possible on the exact owner PDF.
- ID 13 — Delete speed/undo: **PARTIAL** — delete/undo and reload work locally; timing on the exact 5.45 MB owner file was not measured.
- ID 14 — Annotate/Redact behavior: **PARTIAL** — local outputs were opened and checked; the disputed owner-specific “Important” scenario was not reproduced.
- ID 15 — Studio header/footer: **PARTIAL** — code changes are present; the requested rest/scrolled visual comparison at 1104/1920 px is incomplete.
- ID 16 — Developer/API documentation layout: **NOT TESTED** — the complete responsive Swagger/ReDoc/developer-page acceptance was not captured.
- ID 17 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 18 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 19 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 20 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 21 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 22 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 23 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 24 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 25 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 26 — Aadhaar-pattern masking: **FIXED** — two local synthetic positive-mask rounds verified that the marked identifier was masked; the sample value is omitted from all report output.
- ID 27 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 28 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 29 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 30 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 31 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 32 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 33 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 34 — AI Docs layout during Brief: **PARTIAL** — local document handoff/layout and proactive greeting are checked; real 69-page provider generation was unavailable.
- ID 35 — Proactive AI greeting: **FIXED** — browser handoff showed the greeting and page context; local regression tests cover the reply path.
- ID 36 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 37 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 38 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 39 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 40 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 41 — PDF-to-Markdown: **PARTIAL** — the two 69-page substitute outputs opened; exact owner-file output/runtime parity is unverified.
- ID 42 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 43 — Studio delete timing/undo window: **NOT TESTED** — functional delete/undo passed, but exact large owner-file speed/window metrics were not measured.
- ID 44 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 45 — Studio footer/scroll behavior: **PARTIAL** — responsive code changes exist; the specified 1104/1920 rest/scrolled capture pair is missing.
- ID 46 — Quota wording: **FIXED** — local UI and regression checks use the corrected quota wording.
- ID 47 — Studio drag reorder: **FIXED** — page 1→2 and page 4→3 both returned HTTP 200; exported and reloaded 69-page substitute text/order matched expected pages.
- ID 48 — Studio duplicate workflow: **PARTIAL** — local duplicate/workflow checks exist; production account/session behavior is not tested.
- ID 49 — Studio export: **PARTIAL** — multiple local 69-page substitute exports succeeded and matched content; the owner's exact 5.20 MB document was unavailable.
- ID 50 — Developer API page: **PARTIAL** — UI/docs adjustments are present; code-snippet, quota, and responsive acceptance is incomplete.
- ID 51 — Settings label wrapping: **NOT TESTED** — required phone sizes/themes were not measured for this item.
- ID 52 — AI Docs empty-state fragment: **NOT TESTED** — specified phone/browser-state acceptance was not captured.
- ID 53 — Studio scrolled header: **PARTIAL** — code changes are present; required desktop rest/scrolled screenshots are incomplete.
- ID 54 — Legacy tool redirects: **FIXED** — redirects are present and regression-tested locally.
- ID 55 — Operations Today layout: **NOT TESTED** — desktop-width layout acceptance was not captured.
- ID 56 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 57 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 58 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 59 — Responsive sidebar: **PARTIAL** — mobile heights were exercised; the complete 820 px/tablet theme matrix is not.
- ID 60 — Resend invalidates old OTP: **FIXED** — persistence tests reject the earlier code, accept the latest once, and the endpoint now explicitly says the earlier code is invalid. Wrong signup codes receive a neutral invalid/expired response.
- ID 61 — OTP email delivery: **PARTIAL** — simulated-success behavior was removed; real sender-domain delivery and inbox timing were not tested.
- ID 62 — Export/zoom after resize: **NOT TESTED** — resize/reparent export behavior was not verified.
- ID 63 — Registration without OTP: **FIXED** — local regression tests verify the configured no-OTP path does not issue an OTP.
- ID 64 — Forms Add Field/export: **PARTIAL** — form API/output lifecycle tests exist; the exact owner form and browser add/inspect/export sequence were not fully proven.
- ID 65 — Authentication lockout/rate limit: **FIXED** — local lockout and retry timing tests pass; production auth quotas were not touched.
- ID 66 — Developer page responsiveness: **PARTIAL** — responsive styles remain, but complete fresh viewport/theme captures are missing.
- ID 67 — Job-download tenant isolation: **FIXED** — local access-control tests cover anonymous and cross-user not-found behavior.
- ID 68 — Drawn signature: **FIXED** — local draw/export artifacts were opened and visually checked in prior evidence rounds; the full suite passes.
- ID 69 — Clear Studio PDF: **PARTIAL** — local Clear unloads, removes saved PDF/position, and permits a fresh upload; the two-account and owner-file acceptance is open.
- ID 70 — Page Organizer visual controls/order: **FIXED** — drag reorder and content-checked output work; arrow controls remain the touch fallback.
- ID 71 — Annotate content: **FIXED** — both local tool-audit rounds opened outputs with the annotation marker present.
- ID 72 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 73 — Studio resize/page/canvas sync: **NOT TESTED** — resize synchronization acceptance was not captured.
- ID 74 — Terms §4 copy: **FIXED** — corrected copy remains and local regression checks pass; owner/legal review is advisory.
- ID 75 — Compare output: **FIXED** — both local rounds opened the diff with real synthetic filenames and changed content.
- ID 76 — Empty-field Run-disable: **PARTIAL** — local empty/no-match behavior is covered; the full 41-tool UI validation sweep is not.
- ID 77 — Mobile geometry/OCR row clipping: **NOT TESTED** — the requested 390 px OCR/geometry capture is missing.
- ID 78 — Open in Studio: **PARTIAL** — local handoff works; repeated live tool-to-Studio behavior is not verified.
- ID 79 — History/Dashboard FAQ wording: **FIXED** — copy remains present and local checks pass.
- ID 80 — Mobile Settings overflow: **NOT TESTED** — Settings tab strip/overflow was not captured at the required viewport.
- ID 81 — Duplicate security headers: **PARTIAL** — application/NGINX config was adjusted and Compose config validates; proxied live response could not be checked without Docker/Nginx.
- ID 82 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 83 — AI connection debug control: **PARTIAL** — local code/tests cover safe behavior; production query-parameter behavior is unverified.
- ID 84 — Tracker item: **NOT TESTED** — title and acceptance criteria were not supplied.
- ID 85 — Mobile result/toast clipping: **NOT TESTED** — required mobile result-card/toast capture is missing.
- ID 86 — AI Docs phone polish: **NOT TESTED** — the specified phone-layout capture is missing.
- ID 87 — Bottom-bar label size: **NOT TESTED** — phone label legibility was not measured.
- ID 88 — Merge output: **FIXED** — two local content-audit rounds produced an opened 72-page merge with the expected stable filename; the Tool Desk browser merge also produced a four-page output from two synthetic PDFs.
- ID 89 — JSON registration: **FIXED** — local regression tests cover the JSON registration path.
- ID 90 — Concurrent jobs: **PARTIAL** — local parallel job batches completed; production concurrency is untested.
- ID 91 — `/settings`: **FIXED** — local GET returns HTTP 200 and has regression coverage.
- ID 92 — New Page/discard: **PARTIAL** — browser showed the confirmation before clearing and Cancel retained the loaded document; exact owner 69-page state is unavailable.
- ID 93 — Persistence/redeploy survival: **PARTIAL** — named data volume, configurable paths, and backup intent are documented/configured; actual production mount identity and redeploy survival were not inspected.
- ID 94 — Developer API keys: **PARTIAL** — local Bearer/X-API-Key lifecycle and `last_used_at` tests pass; container-redeploy persistence is unverified.
- ID 95 — Smart Metadata export: **PARTIAL** — local exports opened in both tool rounds; provider-backed owner-file accuracy remains open.
- ID 96 — Fill Form: **PARTIAL** — local form-fill lifecycle passes on a substitute; exact owner form and production parity are unavailable.
- ID 97 — Password-reset email: **PARTIAL** — the route no longer reports simulated delivery and uses the configured public origin; actual inbox delivery/link/password-change/login was not tested.
- ID 98 — Cashfree production payments: **PARTIAL** — invalid environment fails closed, demo activation is disabled by default in production, and sandbox configuration is checked; owner PROD setup/webhook and the owner-run real payment remain outstanding.
- ID 99 — AI Chat document gating: **FIXED** — local tests cover document-grounded handling without a phrase gate and Page 2 citations; no live provider claim is made.
- ID 100 — Mobile drawer: **PARTIAL** — prior 667/740/781/844/932 light/dark captures support the dynamic viewport fix; the full browser-chrome shown/hidden phone matrix was not repeated.
- ID 101 — Admin secret code: **NOT TESTED** — explicitly owner-handled/excluded by the prompt; it was not changed and its value is not reproduced here.
- ID 102 — Feedback write/read across processes: **PARTIAL** — local synthetic submissions and admin visibility are covered in unit/browser checks; production multi-process persistence/visibility was not tested.
- ID 103 — Tracker item: **NOT TESTED** — this tracker entry's title and criteria were not supplied.
- ID 104 — Tracker item: **NOT TESTED** — this tracker entry's title and criteria were not supplied.
- ID 105 — Smart Metadata date/topics: **FIXED** — local regression tests reject section-number dates and boilerplate topics; exact provider-backed owner-file accuracy remains a broader ID 9 limitation.
- ID 106 — First-attempt reliability: **PARTIAL** — two local 41-tool rounds completed available operations; the owner-reported live 502/75% stalls across the named browser operations were not tested.
- ID 107 — Tracker item: **NOT TESTED** — this tracker entry's title and criteria were not supplied.
- ID 108 — Disable public API docs in production: **FIXED** — production OpenAPI/Swagger/ReDoc routes are disabled in code and regression-tested.
- ID 109 — Retention copy/scope: **PARTIAL** — copy now separates temporary server jobs from browser-saved Studio/AI work and reflects configurable job TTL; production saved-document cleanup/retention was not verified.
- ID 110 — SEO headings: **FIXED** — all 41 tool-route headings matched in two consecutive recorded runs.
- ID 111 — Word-to-PDF file carryover: **FIXED** — browser ran Merge with two PDFs, then Word to PDF showed zero files and zero file rows.
- ID 112 — HTML-to-PDF SSRF: **FIXED** — tests reject private/loopback/link-local/metadata/non-HTTP targets and redirects into private networks; local localhost import was refused by the guard.
- ID 113 — Repair damaged PDF: **FIXED** — the truncated synthetic file was recovered to a readable PDF; exact owner-corrupted input remains outside scope.
- ID 114 — Account-scoped Studio storage/Clear: **PARTIAL** — storage keys are scoped by account and epoch; browser Clear/fresh-upload passed; a two-account authenticated browser test remains open.
- ID 115 — Feedback overlap: **FIXED** — 390 px height matrix, Studio zoom, cards/nav, dialog visibility, and confirmed-submission behavior passed in local browser checks.
- ID 116 — Sanitize summary/download: **FIXED** — endpoint returns the cleaned output and tested removal summary; UI reports failure rather than silently stopping.
- ID 117 — Digital signatures: **FIXED** — raw-byte regex parsing was replaced by PDF signature-dictionary parsing; unsigned, valid synthetic signature, tampered/out-of-bounds, and signed-output tests pass.
- ID 118 — Admin X-Forwarded-For trust/status: **FIXED** — forwarded IP is trusted only from configured Nginx peer; status no longer exposes another IP's lockout state; local tests pass.
- ID 119 — Mobile Studio Organize: **FIXED** — at 390 × 844 the drawer opened below the toolbar with zero overlap; all measured controls were reachable.
- ID 120 — `/admin` HEAD: **FIXED** — HEAD returns the portal status without a response body and is regression-tested.
- ID 121 — Standalone signing/security entry: **FIXED** — Protect/Unlock link to the security audit flow; Sign copy directs users to Studio's signing surface.
- ID 122 — First-load/main-thread performance: **PARTIAL** — lazy PDF engines reduced initial transfer by about 49.9% and local tool switches measured 78–106 ms; a dedicated Studio-export long-task profile and real low-end-device run remain open.
- ID 123 — Local-mode download details: **PARTIAL** — local result metadata/link code exists; the local-mode download UI was not fully driven end-to-end in the browser.
- ID 124 — Copy nits: **PARTIAL** — copy updates cover multiple listed issues, but all nine items were not individually verified across widths/themes.
- ID 125 — Compact Studio toolbar: **FIXED** — screenshot/evidence at 1920 px measures two rows and 80 px total height; 390 px controls remain reachable and legible.
- ID 126 — Tracker item: **NOT TESTED** — the tracker entry's title and acceptance criteria were not supplied.
- ID 127 — Crawlable tool cards/redirects/sitemap: **FIXED** — cards render as anchors, legacy redirects are present, and route/SEO checks pass locally.
- ID 128 — Feedback dismissal and submission lifecycle: **FIXED** — dismiss state persisted across reload; after a confirmed synthetic submit the main pill hid and Settings reopened the form.

## Reproductions R1–R8: before → after

- R1 (ID 60): earlier resend allowed an older OTP; now only the latest is accepted, the resend response names the invalidation, and arbitrary wrong codes get a neutral error. Tested locally with synthetic codes only.
- R2 (ID 1): not reproduced against an upstream service because AI credentials/configuration are absent. Local no-provider response is safe; translation success remains open.
- R3 (ID 2): not tested with a provider; small/69-page results remain open. No upstream call was made.
- R4 (ID 4): the sole supplied Drive link is one-page, not the 69-page acceptance file; latest local DNS failed before fetch. Keep partial per the owner's instruction.
- R5 (ID 117): fabricated raw-byte signature reports are fixed by parsing real PDF signature dictionaries; unsigned/valid-synthetic/tamper/output tests pass.
- R6 (ID 113): synthetic truncated PDF recovers to a readable output locally; exact owner fixture not available.
- R7 (ID 114): local browser storage is account-scoped and Clear/fresh-upload works; no two-account login journey was run.
- R8 (IDs 93/102): production database/container/feedback cross-process state was not inspected or mutated. Local config is not proof of production mounts.

## 41-tool content audit

Two rounds attempted 41 catalog operations each. Each round had 37 verified completed artifacts, 3 unavailable operations (OCR, Summarize, Translate), and one expected SSRF block for a localhost HTML-to-PDF request. The repo 69-page substitute and synthetic form/Office/images were used. This is not a provider, owner-file, live UI, or production pass. Full per-operation proof: [TOOL-CONTENT-AUDIT.md](TOOL-CONTENT-AUDIT.md).

## Security audit findings

**Risk posture:** no high-confidence live provider key/private-key pattern was found in the current worktree; the dependency audit found no known vulnerabilities. The highest release risk is that critical production state and auth/payment integrations cannot be proven from this local checkout.

| Severity | Issue | Evidence | Required action |
|---|---|---|---|
| High | Owner-handled admin secret rotation remains open | The prompt says the existing admin secret/default was publicly present in prior history and is owner-handled; this audit intentionally did not change or reproduce it. | Make the repository private as planned, rotate the admin secret out-of-band, and keep it only in the production secret manager. |
| High | Production DB/backup/feedback consistency is unverified | Compose declares a named volume and backup target, but Docker Desktop could not inspect an actual mount; no production writes/read/redeploy were attempted. | Owner verifies one shared persistent DB path for every app worker/container, tests redeploy survival, performs a backup restore drill, and confirms each feedback write appears in admin. |
| Medium | Live transport and proxy headers were not inspected | Local CSP/security-header code and Compose config validate; no production HTTPS/TLS/header response or Nginx container was scanned. | After owner authorization, inspect HTTPS redirect, certificate/TLS, HSTS, CSP, frame/referrer/content-type headers, duplicate headers, and exposed files on the live site. |
| Medium | Mail and AI provider delivery remain unverified | Local tests remove inherited provider credentials; reset email and AI translation/summarization were not sent upstream. | Owner configures verified mail/AI providers and checks delivery/output with test accounts and synthetic PDFs. |
| Medium | Cashfree production checkout remains unverified | Production keys/webhook/merchant setup are owner-only; no real payment was run. | Owner configures Cashfree PROD, verifies sandbox first, checks webhook/signature handling, then runs the explicitly owner-only small real payment. |
| Low | Generic secret scanner matches | 18 generic assignment matches were reviewed as test patterns or placeholders; no known key-format or private-key block was found. Git-history scanning was unavailable. | Continue keeping real credentials out of source/history; rotate any value ever committed and use the secret manager. |

## Remaining gaps that keep the verdict at HOLD

- AI Translate and Brief/Summarize have no verified provider-backed outputs (IDs 1/2).
- The only supplied Drive link is not the requested 69-page document (ID 4).
- Production database mount/redeploy/backup and cross-process feedback visibility remain unproven (IDs 93/102).
- Cashfree PROD setup and its owner-run real payment remain outstanding (ID 98).
- Password-reset email receipt remains unverified (ID 97).
- Exact owner PDFs, a two-account same-browser Studio test, full real-phone browser-chrome/theme matrix, and a live Nginx/TLS/header scan remain open.
- Tracker detail was absent for IDs 7, 16–25, 27–33, 36–40, 42, 44, 51–52, 55–58, 62, 72–73, 77, 80, 82, 84–87, 103–104, 107, and 126; those are explicitly marked NOT TESTED.

## Owner-only items

1. Keep the admin secret/repository private and rotate that secret outside this audit (ID 101).
2. Configure Cashfree PROD and perform the owner-authorized real payment (ID 98).
3. Provide an authorized test mail/provider setup and verify password-reset delivery plus AI outputs (IDs 1, 2, 97).
4. On the owner host, verify named-volume identity, worker/container DB path, redeploy survival, feedback read-after-write, backup, and restore without running cleanup on real accounts (IDs 93/102).
5. Provide the exact 69-page PDF if exact-file import/export is still required; the only supplied Drive link remains a one-page file (IDs 3/4/49).

## Architecture and scaling recommendation

The current FastAPI/SQLite-WAL design can serve a small single-host deployment, but SQLite writes across multiple workers/containers and shared/network storage are not a validated path to 100k users. Move to managed PostgreSQL for transactional multi-writer state, object storage for PDFs/results, an asynchronous job queue for heavy conversions/AI, and shared Redis-backed rate limits/session coordination. Add load tests for worker count, queue depth, storage throughput, and restore time before scaling; these changes were not performed in this audit.

## Scope and change control

This was a local codebase/configuration audit with local synthetic data. No production URL, live TLS/headers, owner account, production database, real mailbox, AI provider, Cashfree checkout, or real payment was exercised. The current local scanner and tests are not a penetration test. All changes remain uncommitted on `launch-audit-v10`; nothing was pushed or deployed.
