# Paperplane — Elite Engineering Prompt v10 (launch-audit-v10)

Codex, working in Code mode on the owner's full Paperplane project folder on his PC. This is a direct edit-and-test agent task, NOT a chat report, NOT an inspection-only review. You must edit code, run it on localhost, reproduce every bug before fixing it, and verify every fix by running the feature yourself.

## Baseline (read this first)

- Site: https://paperplane.qd.je/ — testing phase, NOT deployment-ready.
- Repo: https://github.com/hammad986/paperplane-pdf — HEAD `1596e5d` ("feat(audit-v9)…", 5 commits above v8's `39f8c9b`). Live /health version `2.0.0`; feedback.js?v=1.0.0 on the homepage. app.js/styles.css still show v=3.6.8 (version strings NOT bumped — judge the build by content, not version strings).
- Tracker: 128 items — 81 open (7 P0s), 42 verified_fixed, 4 to_verify, 1 not_tested. Open P0s: IDs 1, 2, 4, 93, 98, 101, 102. (ID 101 is OWNER-HANDLED — see Standing Rules. Do not fix it.)
- This round (v10) is built from FIVE independent sources, all cross-checked against the code on `1596e5d` by Muse (independent tester/reporter):
  1. Muse's own v9 live retest (2026-11-10 22:23–23:35 IST, signed-in Pro) + own pytest (348 passed, 2 warnings, twice) + PyMuPDF content checks. Report: `paperplane-live-retest-v9-2026-11-10.md`.
  2. Tab Complete Pre-Launch Report (Nov 10, 18:55–19:50 UTC, test account muhammed.paperplane4@mail.tab.bot, Free) — sign-up resend, Pro checkout, mobile 390px, 41-tool pass, feedback widget.
  3. Tab pre-deploy review (Nov 10, 16:12 UTC onward, visitor) — 5 launch blockers re-check, admin console (blocked at owner-code step), first-time visitor pass, 24h plan.
  4. Instinct Round 5 Master Report (Nov 10–11, test account k5mmx3@mail.instinct.com, Free, 390x844 + 1920) — P1 + F1–F15, full 41-tool pass, Studio features, admin console, security probes.
  5. A parallel e2e verification round (Nov 10, 22:12–22:42 IST, signed-in Pro, 30 min) — code review + live round + admin test. Treat its findings as a THIRD-PARTY report (not Muse's own round). Where it conflicts with Muse's v9 round, the conflict is named and a discriminating test is specified.
- Three screenshots are bundled with this prompt in `paperplane-codex-prompt-v10-images/`. OPEN AND STUDY THEM before coding — they are the primary evidence for three items:
  - `v10-translate-failure.jpg` — AI Translate failing on a 3.2 KB PDF (es Spanish): "Processing failed — The translation provider timed out or could not be reached. Please retry later." (ID 1)
  - `v10-digital-signatures-fabricated.jpg` — the Digital & Visual Signatures modal reporting "TAMPERING DETECTED – FILE WAS MODIFIED, Total Signatures: 3" with Signature #1 "C=US, O=Paperplane Platform, CN=Verified Signer", ByteRange [0, 53816, 62010, 1705], and Signature #2 "Unknown / Self-Signed / INVALID" — for a 3.2 KB unsigned file. The ByteRange implies a ~62 KB file. Impossible. (ID 117)
  - `v10-studio-toolbar-compact.png` — the Advanced Studio toolbar (3 rows at 1920px). The owner wants these tools SMALLER / more compact. (ID 125)

## What was verified REAL (Muse's verdicts on the 3 new reports)

| Claim | Verdict | Evidence |
|---|---|---|
| Resend: old code still works after resend (Blocker 1) | REAL (code + live) | `create_email_otp` only deletes EXPIRED codes ("Keep earlier, unexpired codes valid during the resend overlap window"); `verify_email_otp` accepts ANY unexpired code. Tab live: code A (19:02) signed in at 19:05:36 after a resend at 19:03. v9 REGRESSED v8's cancel+message behaviour. Owner decision: resend MUST cancel the old code + clear message. (Note: Tab's pre-deploy review disagrees — it says a resend must NOT cancel the old code. This prompt implements the OWNER's decision.) |
| Cashfree PROD not configured (Blocker 2 / F1 / ID 98) | REAL (3 sources) | Muse's v9 + Tab (5 presses, same error) + Round 5 (all plans fail). No payment is possible at all. |
| Mobile 390px Profile/Settings visible (ID 100) | VERIFIED FIXED | Code: styles.css:4125–4126 now has the `100dvh` line after the `100vh` line (drawer fixed). Live: Tab signed-in 390px + visitor 390px + Round 5 (390x844) all confirm. |
| Feedback button on-screen at all sizes | REAL (appearance) | Tab (114×34 at 390; 125×38 at 820/1440) + pre-deploy review (112×34 at 390; 123×38 at 820/1440) + Muse (121×36 at 1920). BUT the OVERLAP (ID 115) and the SUBMISSION LOSS (ID 102) are separate, still-open issues. The auditors did NOT submit (except Round 5, whose feedback DID arrive — see ID 102). |
| PDF to Excel fail (Tab, single run) | REAL (flakiness, ID 106) | Muse's v9: first attempt timed out at 75%, retry passed. Same flakiness. |
| Word to PDF fail-then-pass | REAL (new bug, ID 111) | Full pass failed ("accepts at most 1 files" — it picked up the two Merge files); clean run passed. Cross-tool file state leaks. |
| 14 tools "READY ONLY" (Tab) | NOT a product gap | All 14 were VERIFIED by Muse's v9 round with filenames/sizes. The auditor only confirmed the result banner, not the file. |
| 4 AI tools "No change made" (Tab) | INVALID TEST | The auditor ran them with NO input (no question for Chat, no language for Translate). Muse's v9 round stands: Chat ✓, Smart Metadata ✓, Summarize ✗, Translate ✗. |
| Digital Signatures fabricated (F4 / ID 117) | REAL (code + screenshot) | `verify_pdf_signatures` (security_forms_engine.py) regex-searches raw bytes for /ByteRange and /Contents instead of parsing real signature dictionaries. Phantom signatures; out-of-bounds ByteRange → TAMPERED. Screenshot confirms. |
| Studio stale doc + Clear does nothing (F5 / ID 114) | REAL (code + live) | Restore is browser-storage keyed (not account-scoped); `clearStudioPdf` only removes the browser copy (app.js:310), not the server-side saved doc; fresh upload doesn't replace the restored doc. |
| Repair rejects damaged files (F6 / ID 113) | REAL (code + live) | `save_pdf_upload` → `validate_upload` raises "damaged or unreadable" (server.py:1765) BEFORE `repair_pdf` ever sees the file. The upload gate rejects the exact files Repair is meant to fix. |
| 24h deletion claim vs saved docs (F7 / ID 109) | REAL | Saved Studio/AI docs persist for days; the 24h purge covers tool job outputs, not saved docs. (Conflicts with retention ID 3 — fix is likely the copy + a defined retention.) |
| Sanitize no feedback (F8 / ID 116) | REAL | Button is wired in code (toast + download) but the auditor saw no message/output/change. Needs a retest + a summary + download. |
| HTML-to-PDF SSRF (F9 / ID 112) | GUARD EXISTS — verify only | `html_to_pdf` calls `is_safe_url()`; `safe_fetch_url` blocks private/loopback/link-local/metadata + validates redirects. Needs tests + a live check, not a code fix. |
| Feedback pill overlaps mobile (F10 / ID 115) | REAL | Covers tool-card text (mobile Tool Desk), the Studio zoom control, floats over modals. The button being on-screen is fine; the OVERLAP is the bug. |
| /api-docs public (F11 / ID 108) | REAL | Returns 200 to anyone, no login. (Duplicate-headers half = ID 81, already open.) |
| Password-reset emails (F2 / ID 97) | REAL (live + code) | Round 5 live: no reset email in 15+ min while OTP arrived in ~5s. Code: `send_password_reset_email` now uses allow_simulated=False — the simulation is fixed, but delivery still fails live. The break is in the actual send path. |
| Accounts disappear (P1 / ID 93) | REAL, strengthened | Selective deletion (Nov 10 accounts gone, Oct 31–Nov 1 survive). New suspect: Clean Test Probes patterns match %@mail.instinct.com, %@sharklasers.com, %@mail.tab.bot, %@example.com, %probe% — k5mmx3, ptvviosq, all probe/tab accounts match. The cleanup requires preview + explicit confirm, so it only deletes if someone confirmed it. The divergent-DB mechanism is still open. Codex must determine which. |
| Feedback loss intermittent (ID 102) | REAL, refined | Round 5's test feedback DID arrive in admin; Muse's did not. So the loss is INTERMITTENT (write/read hit different DBs depending on which process handles the request). Same defect as ID 93. |
| AI Summarize/Brief work on small files (ID 2 nuance) | REAL | Round 5: 3.2 KB file produced an executive brief + citations. Muse's v9: 69-page times out. File-size-dependent. |
| Studio Export conflict (ID 49) | CONTESTED | Muse's v9: VERIFIED (68-page export, content-checked). The e2e round: PARTIAL (2 attempts, silent return, no download). The export is flaky under some conditions. Acceptance: Export must succeed twice on the 69-page file. |
| Drag reorder conflict (ID 47) | CONTESTED | Muse's v9: drag BROKEN (no-op, confirmed after reload + export). The e2e round: drag VERIFIED (page 4 above page 3, canvas showed Preface). Needs a discriminating third check (both directions + reload + export). |
| Greeting proactive vs reply (ID 35) | NUANCE | The reply works (verified_fixed). The PROACTIVE greeting is missing (panel empty with a doc loaded). Separate minor gap. |
| Admin XFF spoof (e2e 104 / ID 118) | REAL (code) | `ProxyHeadersMiddleware, trusted_hosts="*"` (server.py:282). Lockout is per-IP; `/api/admin/auth/status` is an unauthenticated lockout oracle. NOT live-probed. |
| Admin secret code default (ID 101) | OWNER-HANDLED — EXCLUDED | The owner is making the repo PRIVATE. Do NOT change the admin code or its default in this round. (Muse's note: the value was already public in the pushed commits, so rotation is still recommended — but that is the owner's call, not Codex's task.) |

## Standing Rules

- Work in a local branch named `launch-audit-v10`. Do NOT commit, push, or deploy. Do NOT touch the production server. Do NOT make any real payment. Do NOT use any real user's account or data.
- No credential values, OTP codes, API keys, or test passwords in any file you write (reports, logs, code comments, test fixtures). Use placeholder values only.
- For every item: report FIXED, PARTIAL, or NOT TESTED — with WHY, HOW you tested it, and PROOF (file names, sizes, page counts, exact observed text, screenshots where the item is visual). A banner or toast alone is never proof. A fix is only FIXED when the feature works end to end on the real file, twice in a row.
- Run the full test suite TWICE consecutively at the end. Both runs must pass with 0 failures. Report both run times and counts.
- Pricing ground truth (INR only, no USD in the UI): Free ₹0, Exam ₹19/24 hours, Student ₹49/month or ₹399/year, Pro ₹250/month or ₹999/year, Cyber Café ₹299/month, Developer ₹750/month.
- Owner decisions (settled — do not re-litigate): Compress default "Under 100 KB Govt/SSC" is intended. Continuous Studio scrolling is a launch MUST. Pricing UI is INR-only. Tool Desk is a REAL view. Reload retention with a Clear control. PAGES panel toggle on laptop + mobile. The admin secret code is OWNER-HANDLED (repo goes private) — do NOT change it or its default. The resend rule: a resend MUST invalidate the previous code + the UI must say so clearly. The feedback button (ID 128): dismissible; shown to first-time users on login/signup; after a confirmed submission it hides from the UI and lives only in Settings. The Studio toolbar (ID 125): make the tools smaller / more compact (see the screenshot).

## Phase -1 — ANALYSE FIRST (mandatory, before any fix)

Write `reports/launch-audit-v10/REPRODUCTION-LOG.md`. For each reproduction below, record: the exact steps, the exact observed result (with file names/sizes/error text), and whether it reproduces. Do NOT fix anything until the log is written. If a reproduction does NOT reproduce, say so explicitly with the evidence — do not mark it FIXED on the basis of code reading alone.

- R1 (ID 60): register a test account; request a resend; try the FIRST code. Does it still sign in? (Expected on v9: yes — the bug.)
- R2 (ID 1): translate a small PDF (3.2 KB) to Spanish. Record the exact error + time.
- R3 (ID 2): run Executive Brief + AI Summarize on the 69-page notes file AND on a 3.2 KB file. Record both results + times.
- R4 (ID 4): Cloud Import with the owner's Drive /view link. Record the exact error.
- R5 (ID 117): upload a small UNSIGNED PDF; open Digital & Visual Signatures → Verify Signatures. Record the exact report (count, ByteRanges, subjects). Then Apply Digital PKCS#7. Record whether a downloadable signed PDF appears.
- R6 (ID 113): create a truncated PDF (valid header, missing xref/trailer); run Repair. Record the exact error.
- R7 (ID 114): in a fresh browser profile, create account A, open a document in Studio, sign out, create account B, open Studio. Does B see A's document? Then click Clear Studio PDF. Does the document unload?
- R8 (IDs 93 + 102): check how many app processes/containers run, whether /data is mounted in every one, the DB file's path/mtime/row-counts, and whether a write from one process is visible to another. (Read-only inspection; do not modify server state.)

## Phase 0 — Launch blockers (fix in this order)

### 0.1 IDs 93 + 102 — Persistence / divergent databases (the #1 blocker)

The live write and the live read hit different databases (feedback submissions vanish intermittently; accounts disappear selectively on redeploy). The repo's compose file has a named volume (`paperplane_data:/data`) and the deploy only does `git pull` + `docker compose up -d --build` — so the live setup must differ from the repo, OR more than one app process/DB is running.

Determine the mechanism: (a) check the server's audit logs for `admin_cleanup_probes` calls (did anyone run Clean Test Probes?); (b) check how many app containers/processes run, whether /data is mounted in every one, the DB file's actual path + mtime + row-counts; (c) verify a write from one process is visible to another.

Fix BOTH candidate mechanisms: (i) make the DB persistent (one mounted volume, verified by a redeploy-survival test: create an account → redeploy → log in again with the same account); (ii) narrow the Clean Test Probes matching rule (`_admin_probe_candidates`) to explicit test markers only — the current patterns (`%@mail.instinct.com`, `%@sharklasers.com`, `%@mail.tab.bot`, `%@example.com`, `%probe%`) are too broad (they match any account on those domains) — and the preview must show the EXACT emails before any confirm.

Acceptance: the redeploy-survival test passes; a feedback submission is visible in admin every time (submit 3 times, check admin after each); the Clean Test Probes preview shows exact emails and deletes only confirmed IDs.

### 0.2 ID 98 — Cashfree PROD (nobody can pay)

Checkout fails fast: "Live payments are disabled because Cashfree is not configured for PROD in this production environment." The sandbox checkout is closed AND prod is not configured — no payment is possible at all.

Implement the env split: `CASHFREE_ENV=sandbox` with sandbox keys on the test deployment; live keys from env vars in production. The prod checkout must return 503 (not a sandbox page) when `CASHFREE_ENV != PROD`, and the invalid-`CASHFREE_ENV` fail-open (silently coerced back to TEST) must be removed — fail loudly in logs and show a graceful "payments temporarily unavailable" message instead of a raw config error.

Close the demo/free-activation path (server.py:3453) so it cannot grant a plan without payment in production. Verify it is closed.

Acceptance: the checkout flow reaches a payment page (sandbox on the test deployment, live keys in prod). The owner will run one small REAL payment himself after this round — Codex must NOT run a real payment. Report exactly what the owner must do (keys to set, the one payment to run, the refund).

### 0.3 IDs 1 + 2 — AI provider (Translate + Brief/Summarize)

Translate (ID 1): the provider times out on every run ("The translation provider timed out or could not be reached"). See the screenshot `v10-translate-failure.jpg`. Check the translation provider config (API key, base URL, model name, timeout), add a startup health check, and surface a clear admin-side alert when the provider is unreachable.

Brief/Summarize (ID 2): time out on the 69-page document (~90–120s) but WORK on small files (3.2 KB). The failure is file-size-dependent. Fix the provider timeout/limits (or the chunking for large documents); if the provider cannot handle 69 pages, scope the feature honestly to a page limit and say so in the UI.

Acceptance: Translate produces a translated PDF (test EN→Spanish AND EN→Hindi, on a small file AND the 69-page file). Brief/Summarize produce output on BOTH a small file AND the 69-page file. If any of these cannot be fixed, hide the card until it works (a red failure on launch day is worse than no card).

### 0.4 ID 4 — Cloud Import (SSRF error on the owner's Drive link)

The owner's exact Drive /view share link returns the SSRF error ("Cloud Import accepts PDF files only. This link returned another file type...") because a /view link returns an HTML page, not a PDF.

Fix the import to handle Google Drive /view links (fetch the actual file via the Drive download URL) OR give a clear, correct error telling the user to use a direct download link. Test with the owner's exact link AND with a direct PDF URL.

Acceptance: the owner's link imports the file (or the error correctly explains what to do). The 69-page Drive import remains PARTIAL by definition (the link resolves to a 1-page file, not the 69-page file — there is no other link).

### 0.5 ID 60 — Sign-up resend must cancel the old code (owner decision)

v9 REGRESSED this: `create_email_otp` (persistence.py) now only deletes EXPIRED codes ("Keep earlier, unexpired codes valid during the resend overlap window") and `verify_email_otp` accepts ANY unexpired code. Live proof: code A (19:02) signed in at 19:05:36 after a resend at 19:03.

Remove the overlap window. A resend MUST invalidate the previous code. The UI must say so clearly (restore the v8 message: "This code may have been replaced by a newer one. Use the latest email, or wait for the resend timer and request another code.").

Acceptance: request a resend, then try the FIRST code — it must be refused with the clear message; the SECOND (latest) code must sign in. Run this twice on two fresh test accounts.

### 0.6 ID 97 — Password-reset emails never arrive

Live: no reset email in 15+ minutes while the OTP code arrived in ~5s (Round 5, Nov 10 21:22 IST). Code: `send_password_reset_email` now uses allow_simulated=False (email_service.py:432) — the simulation flag is fixed, but delivery still fails live. So the break is in the actual send path.

Trace the reset-mail path (compare it with the OTP send code, check the mail queue/logs, verify the reset template and recipient handling). Prove delivery end to end (send a reset to a test account and confirm it arrives).

Acceptance: a reset email arrives within a minute, like OTP codes do.

### 0.7 New P1s (fix in this round)

- ID 117 Digital Signatures: `verify_pdf_signatures` (security_forms_engine.py) must parse REAL signature dictionaries (AcroForm /Sig fields via a proper PDF parser) — NEVER regex over raw bytes for /ByteRange and /Contents. An unsigned file must say "No Digital Signatures Found". An out-of-bounds ByteRange is corrupt/unparseable data, not a counted signature. Apply Digital PKCS#7 must return a downloadable signed PDF + a clear success/error message. See the screenshot `v10-digital-signatures-fabricated.jpg`. Test: an unsigned 3.2 KB PDF (must say "No signatures"), a genuinely signed PDF (must parse its real ByteRange + certificate), and Apply (must produce a downloadable signed PDF).
- ID 114 Studio stale doc + Clear: the restore must be scoped to the signed-in account (a new account opens empty); a fresh upload must ALWAYS replace the restored document; Clear Studio PDF must unload the document AND delete both the browser copy and the server-side saved copy, and reset the pager. Test with two accounts in the same browser (R7).
- ID 113 Repair: the Repair operation must bypass/relax the strict upload validation — `save_pdf_upload` → `validate_upload` (server.py:1745/1765) rejects damaged files before `repair_pdf` ever sees them. Accept the damaged file, hand it to `repair_pdf` (which tries PyMuPDF + pypdf recovery), and only reject if repair cannot recover any readable page (with a specific reason). Test with a truncated PDF (valid header, missing xref/trailer) — it must produce a repaired file or a specific "unrecoverable because ..." message.
- ID 118 Admin XFF: trust X-Forwarded-For ONLY from the known reverse proxy (set `trusted_hosts` to the proxy's IP in server.py:282), or use the direct connection IP. `/api/admin/auth/status` (server.py:7564) must not reveal another IP's lockout state. Do NOT live-probe the lockout (it risks a 24h lockout) — verify by code + unit tests.
- ID 110 SEO off-by-one: `syncSeoContent` (app.js ~1458) must clear the old SEO block before loading the new one. Verify the correct heading on all 41 tool pages (two consecutive runs).

## Phase 1 — AI

- ID 99 AI Chat gating: REGRESSION-CHECK only (verified fixed in v9 — the chat uses the attached document without the phrase). Re-run the exact discriminating questions ("What word is written on page two?" without the phrase) on a small file and confirm a grounded answer with a Page 2 citation.
- ID 35 Greetings: the REPLY is verified fixed. Add the missing PROACTIVE greeting: when a document loads, the AI Chat panel must show a greeting + suggested questions (do not leave the panel empty).
- IDs 5/6/12 (AI Docs polish), ID 34 (AI layout during Brief — CONFLICTING observation, needs a third check): fix per the tracker detail; verify before/after upload and processing at 1920px and 390px.

## Phase 2 — Auth / UX / copy / legal

- ID 64 Forms Add Field: the button + toast work, but the added field is NOT in the exported PDF (Muse's v9 content check) — the field must survive into the export, and the Inspect & Fill tab must refresh to show it. (Round 5 confirms the UI works: a Text Box was added, count 3→4, listed in Inspect & Fill.)
- ID 68 Drawn signature: REGRESSION-CHECK only (verified fixed in v9 with content proof — the drawn signature renders as an image in the export).
- IDs 69 + 92 (Clear Studio / New Page): the New Page action must confirm before discarding, and must not persist a zero-byte blank document.
- IDs 74/46/79 (Terms/Billing/History): per the tracker detail.
- ID 128 Feedback button (owner decision): add a close (X) control (dismissed state persists); show the pill to first-time users on login/signup; after a CONFIRMED feedback submission, hide the pill from the main UI and expose feedback only via Settings. The hide logic must key on a server-confirmed submission (or a durable local flag after a successful submit) — NOT on a submission the server never recorded (see ID 102).

## Phase 3 — Studio

- ID 47 Reorder drag: DISCRIMINATING TEST REQUIRED. Muse's v9 round: drag page 1→2 was a no-op (confirmed after reload + export). The e2e round: drag page 4 above page 3 worked (canvas showed Preface). Test BOTH directions (page 1→2 AND page 4→3), confirm after a full reload AND in the exported PDF (page order byte-checked). Fix whichever direction fails.
- ID 49 Studio Export: REGRESSION-CHECK with a stricter bar (CONFLICT: Muse's v9 verified a 68-page export with content proof; the e2e round got a silent return with no download on 2 attempts). Export must produce a verified download TWICE on the 69-page file (after a delete + a reorder), with the page count checked.
- ID 3 Studio retention: REGRESSION-CHECK only (verified fixed in v9: 69→68→67 across reloads).
- IDs 53/45/15 (Studio scroll header / footer / pill nav overlap), IDs 13/43 (Studio layout), IDs 10/11 (Studio panels): per the tracker detail; verify at rest AND scrolled, at 1920px and 1104px.
- ID 114 (stale doc / Clear): see Phase 0.7.
- ID 115 Sanitize: after sanitizing, show a summary of what was stripped (metadata keys removed, annotations purged, JS neutralized) and offer the cleaned file as a download; if the call fails, show the error (never silence).
- ID 125 Studio toolbar smaller (owner decision): reduce the toolbar/tool button size and padding so the tools take less vertical space. See the screenshot `v10-studio-toolbar-compact.png` (3 rows at 1920px). Verify at 1920px and 390px that all controls remain reachable and legible.
- ID 119 Organize on mobile: the Studio Organize button must open the page organizer as a bottom sheet or full-screen view on a 390px viewport.
- ID 121 Security modal entry: add an entry point to the security Audit/Sanitize modal from the standalone /protect-pdf and /unlock-pdf pages.
- Studio → AI Docs handoff: the Studio document must carry into AI Docs (and not revert to a stale document after navigation).

## Phase 4 — Layout / mobile / SEO

- ID 100 Drawer: REGRESSION-CHECK only (verified fixed in v10 — the 100dvh line is now in styles.css:4126 and three reports confirm Profile + Settings visible at 390px). Re-verify at 390px, heights 667/740/781/844/932, light + dark, with the browser chrome shown AND hidden.
- ID 115 Feedback pill overlap: the pill must not cover tool-card text (mobile Tool Desk) or the Studio zoom control, must sit below modal overlays (z-index), must shrink to icon-only under 480px, must respect the safe-area bottom offset, and must hide while any dialog is open. (The button being on-screen at all sizes is already fine.)
- ID 110 SEO: see Phase 0.7.
- IDs 55/52/50/16/51/54/77/80/85/86/87/62/73 (layout): per the tracker detail; verify at 390/820/1440px, light + dark. ID 54: also add the redirects from Phase 5 (ID 127).
- Student suffixes (.res.in/.univ/.college/.school — non-standard) + Compress typos: fix per the tracker detail.

## Phase 5 — Tools / content / security

- The 41-tool output-content audit TWICE: run every tool on a real file, open every output, and verify the content (not just the banner). Record file name + size + page count/content for each. (Nobody has completed this twice end to end — it is a launch requirement.)
- ID 113 Repair: see Phase 0.7.
- ID 111 Word to PDF carryover: each tool page must start with an EMPTY uploader (clear any files carried over from a previous tool). Test: run Merge with 2 files, then open Word to PDF — it must show an empty uploader, not the Merge files.
- ID 70 Page Organizer: the textbox order works (4,3,2,1 produced correct output) but there are still no visual reorder controls — add a thumbnail grid with drag-and-drop (and up/down arrows as fallback on touch), keeping the text field as an advanced option. Verify the output page order by content.
- ID 75 Compare: verify the diff body content live (not just the file existing) — the temp-filename leak was code-fixed; confirm the diff shows real file names and real differences.
- ID 95 Smart Metadata export + ID 96 Fill Form on a real form: REGRESSION-CHECK only (verified fixed in v9).
- ID 105 Smart Metadata date: the document_date must be a real date, not a section number ("3.3.1"); the topics must be real topics, not header fragments.
- ID 121 Sign draw pad: add the draw/type signature pad to the /sign-pdf tool page, or change the card copy to say signatures are placed in Studio.
- ID 123 Local downloads: local-mode results (Merge/Split/Rotate) must show the file name, size, and a re-download link, like server-mode results.
- ID 124 Copy nits: fix all 9 grouped nits (Merge "one file per run", HTML-to-PDF "PDF files", Merge "200 MB" vs "50/500 MB", Protect one field, pricing current-plan marker, AI Chat raw ** markdown, size 5.26 vs 5.20 MB, Unlock "incorrect password", Scan-to-PDF hidden inputs).
- ID 127 Tool cards as links: render tool cards as real anchor (a href) links (crawlable/shareable); add redirects (/scan-pdf → /scan-to-pdf, /tools → /); consider a sitemap.
- ID 108 /api-docs: disable /api-docs and /redoc in production (docs_url=None, redoc_url=None, openapi_url=None) or gate them behind admin auth.
- ID 112 HTML SSRF: ADD TESTS proving the fetcher blocks private/loopback/link-local/cloud-metadata IPs, redirects into those ranges, and non-http(s) schemes. The guard exists in code (`is_safe_url` + `safe_fetch_url`) — prove it with tests and a live check.
- ID 81 Duplicate security headers: set each header in ONE layer only (nginx-only, per the e2e report). Verify with a non-proxied curl (the earlier observations went through a proxy).
- ID 118 XFF: see Phase 0.7.
- ID 122 Performance: profile main-thread JS on the home grid and the heaviest tool pages (compress, organize, grayscale, excel-to-pdf, Studio export); reduce first-load work (lazy-load, code-split, defer non-critical JS). The tabs froze 5+ times during testing.
- ID 120 /admin HEAD 405: confirm it is proxy-only (not a stale build) and make HEAD behave like GET (or document it as proxy behavior).
- IDs 8/9/14/41/90 (sweep): per the tracker detail.

## Phase 6 — Do NOT regress (verify these still work)

- The v9 verified fixes: Studio retention (ID 3), Studio Export (ID 49), drawn signature (ID 68), greetings reply (ID 35), AI Chat gating (ID 99), empty-field Run-disable (ID 76), Smart Metadata export (ID 95), Fill Form on a real form (ID 96), Annotate (content-verified), Merge (merged-PDF.pdf), More Tools dropdown, PAGES toggle, Terms §4, /settings 200, the v8 security P0s (register-no-OTP → otp_required + no cookie; 6th wrong OTP → 429 + Retry-After 900; anonymous job downloads → 404; cross-user downloads → 404).
- The v10 verified fix: the mobile drawer (ID 100, 100dvh).
- The full 41-tool regression sweep (pipeline-level, with the output-content audit from Phase 5 as the content bar).

## Phase 7 — Final A–Z protocol

- Run the full test suite TWICE consecutively. Both runs must pass with 0 failures. Report both run times and counts.
- Re-run the Phase -1 reproductions (R1–R8) and confirm each is fixed (or explicitly NOT TESTED with a reason).
- Write `reports/launch-audit-v10/FINAL-REPORT.md` using the Appendix C template. Give a verdict: READY or HOLD, with the exact remaining gaps if HOLD.
- Write `reports/launch-audit-v10/TOOL-CONTENT-AUDIT.md` (the 41-tool content audit, twice).
- Do NOT commit, push, or deploy. Leave everything uncommitted on the local branch `launch-audit-v10`.

## Appendix A — Evidence Map

- Muse v9 live retest: `paperplane-live-retest-v9-2026-11-10.md` (tracker 107 items at that time; verdict NOT deployment-ready).
- Tab Complete Pre-Launch Report (Nov 10, 18:55–19:50 UTC): sign-up resend (Blocker 1), Pro checkout (Blocker 2), mobile 390px (fixed), 41-tool pass (20 pass with file, 14 ready-only, PDF to Excel fail, 4 AI unclear), feedback widget (fixed, not submitted). It asks for a 3rd sign-in code to finish — NOT needed for coverage (see Appendix E).
- Tab pre-deploy review (Nov 10, 16:12 UTC): 5 launch blockers re-check (Chat fixed, empty-field fixed, Translate still broken, resend + checkout not re-run), admin console (blocked at owner-code step — one wrong OTP entered, 2 attempts remain), visitor pass (390/820/1440, light + dark), 24h plan.
- Instinct Round 5 Master Report (Nov 10–11): P1 (accounts disappear) + F1–F15 (Cashfree, reset emails, Translate, Digital Signatures, Studio stale/Clear, Repair, 24h claim, Sanitize, SSRF, feedback pill, /api-docs, helper texts, Organizer/Sign UI, tool cards/links, misc). Full 41-tool pass: 40 pass, 1 fail (Translate).
- Parallel e2e verification (Nov 10, 22:12–22:42 IST): code review + live round + admin test. Its suggested tracker items 102–115 use ITS numbering — DO NOT USE those numbers (Muse's tracker already uses 102–107 for different items; the v10 items are 108–128). Conflicts with Muse's v9 round are named in Phase 0/3 (Export, drag reorder, greeting).
- Screenshots bundled with this prompt: `v10-translate-failure.jpg` (ID 1), `v10-digital-signatures-fabricated.jpg` (ID 117), `v10-studio-toolbar-compact.png` (ID 125).

## Appendix B — Acceptance table (all must be true for READY)

| # | Gate | IDs | How to prove it |
|---|---|---|---|
| 1 | Persistence proven live (redeploy survival + feedback write/read visible every time + Clean Test Probes narrowed) | 93, 102 | Create an account → redeploy → log in again; submit feedback 3 times, check admin after each; preview shows exact emails |
| 2 | Cashfree PROD verified live (checkout reaches a payment page; demo path closed) | 98 | Sandbox page on test deployment; owner runs one small REAL payment after this round (Codex must NOT) |
| 3 | Translate produces a translated PDF (small + 69-page, EN→Spanish AND EN→Hindi) | 1 | Translated PDF opened + checked, both sizes, both languages |
| 4 | Brief/Summarize produce output on BOTH a small file AND the 69-page file | 2 | Output returned + checked, both sizes |
| 5 | Cloud Import works with the owner's Drive link (or the error correctly explains what to do) | 4 | The owner's exact link imports the file |
| 6 | Resend cancels the old code + clear message; latest code signs in (twice, two fresh accounts) | 60 | First code refused with the message; second code signs in |
| 7 | Password-reset email arrives within a minute | 97 | Reset sent to a test account; email received |
| 8 | Digital Signatures parses real signature dictionaries; unsigned file says "No signatures"; Apply returns a downloadable signed PDF | 117 | Unsigned 3.2 KB PDF → "No signatures"; signed PDF → real ByteRange + cert; Apply → downloadable file |
| 9 | Studio: new account opens empty; fresh upload always wins; Clear deletes both copies; drag reorder verified by reload + export | 114, 47 | Two-account test (R7); drag both directions + reload + export byte-check |
| 10 | Repair fixes a genuinely damaged file (truncated xref) | 113 | Truncated PDF → repaired file with readable pages |
| 11 | Admin lockout not bypassable via X-Forwarded-For (code + unit tests; no live probe) | 118 | `trusted_hosts` restricted to the proxy; auth/status does not leak another IP's state |
| 12 | SEO headings correct on all 41 tool pages (two consecutive runs) | 110 | Heading matches the tool on every page |
| 13 | Studio Export produces a verified download TWICE on the 69-page file (after delete + reorder) | 49 | Two exports, page counts checked |
| 14 | No first-attempt 502s / 75% stalls / silent first-attempt failures | 106 | First attempts succeed on Remove Pages, PDF to Text, Sign, PDF to Excel, Metadata, Studio Delete/Duplicate |
| 15 | Mobile 390px verified (owner's phone half) + feedback pill does not overlap + Organize works on mobile | 100, 115, 119 | Owner's phone checklist; pill below modals, icon-only under 480px; Organize opens as a sheet |
| 16 | Full suite passes TWICE, 0 failures; FINAL-REPORT.md written | — | Two run logs with counts + times |

## Appendix C — FINAL-REPORT.md template

```
# Paperplane — Launch Audit v10 — FINAL REPORT
Build: HEAD <hash> (local branch launch-audit-v10) | Date: <date> | Verdict: READY / HOLD
Suite: <count> passed, <count> failed — run 1 (<time>), run 2 (<time>)
## Per-item status (one line each, with proof)
- ID <n> <title>: FIXED / PARTIAL / NOT TESTED — WHY + HOW + PROOF
## Reproductions (R1–R8): before → after
## 41-tool content audit: <summary> (full table in TOOL-CONTENT-AUDIT.md)
## Remaining gaps (if HOLD): <exact list>
## Owner-only items: <what the owner must do>
```

## Appendix D — Test files

- The 69-page notes file (5.20 MB, 69 pages, real text) — the main regression file. Also a small 3.2 KB PDF (for the size-dependent AI tests), a 10-page text PDF (with a redaction keyword on page 4), a real AcroForm PDF (Name/Email/City fields), a password-protected PDF, a corrupted PDF, a .docx, a .xlsx, a .pptx, a .jpg, and a synthetic Aadhaar-pattern PDF (marked "not a real ID" — never reproduce the sample number).
- The owner's Drive link for Cloud Import (the only link; it resolves to a 1-page file, not the 69-page file — the 69-page import is PARTIAL by definition).

## Appendix E — Owner-only items (NOT Codex's job)

- Admin secret code (ID 101): EXCLUDED from this prompt. The owner is making the repo PRIVATE. Codex must NOT change the admin code or its default. (Muse's note: the value was already public in the pushed commits, so rotation is still recommended — the owner's call.)
- Cashfree PROD keys + one small REAL payment test (ID 98): the owner sets the keys and runs the payment himself after this round; Codex prepares everything else.
- The 3rd sign-in code Tab asked for: NOT needed for coverage — the 14 "READY ONLY" tools were already verified by Muse's v9 round with filenames/sizes, and the 4 AI "no output" results were an invalid test (no input given). The owner decides whether to approve it anyway.
- Deleting the 3 QA feedback entries + the paperplane3 account from the live site: the auditor asked for permission. The owner decides (the feedback rows can be deleted from the admin console; the account needs the server-side SQL route — there is no delete-account option in the site).
- Probe/test account cleanup (owner's job, after this round's verification): the 9 auditor probe accounts, the waitlist test row, the v8 probe OTP row, the Tab accounts re-created Nov 10, the fresh-account Pro/Developer test account (ptvviosq@sharklasers.com), and the Round 5 test account (k5mmx3@mail.instinct.com).
- The Studio document in the owner's Pro account is the modified 67-page file (pages 1–2 swapped, signature mark, added form field) — reload the original 69-page file when wanted.
- Mobile 390px + console errors: the owner's phone half (his checklist). Muse's browser cannot set a phone viewport.
