# Paperplane launch-audit-v9 — FINAL REPORT

Branch: launch-audit-v9, based on 39f8c9b.  
Verdict: HOLD.  
Audit date: 2026-11-10.

## Executive result

The requested v9 audit and local fixes are complete. The working tree remains uncommitted. No commit, push, deploy, SSH session, production database mutation, simulated billing call, or real payment was performed.

The final local full test suite passed twice consecutively:

| Run | Result | Pytest duration | Wall duration | Warning |
|---|---:|---:|---:|---|
| 1 | 348 passed, 0 failed | 102.50 s | 1:46.79 | One Starlette TestClient/httpx deprecation |
| 2 | 348 passed, 0 failed | 72.38 s | 1:17.34 | Same single deprecation |

Logs: [run 1](test-suite-run-1.log) and [run 2](test-suite-run-2.log). A focused regression for the public health-route path disclosure also passed (1 passed). Python compilation, JavaScript syntax checks, git diff whitespace checks, and Docker Compose configuration validation passed. The whitespace check reports only the known LF-to-CRLF normalization warning for persistence.py. Dependency audit with pip-audit reported no known vulnerabilities in requirements.txt or requirements-dev.txt. Docker Compose configuration parsing succeeded; the Docker Engine and Nginx runtime were unavailable, so no container rebuild, restore, or proxied-header acceptance was claimed.

The local fixes include admin-session hardening, admin endpoint protection, OTP handling, user-deletion cleanup, financial reporting safeguards, AI provider isolation, Studio workflows, and frontend validation. The final evidence does not satisfy all 20 mandatory Appendix B gates. In particular, owner-provided AI/payment credentials, the exact 69-page owner PDF, real email delivery, the actual production volume, and a running Docker/Nginx edge were unavailable. The required verdict is therefore HOLD.

## Reproduction log and method

Phase -1 was completed before source edits. Every P0/P1 described in the mounted v9 prompt received a reproduction entry before its fix. The log distinguishes observed local behavior from source tracing and from historical live evidence supplied by the owner. It records expected behavior, suspected root cause, fix plan, and discriminating regression test.

See [REPRODUCTION-LOG.md](REPRODUCTION-LOG.md). Reproductions include persistence/redeploy uncertainty, Cashfree demo activation, AI provider configuration and routing, Studio reorder and retention, fresh API keys, attached-PDF chat routing, reset-email simulation, admin authorization, OTP storage and delivery, CSV formula injection, account artifact deletion, email HTML escaping, duplicate security headers, and the public health-route path leak.

The exact owner test pack was not mounted in this workspace. The repo fixture notes-69page.pdf is 4,980,286 bytes and 69 pages; it is a substitute, not the owner's notes_test.pdf (5,456,746 bytes). The supplied Drive URL was imported locally as a 1-page, 554,620-byte PDF. The owner confirmed there is no other Drive link. The repo AcroForm sample is a 1-page, 2,253-byte file with three widgets; it is not the owner's exact test-form.pdf. Results using these substitutes are labeled accordingly.

## Phase 7 A–Z verification

The local tool-content run invoked all 41 processor operations twice and inspected generated artifacts with format parsers. It recorded 82 attempts: 74 outputs opened (37 per round) and 8 blocked/failed outputs (4 per round). Evidence, filenames, byte sizes, content checks, and durations are in [TOOL-CONTENT-AUDIT.md](TOOL-CONTENT-AUDIT.md) and [tool-content-audit.json](outputs/tool-content-audit.json).

The 4 blocked operations per round were:

- HTML to PDF: local-host access refused by the SSRF guard. This is expected security behavior for the test URL.
- Summarize: no AI provider is configured.
- Translate: no provider produced a translated PDF.
- Mask Aadhaar: the substitute PDF contains no matching synthetic number, so no output is correct; the no-match UI was separately checked twice and returned a neutral “No change made” result in 0.895 s and 0.869 s.

This is a worker/process-level content audit, not proof of every public UI/API route or production runtime. Some operations use format-specific generated test documents or the repo AcroForm sample. Provider-backed output on the owner file, the actual public proxy, the exact 69-page file, and the exact form fixture remain unverified. No failure above is counted as a product pass.

Additional local checks:

- Page Organizer order 3,1,2: both outputs opened as 3-page PDFs with text order page 3 → page 1 → page 2.
- Compare: both generated text diffs were opened; original filenames and changed content were present.
- Studio ↔ AI Docs handoff: two rounds preserved the active document and page context; page-2 citation navigation opened page 2 in Studio.
- Smart Metadata export: two fallback-parser exports opened as JSON with the expected local fields; provider-backed extraction is still pending.
- Concurrent local jobs: two batches of four Rotate jobs completed and downloaded successfully (4/4 per batch); this is not a production load test.
- Security headers: direct local application response had one instance of each checked header. The Nginx proxy result remains untested.
- The final two full-suite runs are the only final acceptance runs counted. An earlier candidate run had one stale AI transport mock; the test harness was corrected to mock the current request abstraction and supply synthetic runtime provider configuration, and the final two suites passed.

## Per-item tracker status — all IDs

FIXED means the local change was reproduced and checked on the local build with the evidence stated. It does not imply production deployment. PARTIAL means a local fix or proof exists but an acceptance condition, exact fixture, account, external service, or live/runtime check is missing. NOT TESTED means the description/evidence was not present or the specific check was not run.

| ID | Status | Item and evidence / remaining proof |
|---:|---|---|
| 1 | PARTIAL | Translate: native provider routing and safe failures are implemented; both tool-audit rounds lacked a provider result. Owner provider credentials and 2-page EN→HI plus 10-page EN→ES output checks remain. |
| 2 | PARTIAL | Brief/Summarize: no configured AI provider; neither the exact owner 69-page file nor provider-backed brief/summary is verified. |
| 3 | PARTIAL | Studio retention/export: local workflows and exports are improved; exact owner-file delete 69→68→67 across two reloads is not verified. |
| 4 | PARTIAL | Exact supplied Drive link imported locally as a 1-page, 554,620-byte PDF. It is not the 69-page file and the public live import was not tested. |
| 5 | PARTIAL | Citation rendering and navigation were checked with local synthetic content; deterministic provider citations across three real-document runs remain unverified. |
| 6 | PARTIAL | False-premise behavior against real document text and provider output was not validated with the owner file/provider. |
| 7 | NOT TESTED | Tracker title and acceptance detail for ID 7 were not mounted in the prompt/worktree. |
| 8 | PARTIAL | Remove output opened as a 68-page PDF in both worker rounds on the repo substitute; the reported first-attempt live timeout and exact owner file remain unverified. |
| 9 | PARTIAL | Smart Metadata fallback exports opened twice. The exact 69-page provider result and real DOCUMENT DATE semantics remain unverified. |
| 10 | PARTIAL | Multi-page extraction path was improved and local extract artifacts exist; exact owner-file UI acceptance remains open. |
| 11 | PARTIAL | Page-jump/canvas rendering was locally inspected; deterministic timing on the exact owner file and deployed browser is unverified. |
| 12 | PARTIAL | AI citation/false-claim behavior is not proven across the owner file and provider-backed repeated runs. |
| 13 | PARTIAL | Delete/undo flow was improved, but speed and undo-window timing on the 5,456,746-byte owner file were not measured. |
| 14 | PARTIAL | Annotate and Redact outputs were opened in the local content audit; the disputed “Important” behavior is not accepted against the owner’s exact scenario. |
| 15 | PARTIAL | Studio header/footer behavior was changed, but the required rest/scrolled screenshots at 1104 and 1920px were not captured as an acceptance pair. |
| 16 | NOT TESTED | Swagger/ReDoc link state and the full responsive developer page acceptance were not directly captured for this item. |
| 17 | NOT TESTED | Tracker title and acceptance detail for ID 17 were not mounted. |
| 18 | NOT TESTED | Tracker title and acceptance detail for ID 18 were not mounted. |
| 19 | NOT TESTED | Tracker title and acceptance detail for ID 19 were not mounted. |
| 20 | NOT TESTED | Tracker title and acceptance detail for ID 20 were not mounted. |
| 21 | NOT TESTED | Tracker title and acceptance detail for ID 21 were not mounted. |
| 22 | NOT TESTED | Tracker title and acceptance detail for ID 22 were not mounted. |
| 23 | NOT TESTED | Tracker title and acceptance detail for ID 23 were not mounted. |
| 24 | NOT TESTED | Tracker title and acceptance detail for ID 24 were not mounted. |
| 25 | NOT TESTED | Tracker title and acceptance detail for ID 25 were not mounted. |
| 26 | PARTIAL | Aadhaar no-match response was neutral and visible twice; the positive masking case was not re-run with a synthetic positive-match PDF in this round. |
| 27 | NOT TESTED | Tracker title and acceptance detail for ID 27 were not mounted. |
| 28 | NOT TESTED | Tracker title and acceptance detail for ID 28 were not mounted. |
| 29 | NOT TESTED | Tracker title and acceptance detail for ID 29 were not mounted. |
| 30 | NOT TESTED | Tracker title and acceptance detail for ID 30 were not mounted. |
| 31 | NOT TESTED | Tracker title and acceptance detail for ID 31 were not mounted. |
| 32 | NOT TESTED | Tracker title and acceptance detail for ID 32 were not mounted. |
| 33 | NOT TESTED | Tracker title and acceptance detail for ID 33 were not mounted. |
| 34 | PARTIAL | AI Docs layout remains stable in local UI checks and the slow-generation layout was stubbed; a real 69-page provider Brief was unavailable. |
| 35 | FIXED | Attached-document greeting checks are covered by the local regression suite; no greeting/provider live acceptance is claimed. |
| 36 | NOT TESTED | Tracker title and acceptance detail for ID 36 were not mounted. |
| 37 | NOT TESTED | Tracker title and acceptance detail for ID 37 were not mounted. |
| 38 | NOT TESTED | Tracker title and acceptance detail for ID 38 were not mounted. |
| 39 | NOT TESTED | Tracker title and acceptance detail for ID 39 were not mounted. |
| 40 | NOT TESTED | Tracker title and acceptance detail for ID 40 were not mounted. |
| 41 | PARTIAL | PDF-to-Markdown produced opened 69-page substitute outputs in two rounds; exact owner-file output and provider/runtime parity remain unverified. |
| 42 | NOT TESTED | Tracker title and acceptance detail for ID 42 were not mounted. |
| 43 | NOT TESTED | Delete speed/undo on the exact large owner document was not measured. |
| 44 | NOT TESTED | Tracker title and acceptance detail for ID 44 were not mounted. |
| 45 | PARTIAL | Footer/scroll behavior was addressed in code; the exact required Studio screenshots and scroll states were not verified. |
| 46 | FIXED | Quota wording was corrected in the UI and regression-checked locally. |
| 47 | PARTIAL | Studio reorder is fixed in local UI/process checks; exact owner-file drag payload → response bytes → exported-byte order is not verified. |
| 48 | PARTIAL | Duplicate Studio workflow is covered by local checks; production account/session behavior is not verified. |
| 49 | PARTIAL | Local 2-page and repo 69-page exports were opened; the exact owner 69-page export/reload chain is unavailable. |
| 50 | PARTIAL | Developer API docs/UI were adjusted; exact code-snippet, quota, and responsive acceptance on the production page is not fully captured. |
| 51 | NOT TESTED | Settings label wrapping/clipping at the specified phone sizes was not measured in this round. |
| 52 | NOT TESTED | AI Docs empty-state citation fragment was not measured against the required phone viewport/browser states. |
| 53 | PARTIAL | Studio scrolled-header path was addressed, but the required 1104/1920px rest/scrolled visual acceptance is missing. |
| 54 | FIXED | Legacy tool slugs redirect to the supported tool paths in the local app and are regression-checked. |
| 55 | NOT TESTED | Operations Today layout at desktop widths was not measured in this round. |
| 56 | NOT TESTED | Tracker title and acceptance detail for ID 56 were not mounted. |
| 57 | NOT TESTED | Tracker title and acceptance detail for ID 57 were not mounted. |
| 58 | NOT TESTED | Tracker title and acceptance detail for ID 58 were not mounted. |
| 59 | PARTIAL | Responsive sidebar changes were checked at mobile heights; the full required 820px, both-theme/tablet no-regression capture is not complete. |
| 60 | FIXED | Two locally seeded, unexpired OTPs remain usable after resend; latest-code notice and expiry behavior have regression coverage without consuming production quota. |
| 61 | PARTIAL | OTP delivery no longer uses simulation, but verified sender-domain configuration and inbox placement were not tested. |
| 62 | NOT TESTED | Export/zoom behavior after Studio resize/reparenting was not verified. |
| 63 | FIXED | Local tests confirm registration does not issue an OTP when configured for the no-OTP registration path. |
| 64 | PARTIAL | Add Field UI and output round trips were exercised locally with a substitute form; both required surfaces and exact owner test-form.pdf are not fully proven. |
| 65 | FIXED | Local regression tests verify lockout/rate-limit behavior and retry timing; no production auth quota was consumed. |
| 66 | PARTIAL | Developer page responsive styles were retained; a complete fresh capture at all required widths/themes is missing. |
| 67 | FIXED | Local access-control tests confirm anonymous/fake and cross-user job access returns not-found behavior. |
| 68 | FIXED | Drawn signature was saved, exported, opened, and visually checked in two local rounds; screenshots and output PDFs are in the evidence folder. |
| 69 | PARTIAL | Studio Clear PDF confirmation and no-document persistence were implemented; exact 69-page reload proof was not run. |
| 70 | FIXED | Page Organizer order 3,1,2 opened with the expected page text sequence in both local rounds; copy now describes the page-number field honestly. |
| 71 | FIXED | Annotate output content was opened and checked in both tool-audit rounds; annotations were present in the output. |
| 72 | NOT TESTED | Tracker title and acceptance detail for ID 72 were not mounted. |
| 73 | NOT TESTED | Studio resize/page/canvas synchronization after resize was not checked. |
| 74 | FIXED | Terms §4 copy remains corrected in the local branch; legal review by the owner remains advisory, not a code pass. |
| 75 | FIXED | Compare text outputs opened in both rounds; original filenames and the actual diff body were present. |
| 76 | PARTIAL | Empty input/no-match messaging is improved and the no-match state was checked twice; the complete all-41 UI validation sweep was not proven. |
| 77 | NOT TESTED | Studio geometry/order and OCR row clipping at 390px was not captured. |
| 78 | PARTIAL | Open-in-Studio behavior is covered by local checks; repeated live tool-to-Studio acceptance is not verified. |
| 79 | FIXED | History/Dashboard FAQ wording remains present in the local branch and is regression-checked. |
| 80 | NOT TESTED | Mobile Settings pane overflow and clipped tab strip were not captured. |
| 81 | PARTIAL | App emits one set of response headers locally and Nginx hides duplicate upstream values in config; actual proxied response is unverified because Nginx/Docker were unavailable. |
| 82 | NOT TESTED | Tracker title and acceptance detail for ID 82 were not mounted. |
| 83 | PARTIAL | Debug-only AI connection control behavior is covered in local code/tests; production query-parameter behavior was not verified. |
| 84 | NOT TESTED | Tracker title and acceptance detail for ID 84 were not mounted. |
| 85 | NOT TESTED | Mobile result-card clipping and toast-over-Run behavior were not measured. |
| 86 | NOT TESTED | AI Docs phone polish items were not captured in the required viewport. |
| 87 | NOT TESTED | Bottom-bar labels at 9px on phone were not measured. |
| 88 | FIXED | Merge outputs opened with the expected 72-page total in both rounds and the output name is stable. |
| 89 | FIXED | JSON registration path is covered by local regression tests and remains operational. |
| 90 | PARTIAL | Two batches of four local concurrent jobs completed and downloaded without 502; production concurrency remains untested. |
| 91 | FIXED | Local GET /settings returns HTTP 200 and is covered by regression checks. |
| 92 | PARTIAL | New Page confirmation and empty-document restore guard are implemented; the exact owner 69-page discard/reload flow is not proven. |
| 93 | PARTIAL | Startup diagnostics, configurable named volume, external-to-volume backup destination, and local same-path restart checks were added. Docker rebuild, actual live volume identity, and backup restore are unverified. |
| 94 | PARTIAL | Two fresh synthetic keys passed Bearer and X-API-Key usage/job calls twice each and last_used_at updated. Key persistence through the actual container redeploy is unverified. |
| 95 | PARTIAL | Smart Metadata JSON exports opened in both rounds with expected local fields; provider-backed 69-page metadata/date accuracy remains open. |
| 96 | PARTIAL | Form fill output was opened on the local 3-widget substitute; exact test-pack form and production parity were unavailable. |
| 97 | PARTIAL | Reset emails now fail closed instead of simulated success and use the configured public HTTPS origin; real sender delivery, link, password change, and new login were not run. |
| 98 | PARTIAL | Production TEST checkout is blocked and demo activation is disabled by default; owner PROD keys, verified merchant URL/name, webhook, and owner-run real payment remain outstanding. |
| 99 | FIXED | Exact 2-page local question returned “beta” with a Page 2 citation; greeting checks and no-document gate have regression coverage. |
| 100 | PARTIAL | Mobile drawer/sidebar now uses a dynamic viewport height with fallback. Before/after screenshots exist at 667/740/781/844/932 in light/dark; browser chrome shown/hidden is not independently proven. |

IDs 7, 17–25, 27–33, 36–40, 42, 44, 56–58, 72, 82, and 84 have no tracker description in the mounted prompt or worktree, so they are deliberately NOT TESTED rather than guessed.

## Appendix B — 20 mandatory acceptance gates

| Gate | Status | Proof and remaining condition |
|---:|---|---|
| 1 — ID 93 redeploy persistence | PARTIAL | Local same-path restart and diagnostics were checked; Docker rebuild and owner-host volume/restore acceptance unavailable. |
| 2 — ID 98 Cashfree PROD | PARTIAL | Local production guard blocks TEST/demo; real merchant setup, webhook and owner-run payment required. |
| 3 — IDs 1+2 AI provider | PARTIAL | Provider adapters and error handling are covered locally; no provider credential or exact 69-page AI output. |
| 4 — IDs 3+49+47 Studio | PARTIAL | Substitute outputs and local reorder checked; exact owner 69-page mutation, reload and export proof absent. |
| 5 — ID 94 Developer API | PARTIAL | Fresh key/header calls passed locally; survival across real volume/container redeploy is unknown. |
| 6 — ID 4 Cloud Import | PARTIAL | Supplied Drive viewer link imported a 1-page file locally; not the requested 69-page acceptance and no live-site claim. |
| 7 — ID 99 AI Chat | FIXED | Exact local 2-page question returned beta and a Page 2 citation in repeated regression coverage. |
| 8 — ID 60 resend | FIXED | Local seeded old/new OTP test passed without spending production email quota. |
| 9 — ID 97 reset email | PARTIAL | No simulated success and canonical URL checks are fixed; real email/reset/login cycle is not verified. |
| 10 — ID 76 empty fields | PARTIAL | Empty states and no-match are improved; the requested all-41 UI button/message sweep is incomplete. |
| 11 — ID 64 Forms Add Field | PARTIAL | Local forms/export round trips exist; exact form fixture and both-surface acceptance are incomplete. |
| 12 — ID 68 drawn signature | FIXED | Export opened and drawn pixels checked twice on the local fixture. |
| 13 — IDs 69+92 Clear/New Page | PARTIAL | Confirmation and persisted no-document state implemented; exact full-file reload path not verified. |
| 14 — ID 100 drawer 100dvh | PARTIAL | Height/theme screenshots exist; browser chrome shown/hidden and profile/settings reachability acceptance is incomplete. |
| 15 — SEO off-by-one | PARTIAL | Local SEO behavior was addressed, but all 41 direct landings were not individually verified. |
| 16 — Merge-server stall | PARTIAL | Repo 69-page substitute completed twice in local worker audit; owner file and production worker timeout path unavailable. |
| 17 — IDs 95+96 | PARTIAL | Local metadata export and filled substitute form opened; exact owner test fixtures/provider semantics are missing. |
| 18 — IDs 70+75 | FIXED | Reordered text sequence and Compare body/original names were opened in both rounds. |
| 19 — 41-tool audit | PARTIAL | 82 total attempts; 74 outputs opened, 8 blocked/failed for stated reasons. |
| 20 — Phase 6 no-regress | PARTIAL | Regression suite passed twice and targeted local checks were repeated; some live/mobile/owner-file checks were unavailable. |

## Security and admin audit

### Improvements made

- Admin authorization now depends on a short-lived MFA-issued admin session in the X-Admin-Session header. Query-string admin keys and direct admin-key API authorization were removed from the reviewed paths. Public status no longer exposes owner contact information.
- Admin OTPs are HMAC-protected with configured stable key material instead of a bare six-digit-code hash, are transactionally consumed once, and are not placed in email subjects or application logs. Admin OTP delivery cannot report success if dispatch failed; simulated OTP mail is disabled.
- Admin JSON request bodies are byte-limited when read, OTP verification is race-resistant, and per-IP failure lockout/rate controls remain in place.
- Persistence diagnostics expose paths, file details and row counts only to the MFA admin session. Public /health and /api/health responses are reduced and no longer disclose filesystem paths.
- Probe cleanup requires a preview of exact rows and protects configured owner accounts. User deletion is transaction-scoped, refuses queued/processing work, removes contained job artifacts, and anonymizes financial ledger references rather than erasing accounting history.
- Admin tables escape dynamic values. CSV exports sanitize spreadsheet formula prefixes. Feedback inputs have length/type validation and rate limits. Financial values use explicit INR and decimal arithmetic with deduplication.
- AI credentials are encrypted at rest, scoped to the selected provider, masked as placeholders rather than submitted values, and sent through native provider request formats. HTTPS validation and a no-redirect transport reduce credential-forwarding risk.
- User/password-reset notifications no longer pretend that a simulated email was sent. Dynamic HTML email values are escaped.
- Production startup now requires a stable secret and a canonical HTTPS public URL on a non-local host. Cashfree production refuses TEST mode and demo-paid activation is off unless explicitly enabled for development.
- Nginx configuration suppresses duplicated upstream security headers. The app retains the authoritative CSP; proxy delivery still needs a live response check.

### Residual security risks

- Admin sessions remain stored in sessionStorage and are readable by same-origin JavaScript. A future XSS can steal the token even with a strict CSP. Prefer a short-lived Secure, HttpOnly, SameSite cookie (or a backend-for-frontend), add CSRF protection for cookie-authenticated mutations, rotate/revoke sessions server-side, and use no-store caching for admin responses. OWASP guidance warns against putting session credentials in Web Storage because same-origin script can read them.
- A per-IP lockout can be weaponized to deny the owner access, especially behind shared NAT/proxy addresses. Combine account-based throttles, trusted proxy IP parsing, progressive delay, alerting and a controlled recovery path.
- Configurable AI base URLs are powerful. Even with HTTPS and no redirects, DNS rebinding/TOCTOU and an accidentally allowed private address may expose internal services. Restrict provider hosts where possible and enforce outbound egress policy at the host/network layer.
- AI provider credentials use stable encryption key material; key rotation and re-encryption procedures need to be documented and tested. Do not silently fall back to another provider's credential.
- Intrusion and login notifications contain IP/device metadata. Define retention/access controls and avoid logging personal data or secrets unnecessarily.
- The local review did not include a production authenticated route crawl, external penetration test, TLS scan, container image scan, dependency SBOM/signature verification, AWS IAM/SG audit, or Nginx runtime header capture. A clean pip-audit result is not a complete supply-chain assurance.
- Cloud Import and HTML-to-PDF remain high-risk SSRF surfaces. The tested local-host request was blocked; production DNS rebinding, IPv6, redirect, metadata-IP and alternate-scheme behavior still need a deployed edge test.
- Admin user deletion is destructive by design. Preview, owner protection and synthetic tests exist; test again on a fresh scratch database before enabling the action in production.

OWASP Top 10:2025 prioritizes Broken Access Control, Security Misconfiguration, Supply Chain Failures, Cryptographic Failures, Injection, Authentication Failures and Mishandling of Exceptional Conditions. The code changes directly address several of these classes, but this local audit is not a claim of complete OWASP compliance.

## Persistence and database integrity

SQLite in WAL mode on a persistent Docker named volume is suitable for this single-host app at current scale when there is one local database file, correct permissions, reliable storage, and modest write concurrency. WAL allows readers and a writer to proceed concurrently, but there is still only one writer at a time; WAL requires processes to use the same host and is not suitable for a network filesystem. At 100,000 registered accounts, user count alone does not force a migration. Write volume, queue contention, latency goals, and multi-host needs do.

The local change makes the volume name configurable, adds startup diagnostics for the resolved path, DB size/mtime and key row counts, and adds an MFA-protected persistence health endpoint. The daily backup uses SQLite's online backup API and writes outside the named volume to a configurable host directory. The configured destination is still on the same EC2 host; it does not protect against loss of the host, disk, or account. There was no Docker Engine here to verify actual mounts, rebuild the container, prove the production volume identity, or restore a backup.

WAL + synchronous=NORMAL protects consistency across application crashes, but a committed transaction may be lost after power loss or OS crash. For billing/account state where losing the latest commit is unacceptable, consider synchronous=FULL after measuring the impact. Also verify foreign-key enforcement is enabled on every connection; SQLite does not enable it by default. Explicit transactional deletion logic is present, but a schema-level cascade should not be assumed unless checked table by table.

Before deploying, the owner must inspect the live Compose file and mounts. Set PAPERPLANE_DATA_VOLUME_NAME to the exact currently used volume; never switch it by assumption, because Docker will happily create a new empty named volume and make existing data appear to vanish.

## Payment and revenue accuracy

The expression 2.00% × (1 + 18%) = 2.36% is mathematically correct when the merchant contract charges a 2.00% gateway fee and GST at 18% on that fee. Razorpay currently publishes 2% with 18% GST on the fee. On ₹1,000 gross, that estimate is ₹20 fee + ₹3.60 GST = ₹23.60, leaving ₹976.40 before other adjustments.

Cashfree's current published standard platform fee is 1.95% plus applicable taxes, so 1.95% × 1.18 = 2.301% (about 2.30%); ₹1,000 would imply about ₹23.01 total and ₹976.99 net, before other adjustments. Cashfree also advertises a time-limited new-merchant offer through 31 March 2027 for qualifying domestic transactions up to ₹20 lakh; its terms say GST remains due and is computed using standard 1.95% pricing even where the platform fee is waived. Merchant eligibility, payment instrument, custom pricing, offers, refunds and settlement terms can change the actual figure. Treat a hard-coded percentage as a forecast, not a bank payout.

The admin dashboard now uses an explicit configured fee rate, Decimal arithmetic, INR labeling and deduplicated order records. It estimates gateway deductions from gross values; it is not a settlement ledger or tax/accounting report. The true net bank amount must reconcile gateway settlement statements and account for method-specific rates, GST, refunds, chargebacks, disputes, failed/reversed orders, withholding if applicable, settlement timing/fees, credits and custom merchant pricing. “Gross revenue” should count verified successful/settled charges rather than created orders, and plan changes/refunds should be modeled explicitly.

## Product, AI, UX, and architecture review

- Strengths: FastAPI with server-side authorization, restrictive CSP, external event handlers, request bounds, rate limiting, synthetic cross-user IDOR tests, provider-aware secret routing, stable volume diagnostics, and real artifact content checks are sound choices.
- Remaining authorization risk: every new admin feature needs server-side role checks; hiding a control in JavaScript is not authorization. Continue to deny by default and verify ownership at every job/file endpoint.
- Floating feedback: the mobile offset and validation/rate-limit behavior are implemented. Keep the widget away from sticky navigation and confirm keyboard focus, contrast, reduced motion, and safe rendering on real devices.
- Dynamic AI settings: runtime switching without restart is a useful operator feature. Keep keys write-only/masked, scoped per provider, encrypted, and never reflected in API errors or logs. Add a host allowlist and a provider health panel with safe error class, timeout and latency. Test provider adapters with mocked request captures and owner-managed credentials.
- File processing: put uploads and generated files in private object storage with short-lived signed access, size quotas, malware/content checks and lifecycle deletion before horizontal scaling. Keep file conversion in isolated workers with CPU/memory/time limits.
- Database and application scaling: separate API, job queue and conversion workers; make long conversions asynchronous and idempotent; add Redis for shared rate limiting/cache/session revocation; move to managed PostgreSQL/Aurora before write contention or multi-host access; use S3 for PDFs. Add schema migrations, connection pooling, queue backpressure, observability and tested restore drills.
- For 100k users, first define concurrent upload/job rate and latency targets, then load-test realistic 2–4 job overlaps and higher concurrency. SQLite/WAL is a reasonable single-node launch configuration, not a multi-instance database architecture.

Overall architecture score: 7/10 (B−) for the local design and implementation after this pass. The score is not a readiness certification. The operational launch verdict is HOLD because production payment, mail, persistence/restore, and owner-file acceptance are incomplete.

## Live checks NOT run

No live production changes or payment actions were performed. The following checks remain outstanding because they require owner-only resources or a runtime not mounted here:

- Actual deployed volume mapping, before/after DB path/mtime/row counts across a rebuild, backup daemon schedule, off-host copy, and restore/login drill.
- Cashfree production credentials, production checkout URL and merchant identity, webhook activation, and the owner-authorized small real payment. Do not share keys in chat or in logs.
- Real reset email receipt, verified sender domain, link/password-change/login cycle, and inbox/junk placement.
- Provider-backed Brief, Summarize and Translate on the exact owner file and specified 2-/10-page test documents.
- Exact 69-page Studio delete/reload/export/reorder chain and Merge timing on the exact owner file.
- Exact owner form PDF, exact 60 MB / 759-page file, corrupted PDF and positive Aadhaar-pattern synthetic fixture.
- Nginx/Docker proxied security-header count, TLS/HSTS response and production CSP.
- Mobile browser chrome expanded/collapsed proof at 390px across all required heights/themes; other specified 390/820/1104/1440/1920 layout captures.
- Live concurrent 2–4 job run, production performance baseline, all 41 tool page SEO landings, and real-user account/cleanup review.

## Owner steps still needed

1. Before any deployment, inspect the current live Compose configuration and exact volume. On the EC2 host, run:

   docker compose config
   docker volume ls
   docker volume inspect paperplane_data
   docker inspect paperplane-app --format '{{json .Mounts}}'

   Confirm the named volume mounted at /data is the one holding the current production SQLite file. Set PAPERPLANE_DATA_VOLUME_NAME to that exact volume name in the deployment environment; do not rename/recreate it to match a default.

2. Before every deployment, run the backup script against the live database, verify a nonzero backup file and timestamp, copy it to off-host object storage, and perform a restore into an isolated scratch container/volume. Verify login and sample user/job/API-key/waitlist counts from the restored copy. Never test restore against the production volume.

3. Confirm PAPERPLANE_BACKUP_HOST_DIR resolves to durable host storage, permissions are restrictive, the daemon runs daily, retention is enforced, and an off-host copy exists. The current same-host backup does not cover host loss.

4. Configure real Cashfree production credentials in the server secret manager or protected environment, set CASHFREE_ENV=PROD, disable demo activation, and verify the merchant identity and production checkout host. Then follow Cashfree's owner flow: use a small real payment only with the owner's explicit authorization, verify the signed webhook, order row, plan entitlement, receipt, refund path, and settlement reconciliation. Do not put credentials into the report.

5. Configure a verified sender domain and production email provider. Send a reset to an owner-controlled test mailbox; verify receipt, correct HTTPS public origin, single-use/expiry, password change, and new login. Also verify OTPs/alerts are not simulated and no code is present in subjects/logs.

6. Provide the exact owner test pack in the workspace, including notes_test.pdf (5,456,746 bytes), test-form.pdf and other Appendix D files. Keep sensitive or personal identity data out of the pack. Repeat the P0 AI/Studio/Forms gates using the exact fixtures.

7. Confirm the AI provider, exact model identifiers, endpoint and quotas in the provider console. Supply credentials only through the server's secret-management path. Run Brief/Summarize/Translate on the exact files and open each downloaded result for content checks.

8. Capture the missing browser/layout evidence: 390px with chrome expanded and collapsed, heights 667/740/781/844/932 in light and dark, plus Studio at rest/scrolled at 1104 and 1920px, and Settings/developer/tool pages at the specified widths. Do not infer browser chrome state from viewport height alone.

9. Review cleanup-probe candidate rows in preview before deleting anything. Confirm protected account allowlist values and audit retention policy. Delete test accounts only after preserving required live audit evidence and confirming ownership.

## Screenshots and artifacts

All paths below are relative to reports/launch-audit-v9.

- Studio/forms/signature/handoff: screenshots/forms-add-no-file-after-fix.png; forms-add-with-file-after-fix.png; forms-add-with-file-True.png; fill-form-no-file.png; fill-form-with-file.png; signature-pad-drawn.png; signature-output-page.png; studio-3page-loaded.png; handoff-studio-page3.png; handoff-ai-context-page3.png; reorder-after-drag.png.
- Empty-input states: id76-fill-form-empty.png; id76-edit-pdf-empty.png; id76-organize-pdf-empty.png.
- Other local UI: home-1440.png; mask-debug.png.
- Mobile sidebar before/after screenshots are captured for each height 667, 740, 781, 844, and 932, in both light and dark themes:
  - Before light: mobile-sidebar-before-light-667.png, mobile-sidebar-before-light-740.png, mobile-sidebar-before-light-781.png, mobile-sidebar-before-light-844.png, mobile-sidebar-before-light-932.png.
  - Before dark: mobile-sidebar-before-dark-667.png, mobile-sidebar-before-dark-740.png, mobile-sidebar-before-dark-781.png, mobile-sidebar-before-dark-844.png, mobile-sidebar-before-dark-932.png.
  - After light: mobile-sidebar-after-light-667.png, mobile-sidebar-after-light-740.png, mobile-sidebar-after-light-781.png, mobile-sidebar-after-light-844.png, mobile-sidebar-after-light-932.png.
  - After dark: mobile-sidebar-after-dark-667.png, mobile-sidebar-after-dark-740.png, mobile-sidebar-after-dark-781.png, mobile-sidebar-after-dark-844.png, mobile-sidebar-after-dark-932.png.

Output artifacts and logs: outputs/ contains the opened PDFs, JSON, text, images, and office documents from the content audit. The full per-operation matrix is in TOOL-CONTENT-AUDIT.md. Full test logs are listed above. Reproduction evidence and pre-fix traces are in REPRODUCTION-LOG.md.

## Sources

- OWASP Top 10:2025: [Introduction](https://top10.owasp.org/2025/0x00_2025-Introduction/) and [A01 Broken Access Control](https://top10.owasp.org/2025/A01_2025-Broken_Access_Control/).
- OWASP guidance: [HTML5/Web Storage security](https://cheatsheetseries.owasp.org/cheatsheets/HTML5_Security_Cheat_Sheet.html), [Session Management](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet), and [CSRF Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html).
- Cashfree published pricing and offer terms: [Payment Gateway Charges](https://www.cashfree.com/payment-gateway-charges/).
- Razorpay published pricing: [Pricing](https://razorpay.com/pricing/).
- SQLite: [WAL](https://www.sqlite.org/wal.html), [Online Backup API](https://www.sqlite.org/backup.html), [Appropriate Uses](https://www.sqlite.org/whentouse.html), [synchronous and foreign-key PRAGMAs](https://www.sqlite.org/pragma.html).

## Working tree

All code, tests, and audit artifacts remain uncommitted on branch launch-audit-v9. No deploy, commit or push was performed.
