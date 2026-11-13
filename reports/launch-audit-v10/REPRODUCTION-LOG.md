# Paperplane launch-audit-v10 — Phase -1 Reproduction Log

Baseline: branch launch-audit-v10 at 1596e5d135637cf36183255970e3a9a11a8614d3 (no source changes at time of this log). Reproduction date: 2026-11-11 local workspace time.

No production endpoint, database, account, payment, or email provider was contacted. Local app checks used an isolated temporary database and explicitly disabled dotenv loading and provider/gateway credentials. Temporary fixture data was synthetic and stored outside the repository. No OTP, API key, password, signing private key, or credential value is recorded here.

At the initial prompt read, the referenced image directory was unavailable at the supplied Downloads path. The user later supplied `C:\Users\mdham\Downloads\paperplane-codex-prompt-v10.zip`; the archive was extracted under `reports/launch-audit-v10/inputs/` and all three images were opened and studied before any source change. No code was changed before or during this reproduction log.

**Image evidence reviewed before fixes:** `v10-translate-failure.jpg` shows `14-audit4.pdf · 3.2 KB`, Spanish selected, and the exact UI error “The translation provider timed out or could not be reached. Please retry later.” `v10-digital-signatures-fabricated.jpg` shows “Total Signatures: 3” on an unsigned-file report and a purported Paperplane “Verified Signer” with ByteRange `[0, 53816, 62010, 1705]`; the displayed byte offsets exceed the screenshot's small input size. `v10-studio-toolbar-compact.png` shows three toolbar rows at desktop width, establishing the requested compactness target.

## R1 — ID 60: resend invalidates the first sign-up code

**Steps:** Initialized an isolated scratch DB, generated two synthetic sign-up OTP records for a synthetic address, then verified each code without printing either value.

**Observed:** The first code remained valid after the second resend. Both verification calls returned a non-null payload. A first harness check used bool(payload) and appeared false because the valid payload was an empty dictionary; the assertion was corrected to payload is not None, after which the bug reproduced.

**Expected:** A resend invalidates the previous unexpired code; only the latest code can complete sign-up, and the UI explains that the prior code was replaced.

**Root cause evidence:** persistence.py:create_email_otp deletes only expired rows and comments that earlier unexpired codes remain valid; verify_email_otp accepts any unexpired row matching the submitted code.

**Discriminating test:** Two generated codes in a scratch DB; attempt the first after resend, then the second. Do not record either code. This reproduces the old-code acceptance.

## R2 — ID 1: Translate a small PDF to Spanish

**Input:** reports/launch-audit-v8/test-files/live-organize-3-1-2.pdf, 3,120 bytes, 3 pages (small local substitute; not the prompt's exact 3.2 KB file).

**Steps:** POSTed the file to the local /api/ai/translate endpoint with target language Spanish; also invoked the local queued-tool processor path. Provider variables and persisted provider configuration were empty, so no external provider request was possible or made.

**Observed:** API returned HTTP 503 in 0.044 s: “AI translation is unavailable because the Paperplane AI translation service is not configured or enabled.” The worker path returned “No text was translated. The translation service did not produce a translated PDF; please retry later.” in 0.027 s. No translated output was created.

**Expected:** A configured provider returns a translated PDF, or the endpoint reports the real upstream failure. The supplied screenshot's provider-timeout message was not reproduced because this run intentionally had no credentials and therefore made no provider call.

**Root cause evidence:** Translation availability is gated by AI configuration; with no key the endpoint exits before an upstream call. The prompt reports a live timeout, which remains a separate provider-backed reproduction.

**Discriminating test:** Repeat on the exact small and 69-page files with owner-configured provider/model, and open both translated outputs. Not run because no credentials may be used in this task.

## R3 — ID 2: Executive Brief and AI Summarize on small and 69-page PDFs

**Inputs:** Small local substitute reports/launch-audit-v8/test-files/live-organize-3-1-2.pdf, 3,120 bytes; 69-page repo substitute reports/launch-audit-v8/test-files/notes-69page.pdf, 4,980,286 bytes. The owner's exact 5.20 MB/5,456,746-byte file was not present.

**Steps:** Submitted both files to local POST /api/ai/summarize (the UI's Executive Brief and summary actions share this route), and invoked the local summarize worker path. No provider key was available or used.

**Observed:** API returned HTTP 503 with “AI provider is not configured” in 0.100 s for the small file and 0.150 s for the 69-page substitute. Both worker invocations raised ValueError “AI provider is not configured” (0.007 s and 0.079 s). No brief, summary, or output file was produced. This did not reproduce the reported size-dependent timeout because neither request reached an upstream provider.

**Expected:** Both small and 69-page files produce checked, page-grounded content; if the provider cannot handle the larger file, the UI states an honest limit or hides the feature.

**Root cause evidence:** The local path requires provider configuration; the exact upstream timeout/quota/model behavior cannot be isolated without the owner's provider configuration.

**Discriminating test:** Run both UI actions against the exact owner file and small file with the owner-configured provider, then open and compare the resulting content. Not run without credentials.

## R4 — ID 4: Cloud Import with the owner's Drive /view link

**Steps:** Submitted the previously supplied public Drive /view URL to the local /api/cloud/sync route. No credentials were supplied. This was a local application request and did not touch the Paperplane production site.

**Observed:** HTTP 400 after 12.047 s: “SSRF Protection: Could not resolve hostname: drive.google.com”. The route rewrites a /view URL to a Drive download URL before calling safe_fetch_url, but this environment could not resolve the external hostname, so it returned no file. This is different from the earlier HTML-content-type error in the supplied report and does not establish whether the download conversion works when DNS/network access is available.

**Expected:** Import the exact 1-page file or explain clearly how to use a direct-download URL. The acceptance itself says 69-page import remains partial because the only supplied link points to a 1-page file.

**Root cause/evidence:** Local hostname resolution failed inside safe_fetch_url; server.py's route contains the /view-to-download rewrite. No public-site request was made.

**Discriminating test:** Repeat locally with DNS/network available and check the returned filename, byte size, and page count; retain the 69-page limitation.

## R5 — ID 117: verify signatures on an unsigned PDF; assess Apply separately

**Inputs:** A clean 3-page, 3,120-byte local PDF and a synthetic 3,200-byte unsigned PDF made from that PDF with a trailing PDF comment containing signature-like ByteRange/Contents tokens. The second file still opened as a 3-page PDF.

**Steps:** Called security_forms_engine.verify_pdf_signatures on both local files and recorded only counts, ranges, and safe status fields.

**Observed:** The clean unsigned file returned is_signed=false and signature_count=0. The unsigned 3,200-byte marker probe returned one phantom candidate with ByteRange [0, 53816, 62010, 1705] and status TAMPERED, although the file is only 3,200 bytes and contains no signature dictionary. This reproduces the parser's raw-byte false-positive class and its out-of-bounds classification; it does not reproduce the exact screenshot's three entries or certificate subjects because the referenced screenshot/input was unavailable.

**Expected:** Parse real PDF signature dictionaries/AcroForm /Sig fields. An unsigned PDF must say “No Digital Signatures Found”; arbitrary comment or page content must not count as a signature. Out-of-bounds ranges should be reported as malformed data, not as a verified signature.

**Root cause evidence:** The isolated environment had no configured or persisted AI provider, so both requests exited before an upstream request. The owner-reported size-dependent timeout remains unverified without provider access.

**Apply Digital PKCS#7:** Not run. The signing path creates/uses private signing material; the task forbids using credential values, and no owner-provided signing test material was available. The screenshot directory was also inaccessible. Whether the UI delivers a signed PDF remains untested.

**Discriminating test:** Add unit fixtures for tokens in comments/strings and a valid AcroForm signature dictionary; use an owner-approved synthetic signing key only if the task's credential restriction is changed. Never print a private key or OTP.

## R6 — ID 113: Repair a truncated PDF

**Input:** Synthetic 539-byte PDF with a valid %PDF header and one page object, truncated before the xref table/trailer; no credentials or personal data.

**Steps:** POSTed the file to local /api/studio/repair in automatic mode; opened the returned artifact with PyMuPDF and checked the page count and a synthetic text marker.

**Observed:** The route returned HTTP 200 in 0.070 s with a 774-byte PDF. The output opened as 1 page and retained the expected text marker. The reported pre-fix validation rejection did not reproduce on baseline 1596e5d.

**Expected:** Damaged input reaches the recovery engine; only unrecoverable files are rejected with a specific explanation.

**Root cause evidence:** The current /api/studio/repair route uses save_upload_spooled rather than the strict save_pdf_upload/validate_upload path, then calls repair_pdf_advanced. The previous report's validation gate appears already changed in this baseline.

**Discriminating test:** Repeat with the exact truncated fixture once it is supplied; test both recoverable and unrecoverable damaged inputs and open each resulting file.

## R7 — ID 114: Studio document isolation, fresh upload, and Clear

**Steps:** Read the baseline restore/write/clear/logout code paths and searched server routes for account-scoped saved-Studio-document storage. No account passwords, OTPs, or login forms were used.

**Observed:** The browser uses one IndexedDB database named paperplane-local-work with global keys such as studio-pdf and studio-position; keys are not namespaced by the signed-in user. restoreStudioWorkspace reads the same global key. Logout removes authentication state but does not clear those IndexedDB records. Therefore a later account in the same browser can restore the prior account's local PDF. clearStudioPdf deletes the local PDF/position keys and unloads the document from the current page. No matching server-side saved-Studio-document endpoint was found in this baseline, so the claim that Clear also needs to delete a server copy is not established from this checkout.

**Expected:** Account B starts empty; a fresh upload always replaces restored state; Clear empties Studio, resets paging, and removes any actual server-side copy.

**Root cause evidence:** web/assets/app.js:85–110 creates and reads a global IndexedDB store; :246–270 restores the same key; :5795–5808 logout clears auth state without clearing local work; :310–345 clears browser state and unloads the current document.

**Discriminating test:** Full two-account same-browser UI test is not completed: test signup requires an email OTP flow, the auth dialogs cannot be automated by the available computer-use instructions, and no owner-provided local test mailbox was supplied. The exact screenshot bundle was also unavailable. Current evidence is a code-path reproduction, not an end-to-end account test.

## R8 — IDs 93 + 102: databases/containers and feedback write/read

**Steps:** Read-only inspection of the v10 local checkout only. Checked local application/container processes, local runtime database presence, Compose volume declaration, and Docker engine availability. No local or production feedback was submitted; no cleanup operation was invoked.

**Observed:** No local Paperplane Python process was returned. runtime_data/paperplane.sqlite3 is absent in the clean v10 worktree. Docker CLI could not reach the Docker Desktop Linux engine (missing npipe endpoint); therefore no container list or actual mount inspection was possible. docker-compose.yml maps the app's PAPERPLANE_DATA_DIR to /data and declares named volume paperplane_data:/data. That proves repository intent only. It does not prove how many production workers/containers run, that each maps the same volume, or that a feedback write is visible across them.

**Expected:** One persistent production DB path shared by all app processes, redeploy-surviving accounts, and feedback submissions immediately visible to admin after every successful POST.

**Root cause evidence:** Production process count, mounts, path/mtime/counts, cleanup audit trail, and cross-process write/read behavior require read-only access to the owner host. Standing rules prohibit touching production, so these checks were not run. Local absence of Docker also prevents a rebuild/restore test.

**Discriminating test:** Owner-side, read-only process/container/mount/DB inspection, then a controlled synthetic local or owner-approved test deployment: create a synthetic account, verify path and volume, redeploy, confirm same login; submit feedback three times and check admin after each. Do not run cleanup against real accounts.

## Phase -1 outcome

R1 and the R5 signature-parser false-positive class reproduced locally. R6's reported upload-gate failure did not reproduce; the current repair endpoint recovered the synthetic truncated file. R2/R3 provider timeouts could not be reproduced without credentials and no upstream calls were made. R4 was blocked by local DNS resolution. R7 is reproduced by the global browser-storage code path but not by a two-account UI session. R8 production database/feedback visibility is NOT TESTED under the no-production-touch rule. No code fixes were made before this log.

## Additional mobile acceptance reproduction — ID 119/125 (found during end-to-end browser verification, before this follow-up fix)

**Steps:** Started the local app with a clean Playwright mobile context at 390 × 844. Opened Studio, loaded the local synthetic two-page PDF `audit-sample.pdf`, then tapped Organize. Opened the rendered screenshot `reports/launch-audit-v10/studio-390-organize.png` and read the live element rectangles.

**Observed:** `.studio-toolbar` occupied y=64…337 (273 px high), while the Pages drawer occupied y=252…552. The two overlapped by 85 px, obscuring the lower part of the toolbar in Organize mode. `styles.css` used a fixed 252 px drawer top at the ≤600 px breakpoint; the toolbar height varies with the responsive controls. This reproduces the control-occlusion defect locally.

**Expected:** The page organizer opens below the responsive toolbar, with every Studio control visible/reachable at 390 px.

**Discriminating test:** Compare the toolbar’s bottom edge to the Pages drawer’s top edge after tapping Organize, then scroll/use the drawer. No credentials or account session were used.

**Fix status at log entry:** Not fixed yet. This reproduction is recorded before the follow-up CSS/JS change.

## Additional mobile acceptance reproduction — ID 115 feedback visibility (found during end-to-end browser verification, before this follow-up fix)

**Steps:** Opened the local Tool Desk in a fresh 390 × 844 Playwright context; waited for the feedback widget's animation-frame collision check; measured its button and the first visible tool card.

**Observed:** The button rectangle was x=330…374, y=724…768 and overlapped a tool card at x=16…374, y=610.6…829.3. The collision guard correctly set `pp-feedback-obstructed`, which made the container `visibility:hidden`; the pill did not cover card text, but was not visible to the mobile visitor. The button did not overlap the bottom navigation (nav begins at y=778). Screenshot: `reports/launch-audit-v10/home-390-feedback.png`.

**Expected:** On a 390 px first view, the pill remains visible in a safe gap, avoids tool-card text and the bottom navigation, and the widget still disappears while a dialog is open.

**Fix status at log entry:** Not fixed yet. This reproduction is recorded before the follow-up feedback-position change.

## Additional performance acceptance reproduction — ID 122 (recorded before lazy-loading change)

**Steps:** Opened the local Tool Desk in Chromium at 1920 × 1080 with a fresh context, blocked all non-local network requests, and collected navigation/resource entries plus PerformanceObserver long-task entries. Then switched to Compress, Page Organizer, Grayscale, and Excel to PDF without uploading a document.

**Observed:** Home navigation transferred 1,692,349 bytes across 19 resources; before any PDF was opened, it fetched `pdf.min.js` (320,325 bytes), `pdf-lib.min.js` (525,415 bytes), and `app.js` (316,120 bytes). DOMContentLoaded was 261 ms and load was 286 ms in this run; the initial long-task observer recorded one 101 ms task. Tool-view switches took 62–85 ms each. This establishes unnecessary PDF-engine downloads during initial Tool Desk load, despite the shell painting quickly.

**Expected:** Keep the shell responsive and defer PDF parsing/editing engines until a PDF feature needs them; preserve Studio, forms, and local-processing behavior.

**Fix status at log entry:** Not fixed yet. This reproduction is recorded before lazy loading.

## Additional retention reproduction — ID 3 (flaky immediate reload after second delete)

**Steps:** With a clean local Playwright context, loaded the repository 69-page PDF substitute, reordered pages in both directions, deleted one page, exported and reloaded the 68-page document, then deleted a second page. After the Studio page count reached 67 and the undo banner was visible, immediately reloaded and reopened Studio.

**Observed:** The page count reached 67 before reload, but the acceptance runner did not observe 67 restored after reload within 90 seconds. The same 69→68→67 sequence had passed in three earlier runs, so the persistence outcome is intermittent under this timing. The runner stopped at the restore assertion before writing a misleading final pass report.

**Expected:** Once deletion reports the new count and displays its undo state, a reload restores that same count and page order.

**Root cause evidence:** Not yet determined. The failure occurs after the pre-reload count is updated; a pending/debounced IndexedDB write is a hypothesis only. The code path and persisted record need a discriminating check.

**Discriminating test:** Repeat the delete/reload sequence while recording the scoped IndexedDB record before reload and after return to Studio; compare immediate reload with a short idle wait. No production account, credential, or owner file is used.

**Fix status at log entry:** Not fixed yet. This reproduction is recorded before investigation or code changes.

**Follow-up discrimination:** A later diagnostic against the reused local test database received HTTP 402 for a page-delete request; the page count and stored PDF blob stayed unchanged, so that request had not performed a deletion. After restarting only the local app with an empty temporary database, two delete requests returned HTTP 200; IndexedDB held the corresponding smaller PDF blobs (59,945 and 59,132 bytes), and reloads restored 68 then 67 pages. Both clean-DB restores had zero browser page errors. This does not confirm a Studio persistence defect; the earlier failed acceptance run is consistent with exhausted local guest-operation quota. No product change was made for this reproduction.

## Additional sign-up OTP reproduction — ID 60 (wrong-code message is misleading)

**Steps:** In the credential-isolated full suite, ran the local sign-up OTP lifecycle using a scratch SQLite database and synthetic inputs. Submitted an incorrect code before any resend occurred. No OTP value, password, or address was copied into this log.

**Observed:** The endpoint rejected the code, but returned wording that said it may have been replaced by a newer code. There had been no resend in this flow, so the explanation was false. The older-code invalidation behavior itself is separately covered by the two-code persistence test.

**Expected:** An arbitrary wrong or expired code gets a neutral “invalid or expired” response. A successful resend explicitly tells the user that the previous code has been invalidated.

**Root cause evidence:** `raise_invalid_otp` used the resend-specific explanation for every sign-up mismatch; the resend endpoint's success message did not say the prior code was invalidated.

**Discriminating test:** Run one signup with an incorrect code and separately resend, then verify the old code is rejected and the latest code can be used. The current local lifecycle test and R1 persistence test cover these cases without recording codes.

**Fix status at log entry:** Not fixed yet. This reproduction is recorded before the handler/UI message change.

## Phase 7 — Final A–Z outcomes

**R1 / ID 60 — FIXED locally:** The resend transaction keeps only the newest OTP. The success response now explicitly says the previous code is invalid; an arbitrary wrong signup code returns the neutral invalid/expired message. The sequential latest-only tests and resend endpoint test pass in both full-suite runs. Codes are not recorded.

**R2 / ID 1 — NOT TESTED with a real provider:** Local requests without provider configuration returned the safe unavailable response. No upstream request was made and no translated PDF was produced. Owner-configured small/69-page Spanish/Hindi translations remain open.

**R3 / ID 2 — NOT TESTED with a real provider:** Local small and 69-page requests stopped at provider configuration, before upstream inference. No brief/summary result can be claimed. The exact owner file and configured AI service were not available.

**R4 / ID 4 — PARTIAL:** The owner supplied only the viewer link that resolves to a 1-page PDF in the earlier local check; the 69-page import remains partial by the owner's instruction. The latest local DNS attempt failed before fetching. SSRF/availability handling now gives an actionable error, but the exact 69-page Drive import is not verified.

**R5 / ID 117 — FIXED locally:** The raw-byte signature regex was removed. Tests cover an unsigned PDF, a real synthetic AcroForm signature dictionary with generated in-memory test material, tampering/out-of-range handling, and the signed-PDF API output. The exact owner file and a browser download flow remain unverified.

**R6 / ID 113 — FIXED locally:** A truncated synthetic PDF with a valid header was recovered to a readable one-page file, and the local 41-tool rounds opened repair outputs. No claim is made for the exact owner-corrupted file.

**R7 / ID 114 — PARTIAL:** Browser storage is account-scoped; Clear unloads Studio, removes saved PDF and position, and a fresh upload becomes the active document. The local browser sequence passed. A two-account signup/sign-out UI test and any server-side saved-copy deletion are not tested; no server saved-Studio endpoint was found in this checkout.

**R8 / IDs 93 + 102 — NOT TESTED in production:** Compose configuration validates and expresses the named data volume/backup intent. Docker Desktop was unavailable for mount/redeploy checks. No production DB, account, cleanup, feedback submission, admin view, or cross-process read was touched.

**ID 3 retention discriminator — PASS on the local substitute:** On an empty local database, delete requests returned HTTP 200; the saved PDF blobs shrank after each mutation, and browser reload restored 68 then 67 pages. The earlier failed rerun was due to exhausted local guest-operation quota on the reused database (HTTP 402 in the diagnostic), not evidence that the local persistence write had failed. The exact owner 69-page file remains unavailable.

**IDs 115/119/122/125 — PASS in the final local browser run:** Feedback remained visible without card/navigation overlap across 390px heights 667/740/781/844/932, did not overlap Studio zoom, hid while a dialog was open, and reopened in Settings after confirmed submission. Studio Organize had zero toolbar/drawer overlap at 390px. The desktop toolbar measured 80px, two rows, 35 visible controls, and no off-screen controls. Initial transfer was 848,462 bytes with neither PDF engine fetched; PDF.js loaded on Studio use, and PDF-Lib stayed deferred until explicitly requested.

**Phase 7 required checks:** `pytest -q` passed twice consecutively (381 passed, 0 failed each; one Starlette deprecation warning in each run). The 41-tool content audit ran twice (37 completed, 3 unavailable, and one expected SSRF block per round). SEO headings matched all 41 routes in both runs. Local Compose validation, JavaScript/Python syntax, and `git diff --check` passed. Dependency audit found no known vulnerabilities across 58 requirements. No production endpoint, real payment, email provider, owner credential, commit, push, or deployment was used.
