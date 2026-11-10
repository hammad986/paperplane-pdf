# Paperplane launch-audit-v9 — Phase -1 Reproduction Log

Branch: `launch-audit-v9` at `39f8c9bcb11b25f6671e53d5c3208a7d5fac3fcb` (v8). Captures here were made before source changes. This log separates independently reproduced local behavior from owner-supplied live evidence and checks blocked by missing fixtures or production access.

## Environment and safety

- The branch worktree was clean before testing. No production endpoint was called, no payment was attempted, and no production database was changed.
- Docker CLI is installed, but Docker Engine is unavailable (`docker ps` reports that the Docker Desktop Linux engine pipe does not exist). Container rebuild, compose health endpoint, backup daemon, and volume restore cannot be exercised here.
- No `.env` exists in this worktree. Cashfree app/secret, Gemini, OpenAI, Bluesminds, Resend, SMTP, and public URL configuration are absent. No key or credential value was emitted.
- The owner-specified `notes_test.pdf` (5,456,746 bytes), `test-form.pdf`, and test-pack README were not found in the expected external locations. A repository copy `reports/launch-audit-v8/test-files/notes-69page.pdf` is available (4,980,286 bytes, 69 pages); a repository form PDF is available (2,253 bytes, one page, three widgets). These are useful local substitutes, not proof on the owner's exact fixtures.
- R1, R2, R5, R6, and R7 used fresh synthetic identities and temporary local SQLite databases. API key values and test passwords were not printed or written to this report.

## Phase -1: required R1–R7 probes

### R1 / ID 93 — account and volume persistence across redeploy

- **Observed:** A fresh user, password-authenticated login, job row, waitlist row, and API-key row all survived a Python process exit/restart against the same isolated `PAPERPLANE_DATA_DIR`: `login_ok=true`, `user_row=true`, `jobs=1`, `api_keys=1`, `api_key_auth=true`, `waitlist_rows=1`. A Docker rebuild was not possible because the Docker engine is unavailable. The owner-supplied live report says the earlier accounts disappeared after the v8 deploy; that server-side observation was not independently reproduced.
- **Expected:** User login, jobs, waitlist, and API-key authentication survive the deploy command and the production volume remains mounted.
- **Suspected root cause:** The repository compose file declares named volume `paperplane_data:/data` (`docker-compose.yml`, `paperplane` service) and the deploy workflow runs `docker compose up -d --build` (`.github/workflows/deploy.yml`). The backup daemon also writes under `DATA_DIR/backups` (`scripts/backup_db.py:42-69`), inside the same mounted data path. The mismatch between the live loss report and repository configuration cannot be reconciled without owner-side host evidence; a compose project/volume mismatch or live deployment using a different data path remains possible.
- **Fix plan:** Add startup and persistence-health diagnostics for resolved DB path, file metadata, row counts, and mounted-volume indication; configure backups to an independent host path; document an owner-side before/after volume check and scratch restore.
- **Discriminating test:** On Docker-capable host, create a fresh account and associated job, waitlist row, and API key; run the exact compose rebuild; authenticate again and verify all four rows. Back up to a separate mount, restore into a scratch container, and log in there. Owner runs this against the live host; Codex does not SSH.

### R2 / ID 98 — Cashfree checkout and free activation path

- **Observed:** With no Cashfree credentials, the local development configuration (`ENVIRONMENT=development`, simulation enabled) returned `mode=demo_activated`, `environment=TEST`, and changed a synthetic account to `tier=pro`. Repeating the no-credential route under production mode with simulation disabled returned HTTP 503 and left the synthetic account `free`. No Cashfree checkout or simulated-card flow was opened.
- **Expected:** No paid tier activates without verified payment; production checkout uses Cashfree PROD and the owner's real merchant identity.
- **Suspected root cause:** The development-only branch is in `server.py:3445-3461`; it is gated by `ENVIRONMENT` and `ALLOW_BILLING_SIMULATION`. `config.py` defaults the environment to development and Cashfree to TEST. The current compose production environment sets billing simulation false. Production keys and merchant identity are owner-only.
- **Fix plan:** Add a regression test that denies demo activation in production and preserves local simulation only when explicitly enabled. Keep status PARTIAL until owner supplies PROD credentials and runs the owner-authorized real-payment/webhook acceptance test.
- **Discriminating test:** With no credentials and production flags, checkout returns 503 and tier/order records remain unchanged. In a browser with owner-supplied PROD configuration, verify `cashfree.com`, merchant identity, and owner-run payment/webhook/order/receipt. Never perform the payment in this audit.

### ID 4 — Cloud Import using the owner's exact Drive link

- **Observed:** The exact link supplied earlier in this thread was POSTed once to the local `/api/cloud/sync` endpoint. It imported successfully as a 1-page PDF, 554,620 bytes, provider `Google Drive`. The output payload was not printed or opened; the link resolves to a one-page file, not the required 69-page input. This does not contradict the owner's prior live failure and does not satisfy 69-page AI/Studio acceptance.
- **Expected:** Direct Drive viewer links import or show clear direct-download guidance; invalid links fail quickly. The owner explicitly confirmed there is no alternate 69-page Drive link, so this item cannot be fully accepted on the exact file.
- **Suspected root cause:** The current route converts `/file/d/<id>/view` to Drive's `uc?export=download` form at `server.py:5672-5678`; this local route succeeded, leaving the reported live discrepancy likely environment/proxy/Drive access dependent.
- **Fix plan:** Keep the successful Drive conversion and fast failure behavior. Do not claim 69-page success. Verify a bad link still fails cleanly; retain PARTIAL because the only authorized link is 1 page.
- **Discriminating test:** Repeat exact URL locally and on owner-host after deployment; inspect page count without exposing document text; separately confirm malformed link returns a clean 404. Full acceptance requires owner to supply a 69-page accessible link, which they said is unavailable.

### R3 / IDs 1 and 2 — AI provider Translate and Brief/Summarize

- **ID 1 Translate observed:** No provider key or provider configuration is present. No upstream request was made; upstream HTTP status/body/latency are unavailable. The 69-page owner file was unavailable; the 69-page repository copy is not byte-identical to the named owner fixture.
- **ID 2 Brief/Summarize observed:** Same provider configuration and fixture limitation. No real provider call or output was produced.
- **Expected:** Translate returns real translated content; Brief and Summarize return content on the exact 69-page file, with upstream errors accurately exposed when unavailable.
- **Suspected root cause:** Provider selection and API access are in `config.py` and `ai_engine.py`; credentials/model-list access is absent in this environment. The reported upstream timeout cannot be attributed to model, auth, quota, gateway, or network without the actual upstream response.
- **Fix plan:** Do not guess a model or fabricate an upstream error. Improve local diagnostics only if they can be tested without a provider; ask owner to configure/verify the provider and provide the exact model listing. Keep both items PARTIAL pending real output on the named input.
- **Discriminating test:** With owner-provided provider config, call the same server code path for 69-page Brief and Summarize plus 2-page EN→HI and 10-page EN→ES Translate; record only sanitized status class, body class, latency, and verify opened output content twice.

### R4 / IDs 3, 49, and 47 — Studio retention, export, and reorder

- **ID 3 retention observed:** A local database process-restart test preserved account/job/key/waitlist rows. Studio document reload retention was not exercised in the browser during Phase -1.
- **ID 49 Export observed:** No browser Export was attempted in Phase -1. The supplied reports state a small 2-page export worked and the 69-page export returned to idle without a download; those are owner-supplied observations, not reproduced here.
- **ID 47 reorder observed:** A direct POST to `/api/studio/pages/reorder` with a synthetic 3-page PDF and order `[2,1,3]` returned HTTP 200, `application/pdf`, 1,396 response bytes, and extracted page text `QA_PAGE_TWO`, `QA_PAGE_ONE`, `QA_PAGE_THREE`. Thus the server converter honors the requested order in this direct probe. The reported Studio drag/UI mismatch and exported-file chain were not reproduced in the browser.
- **Expected:** Studio mutation changes the in-memory document, persists across reload, and exports an opened PDF with the expected page count and text order; mismatches fail visibly.
- **Suspected root cause:** Client mutation and reload chain in `web/assets/page_organizer.js:1177-1244`; server reorder route in `server.py:4277-4320`. Backend-only success narrows the unverified failure to UI payload/reload/export, but does not identify which stage loses the order.
- **Fix plan:** Capture the actual browser drag payload, response-extracted order, and exported order on the 69-page input before changing client code. Reproduce retention and Export at both file sizes, then fix only the failed stage.
- **Discriminating test:** Studio drag page 1 onto page 2; capture request `order`, extract response page order, download and extract export page order. For retention, delete 69→68, reload, then delete 68→67 and reload; verify counts. Repeat each acceptance twice. Exact owner file still required for FIXED.

- **Additional pre-fix browser retest / harness correction:** An earlier Playwright run with a `route.fetch()` interception returned HTTP 422 and a misleading PDF-header error. The interception changed the multipart request, so that result was a harness artifact. Repeating the actual pointer drag without request interception sent `order=[2,1,3]`, received HTTP 200 with `application/pdf` (3,088 bytes), and the output opened with page text order `Page 1 of 10`, `Page 3 of 10`, `Page 2 of 10` as requested. No Studio reorder failure is reproduced on this 3-page fixture; the exact 69-page owner fixture and two consecutive full-size export rounds remain unverified. No reorder code change was made.

### R5 / ID 94 — fresh Developer API keys

- **Observed:** Two fresh synthetic Developer keys were tested without printing either key. For each key, GET `/api/v1/account/usage` and POST `/api/v1/jobs` each returned respectively 200 and 202 twice with both `Authorization: Bearer` and `X-API-Key`. The DB row existed by key ID; `last_used_at` became non-null. No key value or raw prefix was logged.
- **Expected:** Fresh keys authenticate immediately on both supported headers, update `last_used_at`, and survive a deploy.
- **Suspected root cause:** The 401 reported by the owner was not reproduced in this isolated local database. Current auth path is `server.py:1486-1520`; key storage/verification is `persistence.py:833-887`. A live deployment mismatch remains possible.
- **Fix plan:** Add or extend regression coverage for two fresh keys × both headers × repeated usage/job calls and DB `last_used_at`. Do not change the already-passing auth path without a failing reproduction.
- **Discriminating test:** Repeat exact matrix on deployed-equivalent instance with fresh synthetic accounts, then verify both key rows and last-use timestamps before and after deploy. Live and redeploy proof requires owner infrastructure.

### R6 / ID 99 — AI Chat with attached PDF

- **Observed:** On a generated two-page PDF (`Hello PaperPlane QA alpha.` / `Second page text beta.`) with no AI provider configured, the exact ungated question `What word is written on page two?` returned “General chat is unavailable because the AI service is not configured. I can still help with questions about this PDF.” with no citation. The phrase-qualified version returned `Second page text beta. [Page 2]` and citation `[2]` via deterministic local extraction. This reproduces a routing difference between the two prompts, though not the exact reported “I don't have access” wording.
- **Expected:** With a document attached, every non-greeting question searches it and answers from its text; simple greetings remain direct and reliable.
- **Suspected root cause:** `_is_document_question` gates retrieval at `ai_engine.py:913-914`; `chat_with_pdf` dispatches based on that predicate at `ai_engine.py:791+`.
- **Fix plan:** Make retrieval the default when a PDF is attached, bypass only clear greetings/identity/scope replies, and preserve citation alignment. Add the exact page-two and greeting regression checks.
- **Discriminating test:** Run the exact ungated question twice and verify `beta` plus Page 2 citation; run “According to this document…” for comparison; then “hey” and “hello” twice with a document attached.

- **UI streaming-path retest before fix:** The non-stream `/api/ai/chat` endpoint returned `Second page text beta. [Page 2]` on the exact question. The UI's `/api/ai/chat/stream` endpoint, with the same attached 2-page PDF and no provider key, emitted only `Thinking…`, `Analysing…`, `Generating…`, then `AI provider is not configured`; it did not extract the file. This confirms the UI path still gates on `_is_document_question` in `server.py:3777` even though `chat_with_pdf` was corrected. This failure was recorded before changing the stream route.

### Phase 1 / IDs 5, 6, 12 — citation normalization and false premise

- **Observed before fix:** `align_answer_citations("Fact [[Page 2]].", [2])` returned the nested citation unchanged (`[[Page 2]]`) while reporting chip page `[2]`, so in-text markup and citation chip presentation can diverge. On a two-line synthetic PDF with blank author metadata and visible text `Author: Jane Doe.`, asking `Was this written by Albert Einstein?` returned no correction (`None`), because `correct_false_premise` only checked embedded author metadata. This tests the owner-described failure without making an authorship claim about a real document.
- **Expected:** Normalize nested citation markup into one `[Page N]` form; check explicit author evidence in the document text and state uncertainty when no author can be verified.
- **Suspected root cause:** `align_answer_citations` applies a citation regex that matches the inner brackets but leaves the outer pair (`ai_engine.py:366-410`); `correct_false_premise` reads metadata only (`ai_engine.py:297-359`).
- **Fix plan:** Add focused regression cases for nested and duplicated citations and document-text author claims, then verify the same answer/citation alignment on the streaming endpoint. Provider-dependent 69-page repeated runs remain pending provider configuration and the exact owner file.
- **Discriminating test:** Exact nested citation normalized once and chip parity preserved; explicit text author conflicts with the question claim; blank/unattributed text yields an uncertainty answer rather than a false correction.

### Phase 2 / ID 68 — drawn signature pad

- **Observed before fix:** On the repository's one-page AcroForm fixture, opening the signature modal and drawing in the default active “Draw Signature” tab without clicking that tab left the editor with `0` signature objects and the modal open. Clicking the already-active Draw Signature tab first initialized the pad; the same stroke then placed one editor object and closed the modal. This reproduces a first-use initialization gap rather than a pointer-coordinate error.
- **Expected:** Opening the draw-signature modal initializes pointer handling before the user draws; placing the drawn mark adds an editor object and the exported/opened PDF visibly contains the mark.
- **Suspected root cause:** `SignaturePad` is created only from tab, clear, type, or place click handlers in `web/assets/app.js:3015-3070`; `EditCanvasManager._showSignatureDialog` only reveals the modal (`web/assets/editor.js:1445-1450`). The default-active draw pane therefore has no listeners during the user's first stroke.
- **Fix plan:** Dispatch a signature-modal-open event when it becomes visible and initialize `SignaturePad` on that event. Verify default first-use draw, editor object creation, exported output, and a pixel difference in the opened PDF.
- **Discriminating test:** Do not click Draw Signature after opening; draw via pointer input, place, export, and confirm non-background pixels in the output at the placed location.

### Phase 2 / ID 64 — Forms Add Field visibility and round trip

- **Observed before fix:** Clicking Studio → More Tools → Form Fields & Fill with a loaded form opened the forms modal, but a second click handler also switched the workspace to the `flatten` tool desk behind the modal. The Add Field button was present after opening the modal's Add Field tab. With no PDF loaded, the modal correctly stayed closed and the Add Field button remained unavailable. This reproduced the competing-handler behavior and distinguishes it from the Add Field tab's own visibility toggle.
- **Expected:** The Studio Forms action opens the form engine without switching the workspace; Add Field appears only in its Add tab with an active Studio document. The `/fill-form` tool page remains an existing-field fill workflow and has no Studio Add Field control.
- **Suspected root cause:** `PaperplaneSecurityFormsController._bindHeaderButtons` opens the modal, while `web/assets/app.js:3229` also binds `#studio-forms-btn` to `selectOperation('flatten')`.
- **Fix plan:** Remove the conflicting navigation handler; verify modal, Add tab, no-file state, `/fill-form` state, and a full add/save/open AcroForm round trip.
- **Discriminating test:** On a loaded fillable PDF, Studio remains selected with the modal open, Add Field appears only on the Add tab, and the exported PDF contains the new widget/value; capture no-file and `/fill-form` screenshots too.

### Phase 2 / ID 76 — required-input button state

- **Additional pre-fix attempt / harness correction:** An initial attempt uploaded a file before the asynchronous `/fill-form` route selected its operation, so the route change cleared the file; the resulting “Select files to continue” state was incorrectly attributed to valid form JSON. A separate `.file-item` selector was also wrong; the correct upload row is `.file-row-card`. After correcting the sequence (wait for the fields control, then upload), the existing `renderOptions()` delegated input/change listener updates the button state. No source change was retained for ID 76 based on the invalid attempt.
- **Expected:** Empty organize/edit/forms inputs keep Run disabled with a field-specific label/hint and no red result card; valid input immediately enables Run when a file is present.
- **Suspected root cause:** The owner-reported red banner may occur only on the deployed route or a direct form submission; the local button path has not reproduced it.
- **Fix plan:** Preserve the neutral validation presentation and verify the three controls through the correct route sequence. Keep PARTIAL until all 41 tools and the owner deployment are swept.
- **Discriminating test:** Wait for each route's option field before uploading; verify empty label/disabled state and no red failure banner, enter valid input, and assert the button becomes enabled.

### R7 / ID 97 — password-reset email delivery

- **Observed:** No production mail configuration is present, so no production email was sent or delivery checked. In an isolated local call with SMTP/Resend disabled, `send_password_reset_email` returned `true` and emitted a “simulated” log entry; it did not deliver. The reset function uses `_dispatch_email` with its default `allow_simulated=True` (`email_service.py:100-118, 228-274`). The reset link base is passed from `request.base_url` (`server.py:3068-3076`), not the configured public URL.
- **Expected:** Reset mail reports delivery only after an actual provider accepts it; generated URL uses the public HTTPS base; link works end-to-end.
- **Suspected root cause:** Simulated-success default for password reset and request-derived base URL. Whether production currently logs simulated vs delivered was not testable without server logs/config.
- **Fix plan:** Disable simulated-success for password-reset dispatch, log delivery failure without logging reset tokens, and use the configured public URL. Preserve generic responses where needed to prevent account enumeration. Owner must verify inbox arrival and reset completion twice with a synthetic address.
- **Discriminating test:** Local no-provider reset returns/records a delivery failure and no simulated success; mocked provider success records delivery; configured public URL is used; owner verifies received link and new-password login twice.

- **Additional ID 97 pre-fix reproduction — password-change notification:** With SMTP and Resend disabled, a local call to `send_password_changed_notification` for a synthetic `.test` address returned `True` and the logger recorded “Email dispatch simulated.” This confirmation message also could falsely imply delivery. **Expected:** no transactional or security notification reports delivery unless a configured provider accepts it. **Suspected root:** this function still called `_dispatch_email` with its default `allow_simulated=True`. **Fix plan:** disable simulation for password-change notifications and update the fallback regression test to expect delivery failure when no provider is configured. **Discriminating test:** no-provider call returns `False`; provider-accepted mock returns `True`.

## Other P0/P1 items — baseline entry per tracker item

Where noted as “owner-supplied only,” that is not an independent reproduction and remains open. No source fix for these items had been made when this file was created.

### Phase 1 — AI

- **ID 5 — citation count/placement nondeterminism. Observed:** Owner-supplied evidence reports changing chip counts and duplicate `[Page N]` / `[[Page N]]` markers; not reproduced without provider and exact 69-page input. **Expected:** Stable citation format and count. **Suspected root:** citation parsing/rendering in `ai_engine.py` and frontend answer formatter. **Plan/test:** capture the same question 3 consecutive times on exact owner input and compare page citation arrays and rendered text.
- **ID 6 — false author premise. Observed:** Owner-supplied evidence says “was written by Albert Einstein” is not corrected when embedded metadata is blank; not independently reproduced. **Expected:** Check source text as well as metadata before affirming the premise. **Suspected root:** metadata-only author validation in the Brief/AI answer path. **Plan/test:** ask the false premise on exact owner PDF, verify answer checks extracted text and does not affirm unsupported authorship.
- **ID 12 — raw Markdown/LaTeX and duplicate page markers. Observed:** Owner-supplied evidence reports raw formatting and duplicate citations; not independently reproduced. **Expected:** Clean rendered answer with one citation style. **Suspected root:** answer-to-HTML renderer and citation normalization. **Plan/test:** same three 69-page questions × three runs; inspect visible output and citation arrays.
- **ID 34 — AI Docs layout during Brief. Observed:** Owner-supplied screenshot description reports panels shift/clip during generation; no browser reproduction before fixes. **Expected:** Same layout before/after upload and processing. **Suspected root:** generated-state CSS/DOM changes in AI Docs. **Plan/test:** screenshot baseline, upload exact PDF, use a delayed local stub, compare element bounds; provider-backed run still required.

### Phase 2 — Auth, tools, and Studio

- **ID 60 — resend invalidates old OTP. Observed:** Owner-supplied evidence reports the first code is refused after resend and the UI says to use the latest code; local OTP behavior not reproduced yet. **Expected:** Both codes remain valid for TTL or a pre-entry warning explains invalidation. **Suspected root:** `persistence.py` deletes same-email/purpose OTP rows before insert (`create_email_otp`). **Plan/test:** seeded local OTP flow twice; never consume production quota.
- **ID 64 — Forms Add Field visibility/round-trip. Observed:** owner reports disagree about the Studio modal and `/fill-form`; no UI reproduction yet. **Expected:** Button visible where supported and field is present in opened output. **Suspected root:** `web/index.html` hidden control and `web/assets/security_forms.js` toggle/submit path. **Plan/test:** screenshot both surfaces with/without file, then add/save/open and inspect field widget.
- **ID 69 — Clear Studio control. Observed:** Owner-supplied evidence says no clear-PDF action is in Studio; not browser-tested. **Expected:** In-Studio confirmable clear control clears saved PDF. **Suspected root:** clear action lives only in Settings privacy flow. **Plan/test:** load document, clear from Studio, reload and verify document absent.
- **ID 92 — New Page persists zero-byte document. Observed:** Owner-supplied evidence reports reload error after New Page discards current document; not reproduced. **Expected:** Confirm before discard and persist no document rather than empty bytes. **Suspected root:** New Page persistence path and Studio restore in `web/assets/app.js`/Studio loader. **Plan/test:** New Page with loaded document, accept confirmation, reload, verify no zero-byte restore/error.
- **ID 76 — empty-input error presentation. Observed:** Owner-supplied evidence reports red “Operation Failed” on Page Organizer, Edit PDF, Fill PDF Form; not reproduced. **Expected:** Run disabled with actionable reason; validation is informational. **Suspected root:** shared result title/style at `web/assets/app.js:4013` plus each form's validation handlers. **Plan/test:** empty and valid input in those three tools; sweep all 41 forms.

### Phase 3 — Studio

- **ID 53 — Studio header on scroll. Observed:** owner screenshot description reports header/toolbar clipped after scroll; no browser reproduction. **Expected:** Persistent usable header and page controls. **Suspected root:** non-sticky Studio header/scroll container styles. **Plan/test:** screenshot at rest/scrolled at 1104px and 1920px.
- **ID 45 — Studio footer placement. Observed:** owner says footer becomes visible in Studio scrolling and should be hidden there; no browser reproduction. **Expected:** Studio uses full page; footer does not intrude. **Suspected root:** app shell footer flow. **Plan/test:** screenshots at rest and scrolled.
- **ID 15 — sticky pill nav overlaps content. Observed:** owner-supplied screenshot description reports headings clipped under sticky nav; not reproduced. **Expected:** page content clears sticky nav while scrolling. **Suspected root:** nav height/anchor scroll offsets. **Plan/test:** scroll tool headings and verify unobscured at 1104px/1920px.
- **ID 13 — delete speed on 69 pages. Observed:** owner reports 20–30s; no delete timing recorded on the available repository copy before fixes. **Expected:** Fast delete or undo timer begins after completion. **Suspected root:** full PDF mutation/reload path in `web/assets/page_organizer.js`. **Plan/test:** time delete twice on exact owner 69-page input and verify undo window.
- **ID 10 — multi-page Extract. Observed:** owner reports only current-page export; no UI reproduction. **Expected:** select multiple pages and download a multi-page PDF. **Suspected root:** Studio extract controls/API payload. **Plan/test:** extract pages 2 and 4, open output, verify exact two-page text order.
- **ID 11 — canvas on page jump. Observed:** owner reports blank at 0s and later render; no browser reproduction. **Expected:** deterministic page rendering on navigation. **Suspected root:** canvas load/render sequencing around `jumpToStudioPage`. **Plan/test:** jump across several pages, capture render and page number at each transition.

### Phase 4 — Layout and server Merge

- **ID 100 — mobile drawer height. Observed:** owner and code cross-check describe profile/settings controls below short viewport because `.sidebar` uses `100vh` at `web/assets/styles.css:4120` and `.main-area` uses `100vh` at `:680`; not yet reproduced in the browser. **Expected:** profile/settings reachable at 390px across specified heights, themes, and browser-chrome states. **Suspected root:** viewport-unit sizing. **Plan/test:** screenshots at 667/740/781/844/932, light/dark, chrome shown/hidden.
- **SEO heading sync — P1. Observed:** deep-analysis evidence says 27 pages show the previous tool heading; not navigated through all routes before fixes. **Expected:** each route's H1, description, and title match on first landing. **Suspected root:** `syncSeoContent` in `web/assets/app.js:1458` does not clear stale content when guarded fetches race. **Plan/test:** navigate all 41 routes from cold load and compare DOM title/H1/description.
- **Merge server stall — P1. Observed:** owner reports 75% stall for about two minutes; not reproduced with exact owner PDF. **Expected:** server Merge completes without stall and outputs concatenated pages. **Suspected root:** server worker/timeout/queue path; not established. **Plan/test:** run exact 69-page input twice and record duration, output page count and text.
- **ID 52 — AI Docs empty-state clipping. Observed:** owner reports bottom of “page citations.” fragment hidden; not browser-tested. **Expected:** full empty-state text visible. **Suspected root:** AI Docs panel height/overflow. **Plan/test:** screenshot empty-state at supported widths and heights.
- **ID 16 — Developer API docs links. Observed:** owner reports Swagger/ReDoc links absent; not inspected on local page yet. **Expected:** API docs links are visible and route successfully. **Suspected root:** Developers page template/content. **Plan/test:** inspect `/developers` and link destinations.
- **ID 62 — Studio resize reparenting. Observed:** owner reports Export stall and pager/canvas desync after resize; not reproduced. **Expected:** Export and zoom controls continue working after resize. **Suspected root:** `placeStudioControl` reparenting (`web/assets/app.js` around the owner-cited line 805). **Plan/test:** resize viewport, run Export, change zoom, compare canvas/pager.
- **ID 59 — 820px sidebar regression baseline. Observed:** owner-supplied prior measurements say 220px sidebar, no page overflow; no v9 baseline capture. **Expected:** preserve measurements at 390/820/1440 light/dark. **Suspected root:** shared responsive sidebar CSS. **Plan/test:** viewport matrix after changes.
- **ID 66 — Developer table regression baseline. Observed:** owner-supplied prior measurements say table fits 390px and scrolls inside its box at 820px; no v9 baseline capture. **Expected:** preserve fit and internal scroll at 390/820/1440 light/dark. **Suspected root:** responsive table wrapper. **Plan/test:** viewport matrix after changes.

### Phase 5 — Tools

- **ID 70 — Organizer output order/affordance. Observed:** the directly probed Studio backend reorder returns the requested content order; tool-page `[3,1,2]` output and its “visual drag-and-drop” claim were not tested. **Expected:** opened output text follows `[3,1,2]`; page description matches actual textbox controls or visual controls exist. **Suspected root:** tool order parsing/rendering and stale visual affordance copy. **Plan/test:** run with labeled 3-page PDF, open output, inspect text; inspect page controls.
- **ID 8 — Remove Pages first-attempt timeout. Observed:** owner evidence says one initial timeout, later run needs clean repeat; no local repro. **Expected:** two consecutive successful outputs with the correct page count. **Suspected root:** tool request timeout/worker path not yet known. **Plan/test:** run twice and inspect both files.
- **ID 9 — Smart Metadata 502 and document date. Observed:** owner reports intermittent 502 and section number `3.3.1` used as a document date; no live provider run. **Expected:** stable metadata output with a real date or no date claim. **Suspected root:** AI extraction/schema/date parser. **Plan/test:** three repeated runs on exact input, open export, validate date type and metadata.
- **ID 14 — Annotate/Redact contradiction. Observed:** owner evidence reports same keyword “Important” handled inconsistently; no local reproduction. **Expected:** consistent file-specific distinction and opened output. **Suspected root:** separate phrase extraction/classification paths. **Plan/test:** same labeled document/keyword through both tools twice and inspect outputs.
- **ID 41 — PDF to Markdown flakiness. Observed:** owner evidence says 69-page run needs two clean consecutive completions; not reproduced with exact owner file. **Expected:** Markdown export contains expected page text/markers twice. **Suspected root:** conversion timeout/chunking. **Plan/test:** run twice with exact owner file and inspect output text.
- **ID 90 — concurrent job 502. Observed:** prior local-only probe reports a concurrency concern; header half was separately reported clean live. No live concurrent test was run. **Expected:** 2–4 local concurrent jobs complete without 502; live remains owner-only if it mutates production. **Suspected root:** worker/queue or proxy concurrency handling. **Plan/test:** synthetic local 2/4-job burst, inspect statuses and output files.

## Phase -1 gate

The required R1–R7 probes were attempted before code changes. Local evidence is captured above. Owner-only checks and fixture/provider-dependent checks remain open. The reproduction gate is satisfied for any subsequent local fix only where a failing local reproduction is recorded above or appended here before editing that item. No source fix was made before creating this log.

## Additional pre-fix reproductions performed before the corresponding Phase 3/4 edits

### Phase 3 / ID 10 — Studio multi-page Extract

- **Observed:** On the local deployed-equivalent build, loaded the available three-page labeled fixture (`live-organize-3-1-2.pdf`, 3,120 bytes), selected thumbnail pages 1 and 3, then pressed Studio's Extract button. The button advertised “Extract current page as a PDF”; the download was `extracted_3_live-organize-3-1-2.pdf`, 1,391 bytes, one page, containing only the currently active page. It did not extract both selected pages. The existing batch extraction controller can accept a page array, but the toolbar click passes only `[state.studio.currentPage]`.
- **Expected:** Extract uses all selected pages when multiple pages are selected, and otherwise extracts the active page; the downloaded file opens with those pages in order.
- **Suspected root cause:** `web/assets/app.js` handler for `#editor-extract-page-btn` calls `PaperplanePageOrganizer.extractPages([state.studio.currentPage])` instead of its existing `extractSelected()` helper. The helper chooses sorted selection or the active page.
- **Fix plan:** Route the toolbar button through `extractSelected()` and update the accessible label/tooltip to state that selected pages are used.
- **Discriminating test:** Select pages 1 and 3, extract, open the download, and assert two pages with the expected source text; repeat with no multi-selection and assert a one-page active-page output.
- **Harness correction:** The first Playwright attempt used stale `.thumb-card` selectors and timed out; the current organizer cards are `.organizer-thumb-card`. The corrected locator reproduced the one-page output above.

### Phase 3 / Studio → AI Docs handoff

- **Observed:** Loaded the three-page labeled fixture into Studio, then selected the AI Docs tab. AI Docs opened with `#ai-active-doc-bar` hidden and its placeholder filename still `document.pdf`; the Studio page number was 1. No file or current page was handed off.
- **Expected:** Studio → AI Docs and AI Docs → Studio carry the same PDF and page context, with a visible control in each workspace.
- **Suspected root cause:** Studio owns `state.studio.srcFile` while AI Docs uses `state.files`; the current workspace tab handler only switches views and does not synchronize those records.
- **Fix plan:** Add reciprocal handoff controls, transfer the same File object, remember the current page as the AI context page, and restore that page when returning to Studio.
- **Discriminating test:** Load a labeled 3-page PDF in Studio, select page 3, hand off to AI Docs and verify the filename/context, then open it in Studio and verify page 3 renders.

### Phase 4 / ID 54 — legacy slug 404s

- **Observed:** The local app returned HTTP 404 for `/extract-pages`, `/grayscale-pdf`, `/pdf-to-ppt`, and `/ppt-to-pdf`. The existing `LEGACY_SLUG_REDIRECTS` did not include these paths, while canonical pages exist for the corresponding operations.
- **Expected:** These legacy/public slugs redirect to their existing canonical tool pages and retain normal unknown-slug 404 behavior.
- **Suspected root cause:** Missing entries in `server.py:LEGACY_SLUG_REDIRECTS`.
- **Fix plan:** Add one redirect per missing slug to the correct canonical operation page.
- **Discriminating test:** Request each alias without following redirects, assert HTTP 301 and the intended `Location`, then follow and assert HTTP 200 with the matching tool route.

### Phase 4 / Developer quota copy and Student eligibility suffixes

- **Observed:** Local DOM inspection found the Settings text “Developer API quotas are separate.” The `/developers` screen separately labels the visible 10 calls/day, 3 AI calls/day and 10 MB / 2 jobs values as the **Free Sandbox Tier**, so the Settings sentence can imply a numeric production-tier quota that is not defined in code. `persistence.py:EDU_EMAIL_PATTERNS` and the Student annual eligibility copy both list `.res.in`, `.univ`, `.college`, and `.school`.
- **Expected:** Settings should not promise a separate unspecified quota, and the annual Student eligibility list should contain only the academic suffixes accepted by the chosen eligibility policy.
- **Suspected root cause:** Static copy in `web/index.html` plus dynamic Settings copy in `web/assets/app.js`; the suffix policy is duplicated in the pricing copy and `persistence.py`.
- **Fix plan:** Remove the unsupported quota sentence and remove the four flagged suffixes consistently from UI copy and validation. Preserve the other listed academic domains.
- **Discriminating test:** Assert Settings no longer says Developer quotas are separate; assert the listed domains agree across UI and validation, and that the four removed suffixes are rejected while the retained domains remain accepted.

### Phase 4 / IDs 16 and 50 — Developer specification links and snippet button

- **Observed:** Local `/developers` contains Swagger and ReDoc link buttons. `/docs` redirects to `/developers` under this local configuration and `/redoc` returns HTTP 404 because interactive API docs are disabled by the existing docs safety configuration unless explicitly enabled. The snippet button's DOM text is “Copy Snippet” beside a decorative icon; the reported “Copy Copy Snippet” duplication was not reproduced.
- **Expected:** Visible specification links should lead to available, correctly labeled documentation. Production API docs are intentionally disabled by the existing security configuration; changing that policy without an owner decision would undo that control.
- **Suspected root cause:** `server.py` configures docs routes as `None` when `DISABLE_DOCS` is true, while `web/index.html` always renders links to `/docs` and `/redoc`.
- **Fix plan:** Preserve the existing docs-disabled policy; record the conflict and require an owner decision before exposing interactive schemas in production. Do not relabel the current developer guide as Swagger/ReDoc.
- **Discriminating test:** On the owner's deployed host, confirm the intended documentation policy. If docs are meant to be public, explicitly opt in and verify both links; otherwise update the copy to describe the in-page API reference and remove dead links.

### Phase 4 / IDs 55, 59, 66, 80, 87 — local viewport observations

- **Observed:** In headless Chromium at 390/820/1440 CSS pixels, body width matched the viewport. At 820px the sidebar quota label and count fit in their row without overlap. The developer endpoint table measured 342px at 390px and 607px at 820px; the 390px settings modal fit its viewport. Mobile navigation labels measured 11px at 390px, 9px at 820px, and desktop defaults at 1440px. The 820px sidebar's exact 220px measurement was not collected in this probe.
- **Expected:** No page-level horizontal overflow, readable phone labels, and no overlap in the quota row or endpoint table.
- **Suspected root cause:** These items are responsive CSS and settings-panel layout; no concrete local failure was observed in this probe.
- **Fix plan:** No source change from this probe; preserve the existing layout and leave the exact physical-device/chrome checks as PARTIAL.
- **Discriminating test:** Recheck physical Chrome with its address bar shown/collapsed and collect cropped before/after evidence for the profile/settings controls.

### Phase 5 / ID 70 — Page Organizer copy and content order

- **Observed before the copy correction:** `GET /api/seo/organize` returned 200 with heading “Organize PDF pages with a visual editor,” intro promising thumbnails, and how-to instructions to drag pages. The available operation form uses a “Page order (list every page once)” text input and has no thumbnail grid or drag controls. Running `server.process("organize", ..., {"pages":"3,1,2"}, ...)` on the labeled three-page PDF produced `labeled-qa-3page_organize.pdf`, 1,452 bytes; opening it with PyMuPDF found 3 pages with text `HANDOFF PAGE THREE`, `HANDOFF PAGE ONE`, `HANDOFF PAGE TWO` in the requested order.
- **Expected:** Page Organizer instructions describe the available numeric-order control accurately, and output content follows the requested page order.
- **Suspected root cause:** Stale visual-editor claims in `OPERATIONS["organize"]` and `SEO_CATALOG["organize"]`; the backend order path itself preserves `[3,1,2]`.
- **Fix plan:** Replace visual/drag/thumbnail claims with instructions for the comma-separated page-order field. Add content and route-copy regression checks.
- **Discriminating test:** Run the labeled `[3,1,2]` source twice, open both outputs and verify text order; assert `/api/seo/organize` describes a numeric complete order without claiming thumbnails or dragging.
- **Harness note:** A failed first browser handoff test waited for a hidden file input to become visible; changing the wait state to `attached` resolved it. The next attempt used a broad `canvas` selector that matched both the page canvas and draw overlay; scoping to `canvas.pdf-page-canvas` resolved that. Neither was an application failure.

## Additional Phase -1 pre-fix reproductions — owner admin pages and feedback features

The added owner dashboard code was audited from the unmodified main checkout (`f58d82e`) using an isolated temporary SQLite data directory, synthetic-only identities/keys, and FastAPI TestClient. No production URL, owner credential, real key, payment, or database was used. These entries were recorded before bringing the dashboard changes into the `launch-audit-v9` worktree or changing their implementation.

### Admin authentication, session transport, and information disclosure

- **Observed:** Before completing the advertised three-factor flow, `GET /api/admin/dashboard` returned HTTP 200 with a synthetic value in `X-Admin-Key`; the same route returned HTTP 200 with the synthetic key in the `?key=` query parameter. A DB-issued synthetic admin session was also accepted in `?session=` and returned HTTP 200. Public `GET /api/admin/auth/status` included an `alert_email` field. These calls were made only against the local TestClient.
- **Expected:** Protected admin routes require a session issued only after key + owner code + OTP. No bearer-like credential is accepted in a URL, and unauthenticated status reveals no owner contact address.
- **Suspected root cause:** `server.py:120-143` accepts both direct admin keys and query credentials; `server.py:7487-7495` exposes `ADMIN_ALERT_EMAIL` in public status. `web/assets/admin.js` also reads a session query parameter into `sessionStorage` before removing it from the visible URL.
- **Fix plan:** Remove key and query-string authentication fallbacks; accept only a valid MFA-issued session in the designated header or secure cookie. Remove owner contact information from public status and stop reading session tokens from URL parameters.
- **Discriminating test:** Without a completed MFA flow, test header key, `?key=`, and `?session=`; all protected calls must return 401. A valid MFA-issued header session must succeed. Public status must not contain an email field.

### Global administrator lockout denial of service

- **Observed:** Three synthetic failed-attempt records caused an admin step-1 request from a second synthetic IP to return HTTP 423. The lockout state is shared by the entire owner console, not scoped to the attacker address.
- **Expected:** Rate/lockout controls slow abusive sources without allowing any remote client to disable owner access for 24 hours.
- **Suspected root cause:** One `admin_auth_state` singleton row and no client/IP argument in `record_admin_failed_attempt()` (`persistence.py:162-172,1278-1321`); both auth steps consult the same global state (`server.py:7501-7508,7559-7564`).
- **Fix plan:** Scope failures and temporary lockout to a normalized client address, bound retained buckets, and keep a separate short global emergency guard only if needed.
- **Discriminating test:** Three failed attempts from address A must lock A but not block correct step-1 from address B; repeated attempts from A remain locked and successful authentication clears only A's state.

### Feedback input validation and request bounds

- **Observed:** `/api/feedback` with a non-integer rating returned HTTP 500. A synthetic 50 KB message returned HTTP 200 and was stored. The endpoint accepts raw JSON without rating/category/email/length validation.
- **Expected:** Invalid fields return 4xx validation responses, ratings are 1–5, category/email are constrained, and request/message size is bounded before persistence.
- **Suspected root cause:** `server.py:7683-7693` calls `int()` without a validation guard and checks only that the message is non-empty; `persistence.py:1551` clamps invalid numeric range silently, while there is no maximum message length.
- **Fix plan:** Validate object type, rating integer, category allowlist, email format/length, message length, and body length; return 422 or 413 without a traceback.
- **Discriminating test:** Invalid rating/category/email and over-limit body/message must return 4xx and create no feedback row; valid boundary values persist.

### Probe cleanup overmatching

- **Observed:** In a scratch database, the cleanup function deleted the synthetic address `support-probe@customer.invalid` solely because it contained the substring “probe”. It returned the address in the response. No real data was touched.
- **Expected:** Test-account cleanup is previewable and restricted to explicit synthetic/test identities; a broad substring must not select a legitimate-looking customer account.
- **Suspected root cause:** `persistence.py:1513-1542` immediately deletes all rows matching broad SQL `LIKE` patterns, including `%probe%`, `%example.com`, and `test_%@%`, without an allowlist, dry run, or owner exclusions.
- **Fix plan:** Add preview mode, return stable candidate IDs/counts only, and require a second explicit delete with exact candidate IDs; narrow candidates to reserved test domains/prefixes and exclude protected owner accounts.
- **Discriminating test:** A synthetic account matching a reserved test identity appears in preview and can be explicitly deleted; a non-test-domain address containing “probe” is not selected; the preview request mutates no rows.

### Financial telemetry fallback and duplicate potential

- **Observed:** With only a synthetic active `student_pro` account and no billing event, revenue analytics reported gross revenue of ₹99.00. The product's signed-off ground truth is ₹49/month or ₹399/year. Source inspection also showed all non-free users counted regardless of subscription status and event rows summed without deduplication by Cashfree order.
- **Expected:** “Gross revenue generated” reflects verified, deduplicated settled payment amounts; estimates are separately labeled and must respect the actual billing period/price. Active-user count is not a revenue ledger.
- **Suspected root cause:** `persistence.py:1582-1651` uses hard-coded prices (including the wrong Student amount), sums multiple event types, and falls back to an arbitrary one-price-per-paid-user estimate.
- **Fix plan:** Calculate actual paid totals from unique verified settlement/order records; count active subscribers separately; remove fake-revenue fallback or mark it explicitly as a non-revenue estimate with billing period.
- **Discriminating test:** duplicate notifications for one order count once; failed/pending/canceled orders count zero; absent amount yields no booked revenue; supported Student period prices remain distinct.

### AI credential storage and custom endpoint validation

- **Observed:** Setting a synthetic AI credential through the current admin persistence function stored the exact value as plaintext in the scratch SQLite database. Source inspection showed provider, model, and base URL are saved without allowlist or URL validation.
- **Expected:** UI masking does not stand in for encryption at rest. Credentials should be encrypted with a key stored outside the database (or a managed secret store); provider/endpoint must be constrained so a configured key cannot be sent to an unintended host.
- **Suspected root cause:** `persistence.py:1654-1729` writes and reads `AI_API_KEY` directly and accepts arbitrary `AI_BASE_URL` values; `ai_engine.py` consumes those runtime settings.
- **Fix plan:** Encrypt the stored key with an external key source, provide a safe unavailable/rotation path if the key is absent, validate supported provider+model/base URL combinations, and block unsafe schemes/loopback/private link-local targets unless explicitly approved in development.
- **Discriminating test:** persisted value differs from synthetic plaintext and decrypts only in runtime; masked response never returns raw key; unsupported/HTTP/private destinations are rejected; valid official provider endpoints continue working.

### Embedded admin code and destructive account operations

- **Observed:** Source inspection found a default owner secret code literal in `server.py` rather than a required deployment secret. `admin_delete_user` and cleanup delete sessions/jobs/usage/OTP/reset/idempotency rows but leave billing/audit references; jobs' on-disk output files are not removed by the user deletion helper.
- **Expected:** Production boot fails closed unless both high-entropy owner factors are supplied through deployment secrets; account deletion has an explicit retention policy, preserves financial ledger integrity, and removes or securely expires associated private file artifacts.
- **Suspected root cause:** `server.py:115-117`; `persistence.py:1493-1542` does manual SQL deletion without a transactionally defined ledger/audit/file-retention policy.
- **Fix plan:** Remove the default secret literal; require an environment-provided code, document rotation, and make user deletion transactional with a defined accounting/audit retention strategy plus job-output cleanup.
- **Discriminating test:** Production configuration without owner secrets fails closed; deletion of a synthetic user leaves no dangling foreign references or user-owned output files and retains only intentionally anonymized/audited financial records.

### Admin CSV spreadsheet formula injection (pending targeted reproduction)

- **Observed:** Not yet dynamically reproduced at the time of this entry; source writes untrusted email/platform fields directly to CSV without neutralizing spreadsheet formula prefixes (`server.py:7639-7669`).
- **Expected:** Exports open as data in common spreadsheet software; user-controlled cells beginning with `=`, `+`, `-`, or `@` must not execute formulas.
- **Suspected root cause:** Raw `csv.DictWriter.writerow` values in both admin CSV handlers.
- **Fix plan:** Reproduce with a synthetic waitlist row, then apply a spreadsheet-safe cell sanitizer and regression coverage.
- **Discriminating test:** Export a cell beginning with each dangerous prefix, parse CSV, and assert a leading apostrophe or equivalent safe encoding is present while ordinary values are unchanged.

### Premium-tier audit endpoint authorization (added admin surface)

- **Observed:** A synthetic Pro user with a normal user session called `GET /api/admin/audit-summary` and received HTTP 200 plus the synthetic audit record. No owner/admin session was supplied.
- **Expected:** User activity and IP/email audit logs are owner-only; Pro/Developer entitlement is not an administrative role.
- **Suspected root cause:** `server.py:get_admin_audit_summary` permits `pro`, `dev`, or `admin` tiers and checks no owner MFA session.
- **Fix plan:** Protect this route with the same MFA-issued admin dependency as the new owner console, or remove the route if unused.
- **Discriminating test:** Pro/Developer/free sessions all receive 401/403; the valid admin session can retrieve the logs.

### CSV formula injection

- **Observed:** A synthetic waitlist record with a formula-prefixed `platform` exported unchanged in `/api/admin/waitlist/export.csv`; the raw formula prefix was present in the response body. The export was requested with a synthetic valid admin session against scratch DB only.
- **Expected:** Untrusted cells are neutralized before CSV serialization so spreadsheet applications display them as text.
- **Suspected root cause:** Both CSV handlers pass untrusted columns directly to `csv.DictWriter` (`server.py:7640-7669`).
- **Fix plan:** Apply one sanitizer to all exported fields that prefixes formula initiators after leading whitespace/control characters; add coverage for `=`, `+`, `-`, and `@`.
- **Discriminating test:** Parse both exports and assert each dangerous cell is safe-prefixed while normal values remain unchanged.

### Account deletion leaves private job artifacts

- **Observed:** Deleting a synthetic account removed its user/job database records but left its `JOBS/<job_id>` directory and synthetic output file on disk.
- **Expected:** User-requested/admin deletion removes user-owned job inputs and outputs, or reports that cleanup is still pending; no inaccessible-but-retained file should be silently left behind.
- **Suspected root cause:** `persistence.py:admin_delete_user` deletes DB rows only; user job artifacts are stored under `server.JOBS/<job_id>` and the helper does not schedule directory removal.
- **Fix plan:** Gather safe job IDs, delete DB rows transactionally, then remove only each job's contained directory; report cleanup failures and keep a recoverable cleanup marker if an artifact cannot be removed.
- **Discriminating test:** After deleting a synthetic user, no associated jobs or contained output files remain; a path-traversal-like job ID cannot escape the jobs root.

### AI provider selector does not route by provider

- **Observed:** Source cross-check of all inference entry points shows admin `provider` is persisted and returned, but `call_llm()` always delegates to `call_bluesminds()`; the request builder always formats an OpenAI-compatible `/chat/completions` request. Native Anthropic/Gemini provider configuration is therefore not honored. This is a code-path reproduction pending a no-network mocked request capture.
- **Expected:** Selecting a provider that requires a different endpoint/auth/body format produces a provider-specific request, or the UI refuses unsupported providers.
- **Suspected root cause:** `ai_engine.py:call_llm`, `call_bluesminds`, and `test_bluesminds_connectivity` never dispatch on `runtime_creds['provider']`.
- **Fix plan:** Implement provider-specific adapters for advertised choices using official request formats, or remove unsupported choices and make the UI explicitly say the configured endpoint is OpenAI-compatible only. Keep secret routing constrained to verified endpoints.
- **Discriminating test:** Mock HTTP for each provider selection and assert host, path, auth scheme, and request body shape without network access; unsupported providers fail before any request.

## Additional pre-fix traces found during the admin/security cross-check

These are source-level traces of the pre-fix implementation, identified while cross-checking the merged owner-console implementation. They are appended here to preserve the evidence and distinguish code-path findings from dynamic reproductions; the corresponding regression checks were added after the fixes.

### Cashfree production environment default

- **Observed:** Before the guard, `config.py` defaulted `CASHFREE_ENV` to `TEST` independently of `PAPERPLANE_ENV`. With production credentials present, `create_checkout_session` proceeded to the Cashfree request builder and returned the configured environment without requiring `PROD`. No real or sandbox gateway credentials were used in this audit; the behavior was traced from the local code path.
- **Expected:** A production environment must refuse checkout unless Cashfree is explicitly configured for `PROD`; missing credentials or `TEST` must leave the account unchanged.
- **Suspected root cause:** Cashfree host selection had a `TEST` default and checkout only checked whether credentials existed.
- **Fix plan:** Default the host by environment, block `TEST` in production before any upstream request, and test with runtime-generated synthetic values plus a mocked gateway.
- **Discriminating test:** Production + `TEST` + synthetic credentials returns 503, does not call the gateway, and leaves the synthetic user on Free; production with no credentials also remains Free.

### Cross-provider credential and masked-key round trip

- **Observed:** Before hardening, the admin database used one `AI_API_KEY` for every selected provider; changing `AI_PROVIDER` did not partition that key. The admin UI placed the partially masked key in the input's actual `value` and sent it on Save, while persistence only recognized masks that began with bullet characters. An unchanged masked display could therefore overwrite the real key with the mask; switching providers could also route one provider's credential to another provider's API.
- **Expected:** A mask is display-only, keys remain scoped to their provider, and an absent key for the selected provider fails closed without borrowing another provider's key.
- **Suspected root cause:** One shared credential setting and a masked string posted as a real form value.
- **Fix plan:** Store credentials under provider-specific encrypted settings, migrate legacy settings only to the provider that owned them, show masks as placeholders, and remove cross-provider environment-key fallback.
- **Discriminating test:** Store a runtime-generated key, save the masked display without changing the key, switch providers without a key, assert no key is sent, then switch back and verify the original provider key still works. Mock all six provider request formats and assert host/path/auth/body without network access.

### Admin request bounds, OTP consumption, and persistence diagnostics

- **Observed:** Before hardening, admin endpoints checked `Content-Length` but parsed request bodies with `request.json()`; a chunked body without that header had no application-level byte cap. OTP verification selected and cleared the singleton OTP in separate autocommit operations, allowing a race between simultaneous requests. The persistence health endpoint allowed only loopback clients, which excludes an Nginx container forwarding over the Docker bridge.
- **Expected:** Bound admin JSON independently of headers, consume an OTP atomically, and allow only a fully MFA-authenticated owner to view persistence details through the reverse proxy.
- **Suspected root cause:** Header-only request-size checks, non-transactional OTP read/update, and a loopback-only health endpoint.
- **Fix plan:** Stream and cap small admin JSON bodies, use an immediate SQLite transaction for single-use OTP verification, and protect the health snapshot with the MFA session dependency.
- **Discriminating test:** Malformed/oversized bodies return 4xx/413, one generated OTP succeeds once, anonymous health access is 401, and an admin session retrieves resolved path, mount state, file metadata, and row counts.

### Security-header duplication at the reverse proxy

- **Observed:** Direct app middleware sets one instance of each application security header. The Nginx template also adds `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and `Permissions-Policy`; source configuration therefore predicts duplicate values on proxied responses. Docker Engine/Nginx runtime is unavailable here, so the proxied header count could not be captured by curl.
- **Expected:** The browser receives one authoritative value per header, with HSTS still emitted by the TLS edge and CSP still emitted by the application.
- **Suspected root cause:** The proxy appended the same four headers that FastAPI already returned.
- **Fix plan:** Hide only those four upstream headers at Nginx and keep its edge values; leave direct application responses intact for non-proxy local use.
- **Discriminating test:** Direct TestClient response has exactly one each; Nginx template contains upstream hide rules; owner verifies proxied `curl -sSI` after deployment.

### Production session-secret fallback and verified revenue count

- **Observed:** Before hardening, a missing session secret silently generated a random key per process, so production sessions could diverge across Uvicorn workers/restarts. The revenue dashboard counted every active non-Free user as a paying customer even when no verified payment event existed, and treated missing currency as INR.
- **Expected:** Production starts only with a stable configured session secret; paying-customer count and gross revenue come from verified, deduplicated INR orders, and missing currency is not booked.
- **Suspected root cause:** Development-friendly random-secret fallback was also active in production; paid-tier entitlement was used as a revenue proxy.
- **Fix plan:** Fail production startup without a sufficiently long configured secret; count only active paid-tier users tied to verified orders; require explicit INR currency and use a configurable fee estimate.
- **Discriminating test:** A subprocess with production settings but no session secret fails closed; duplicate verified orders count once; pending, demo, foreign-currency, and missing-currency events do not count; the fee calculation uses exact decimal rounding.

### Owner contact disclosure in the public admin shell and email fallback

- **Observed:** Source inspection found a personal owner email embedded in the publicly served `/admin` HTML's OTP destination and as the fallback recipient for waitlist notifications. The admin status API no longer returned the address, but the page source and email dispatcher still exposed/used it. No email was sent.
- **Expected:** Public login HTML must describe the configured delivery destination without naming it; notifications must be skipped when `ADMIN_ALERT_EMAIL` is unset rather than sent to a source-coded recipient.
- **Suspected root cause:** Stale presentation text in the embedded admin HTML and a hard-coded default in `email_service.send_waitlist_alert`.
- **Fix plan:** Replace the email text with a generic configured-owner label, remove the hard-coded fallback, and return a non-delivery result with a safe warning if no recipient is configured.
- **Discriminating test:** Anonymous GET `/admin` contains no email-shaped OTP destination; waitlist alert with no configured recipient returns false and does not call the email transport.

### Waitlist input validation and HTML email injection

- **Observed:** Before the validation hardening, `/api/waitlist` accepted an email whenever it contained `@` and `.`, and passed the raw platform value to persistence. `send_waitlist_alert` interpolated the submitted email and platform directly into an HTML email to the owner. A public caller could submit markup-like email/platform data and influence owner notification HTML; no actual email was sent.
- **Expected:** Validate email as a bounded string, constrain platform to the documented set, and HTML-escape all untrusted notification fields before composing mail.
- **Suspected root cause:** Permissive `@`/`.` checks and raw f-string interpolation in the notification template.
- **Fix plan:** Apply strict shape/type/length validation at the route and persistence boundary, escape email/platform/IP in HTML, and keep the message subject safe through the same validation.
- **Discriminating test:** Malformed email and non-string platform create no waitlist row; an HTML-like notification value is escaped in the mocked email body and never reaches the dispatcher raw.

### Additional pre-fix trace — low-entropy admin OTP storage and provider redirects

- **Observed:** At the v8 baseline, `persistence.set_admin_pending_otp` stored `SHA256(six_digit_OTP)` in the SQLite row. Because the OTP has only one million possibilities, a database-only attacker could test that small space offline without triggering the three-attempt lockout. Separately, provider calls in baseline `ai_engine.py` used `urllib.request.urlopen` with its default redirect handler while sending bearer, `x-api-key`, or `x-goog-api-key` credentials. No external provider was contacted and no redirect was followed during reproduction; cross-origin header behavior was not claimed as a live exploit.
- **Expected:** OTP verification should compare a keyed digest so a database-only copy does not enable a practical OTP search; provider credentials should never be sent to a redirect destination.
- **Suspected root cause:** Unkeyed `hashlib.sha256(otp_code)` in `persistence.py`; default `urlopen` redirect handling in AI provider request paths in `ai_engine.py`.
- **Fix plan:** Derive an HMAC key from a stable server secret that is shared across workers, keep compare_digest and transactional single-use consumption, and route all AI provider calls through a no-redirect opener.
- **Discriminating test:** Store a generated OTP and assert the DB value differs from SHA-256 of the code, the correct code verifies exactly once, and wrong codes fail. Assert the no-redirect handler returns no redirect request for an external target. These tests are synthetic and make no provider network requests.

### Additional pre-fix trace — OTP disclosure in email logs and false admin delivery success

- **Observed:** Baseline `send_otp_email` included the one-time code in its subject; both SMTP and Resend success logs include the email subject. If no provider was configured, its default simulated branch logged the complete message body. `send_admin_login_otp` also put the code in the subject, allowed simulated dispatch, and the admin step-1 route returned `otp_sent` immediately via a background task without checking delivery. The source trace identifies this leak path; no actual OTP was generated for this reproduction or written to a log.
- **Expected:** OTP values appear only in the email body sent to the intended recipient; neither subjects, server logs, reports, nor simulated previews contain the code. Admin login must not claim that an OTP was sent unless a configured provider accepted it.
- **Suspected root cause:** OTP-bearing subject strings in `email_service.py`, simulated dispatch defaults on OTP functions, and unchecked background delivery in `/api/admin/auth/step1`.
- **Fix plan:** Use generic OTP subjects, disable simulation for user/admin OTP delivery, send the owner OTP through a worker thread and require provider success before returning `otp_sent`; clear the pending OTP and return a safe service error on failure.
- **Discriminating test:** Mock provider acceptance and capture logs to confirm the generated code exists only in the email body, not subject/logs. With provider failure, assert the admin route returns 503, the pending OTP is cleared, and the code is not returned or logged.

### Additional pre-fix trace — HTML escaping in transactional email templates

- **Observed:** The source review found request-derived or user-derived values interpolated directly into several HTML email templates: login user-agent/IP/email, reset-link URL/email, password-change notice, OTP destination text, and lockout alert details. Unlike the waitlist template, these paths did not consistently use HTML escaping. No email was dispatched and no HTML payload was rendered to a recipient during this trace.
- **Expected:** Treat every dynamic value as untrusted when placed in HTML text or an attribute; email templates should encode markup characters while leaving plain-text messages readable.
- **Suspected root cause:** Inline f-string HTML composition in `email_service.py` without applying `html.escape` to every dynamic field.
- **Fix plan:** Escape user-controlled and request-derived values at each HTML interpolation point; keep text/plain bodies useful and preserve the generic OTP subject. Add mocked-dispatch assertions across the relevant templates.
- **Discriminating test:** Pass markup-like synthetic IP, user-agent, email, and URL strings into the email helpers with `_dispatch_email` mocked; assert no raw tag reaches HTML and the encoded representation is present.

### Additional pre-fix trace — production reset-link origin could fall back to request host

- **Observed:** Before configuration hardening, `PAPERPLANE_PUBLIC_URL` was optional. The reset route used `request.base_url` when it was unset, and `email_service.py` defaulted its origin to a localhost URL. Thus a production deployment with an incomplete environment could send a localhost or request-host reset link. No reset email was sent in this trace; the configured public URL was absent locally.
- **Expected:** Production must use a configured absolute HTTPS origin for reset links and canonical URLs; missing or local origins must prevent startup rather than issue unusable or attacker-controlled links.
- **Suspected root cause:** Optional public-origin configuration in `config.py`, plus request-derived fallback in `/api/auth/forgot-password`.
- **Fix plan:** Fail production startup for missing/non-HTTPS/local public origins, keep development fallback behavior, and make the generic forgot-password response avoid claiming delivery to protect against account enumeration.
- **Discriminating test:** Production subprocess with a valid stable session secret and missing/local/non-HTTPS public URL must fail closed; HTTPS public URL is used for generated reset links, with no provider call required in test mode.

## Phase 7 harness correction — AI connectivity retry test

- **Observed:** The first candidate full-suite run completed 346 tests and had one failure in `test_connectivity_check_retries_transient_failure_once` after the AI transport was changed to `_open_ai_request` and runtime provider configuration. The test still monkeypatched the removed direct `urllib.request.urlopen` path and did not provide selected-provider runtime credentials, so the probe returned `configuration_missing` before exercising its intended retry assertion. No provider request was made.
- **Expected:** The test should isolate connectivity retry behavior by supplying synthetic runtime configuration and mocking the supported request abstraction.
- **Correction:** Updated the test fixture to provide a synthetic Bluesminds config and mock `_open_ai_request`; retained the retry count, transient-503-then-success assertion, and production no-redirect path.
- **Verification:** Focused rerun and the two final full-suite runs are recorded in the run logs after this correction.

### Additional pre-fix trace — filesystem path in the legacy public health route

- **Observed:** A local unauthenticated `GET /health` returned HTTP 200 and included the resolved jobs directory in the JSON body. The separate `GET /api/health` route returns a reduced operational summary, but the duplicate later `/api/health` decorator on the legacy handler made the route map ambiguous while `/health` still exposed the filesystem path.
- **Expected:** Public health reveals only service availability; resolved paths, mount state, file metadata, and database counts are available only through the MFA-protected persistence diagnostic.
- **Suspected root cause:** Duplicate `/api/health` route registration plus the legacy handler returning `jobs_directory` in `server.py`.
- **Fix plan:** Remove the duplicate API decorator and filesystem path from the public `/health` response. Keep `/api/health` on its reduced health handler and `/api/health/persistence` owner-only.
- **Discriminating test:** Anonymous GET `/health` and `/api/health` return 200 without path fields; anonymous persistence diagnostics return 401 and an MFA session may inspect details.
