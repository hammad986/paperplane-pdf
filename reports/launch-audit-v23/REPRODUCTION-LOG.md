353 elite-list items confirmed in paperplane-codex-elite-prompt-v23.pdf (99 pages; v23 checklist canonical IDs 1–357 with intentional gaps).


# Phase -1 Part A — baseline and v22 claims

Baseline branch/commit: main / 03436d90d9fc233eedf3a614eaa5de4f520137ca. The worktree was clean at start. No branch was created, and no reset, commit, push, deployment, production payment, or admin login was performed. A separate read-only Chrome inspection of the live pages was followed by two authorized guest operations using a public five-page PDF; they created normal transient job records for retention cleanup, not account or user document changes.

Full suite run before any v23 code change: **488 passed, 1 Starlette/httpx deprecation warning** twice. Logs: pytest-baseline-run1.log, pytest-baseline-run2.log. This confirms the v22 count and satisfies v23's baseline gate.

## ID 249 — Studio toolbar at 1360px

Reproduced the primary ribbon wrapping and placing Export PDF on a second line at a 1360×900 viewport. Changed desktop ribbon layout to a single non-wrapping row and compacted icon controls between 901–1450px while retaining native button titles/accessible labels. Two Chromium runs confirmed the primary row is 41px high, the complete ribbon fits its 816px client width, Export PDF fits inside the visible toolbar, document width remains 1360px, and no page errors occurred. Evidence: `browser-id249-studio-toolbar-1360.json`, script, and two screenshots.

## ID 250 — PDF to Markdown output title and hierarchy

Reproduced that the upload pipeline passed a random staged path to the converter without preserving the user's original filename, and that regular 12pt lines were promoted to `###`. Passed a sanitized original upload name through job options, use it as the H1 fallback when PDF metadata has no trustworthy title, and reserve heading markup for larger or bold text. Two browser API uploads of a synthetic PDF named `Annual Report.pdf` completed and downloaded 125-byte Markdown with `# Annual Report`, two unmarked body paragraphs, and `## Key Findings`. Focused regression tests passed. Evidence: `browser-id250-markdown-upload.json`, script.

## ID 251 — Admin plan counts and job dates

The live evidence cannot be asserted from the old synthetic 13-account dataset, so seeded a controlled 13-account dashboard fixture to discriminate the percentage calculation and missing tier rows. Reworked the plan breakdown to render every tier returned by analytics with each percentage divided by `total_users`, and changed the “today” metric to an explicit UTC calendar-day count separate from all-time jobs. A persistence regression seeded five tiers and jobs across UTC midnight. Two Chromium runs showed all five categories and distinct totals (987 all time / 7 today) with no page errors. Evidence: browser JSON/script/screenshots and the analytics regression test.

## ID 252 — Summary citation noise and truncation

Aligned consecutive supported inline page references into compact ranges and capped very long scattered inline citations at 120 characters while preserving the complete verified page set for source chips. The summary chip renderer compresses consecutive pages and limits visible disjoint ranges with an explicit remainder count. Tests verify a six-page run becomes `[Pages 1-6]`, scattered references stay bounded without losing the returned page IDs, and two browser rounds render `Pages 1-6` with capped ranges. Evidence: `browser-id252-summary-citations.json`, script, and citation regression test.

## ID 256 — Safe repair failure message

Two local Chromium runs uploaded a malformed no-trailer PDF through the repair job API. Both jobs failed with the friendly “This PDF is too damaged to repair automatically.” message; no pikepdf or `code=4` internal string appeared and the browser had no JS errors. Existing tests also verify storage errors receive a distinct safe retry message. Evidence: `browser-id256-repair-safe-error.json`, script.

## ID 259 — Studio and AI document page-count difference

Rather than silently present the original AI upload as the edited Studio result, added a visible disclosure to the AI active-document card that the AI workspace keeps its own PDF copy and must be given the edited export to refresh page count and analysis. Two Chromium upload rounds used a ten-page PDF at 1366px and 390px; both showed the ten-page AI count and disclosure with no horizontal overflow or JS errors. Evidence: `browser-id259-ai-copy-disclosure.json`, script, screenshots.

## ID 262 — Browser crash on PDF upload

Two fresh Chromium sessions uploaded a generated ten-page PDF through the Merge page's file input. Both sessions stayed alive, kept the upload listed, and reported no crash or JS error; selection completed in 2.004s and 1.685s. Evidence: `browser-id262-upload-stability.json`, script, screenshots.

## ID 258 — Daily synthetic sandbox probe

Confirmed the scheduled workflow and probe script exist locally. The workflow is scheduled daily and manually dispatchable, with test-only Cashfree credentials. A successful GitHub Actions run and the owner's alert channel/recipient are still unverified; this item remains partial and no checkout was attempted.

## IDs 267–268 — Studio toolbar delete and fresh upload

Two fresh Chromium rounds uploaded the same generated ten-page document directly into Studio. It rendered all ten pages without a null-style error; clicking the toolbar Delete page then yielded nine pages without the bogus “Cannot delete all pages” toast. No page errors occurred. Evidence: `browser-ids267-268-studio-upload-delete.json`, script, screenshots.

## ID 271 — Hindi Devanagari translation output

Re-ran the controlled local translation regressions. Both returned PDF outputs with the expected extractable Devanagari strings, including `प्लेन` and `टेस्ट`. No live provider/browser download was available in this pass, so classification remains partial; final proof requires content-checking a real provider-generated downloaded PDF after deployment.

## IDs 295 and 309 — DOCX rasterization and Scan-to-PDF dimensions

The current two-round v23 browser catalog converted a 4.98 MB, 69-page PDF into a 1.27 MB editable DOCX with 207 paragraphs and preserved first-page text; this confirms the old rasterization blowup is absent locally (mixed-media preservation is separately tracked as ID 308). The current Scan-to-PDF browser rounds for ID 253 also cover ID 309: 2400×1800 pixels at Original 200 DPI became 864×648 PDF points. Evidence: `browser-catalog-round2.json`, `browser-id253-scan-dpi.json`.

## ID 294 — Large-file server operations

Generated a 4.83 MB, 69-page image/text PDF, then uploaded/downloaded it in Chromium through Compress, Watermark, and Page Numbers. All three completed in 0.92s, 1.65s, and 1.30s; output retained 69 pages, Compress retained its text marker, Watermark retained `CONFIDENTIAL`, and Page Numbers contained first/last `Page N of 69` stamps. Evidence: `browser-id294-large-server-tools.json`, script.

## ID 301 — Sparse-PDF broad question response

Reproduced with a 24-page gallery PDF containing only 159 searchable characters. Added a deterministic low-text-density check for broad subject/summary questions; it now says the subject cannot be reliably identified and recommends OCR, instead of “No relevant information found.” The focused regression and two local Chromium API runs passed without provider access or JS errors. Evidence: `browser-id301-sparse-pdf-message.json`, script.

## IDs 297–298 — Cloud import trigger and annotation comment

The shared Drive/Dropbox URL dialog was exercised from both entry points in two Chromium rounds; each trigger opens the same single URL field and action. The current browser catalog annotation download was also checked for `ANNOTATION_AUDIT_NOTE` in extracted PDF text. Evidence: `browser-ids274-275.json`, `browser-catalog-round2.json`.

## ID 302 — PDF-to-Excel table columns

Two local Chromium runs uploaded a grid PDF and downloaded the resulting workbook. Both preserved the exact 3×4 table with separate Item, Quantity, Price, and Amount columns and both data rows. Unstructured prose still exports as one text column, which is not structured table data. Evidence: `browser-id302-excel-table-columns.json`, script.

## ID 303 — Sidebar Compare and Metadata entries

Two local Chromium rounds opened the Edit PDF sidebar category and confirmed both Compare PDF and PDF Metadata controls are listed and visible. Evidence: `browser-id303-sidebar-compare-metadata.json`, script.

The attached v23 PDF is 99 pages. Its tracker summary states 353 elite-list items: 247 open (11 P0, 76 P1, 160 P2), 89 verified_fixed, 15 to_verify, and 2 not_tested. The canonical IDs span 1–357 with intentional gaps and documented tracker-only artifact 244. The first line above records the count before work.

## V22 claims audit

| # | Claim from v22 report | Current code/evidence check | Result |
|---|---|---|---|
| 1 | ID 241 {total} substitution | server.py:2682-2704 replaces both {n} and {total}; regression coverage is in tests/test_text_layer_v18.py and tests/test_launch_audit_v22.py. | Present locally; live verified in v22 per PDF. Retest old failure mode in Phase -1. |
| 2 | ID 309 Scan-to-PDF sizes | converters.py:2245-2289, server.py:2397-2399, web/assets/app.js:3525-3532; tests in tests/test_launch_audit_v22.py; local Chromium evidence from v22 scripts. | Present locally; live verified in v22 per PDF. Retest raw-pixel failure mode. |
| 3 | ID 283 compression content guard | converters.py:1920-2084 skips alpha/palette/CMYK image replacement and validates rendered black-pixel changes; job warning passes via server.py:2372-2388, persistence.py:51, 227-235, 1080+, and web/assets/app.js:4638-4642. Tests in v21/v22 audit test files. | Present locally; live verified in v22 per PDF. Add exact rendered image regression to current v23 tests. |
| 4 | ID 299 billing status omits Cashfree order ID | server.py:3790-3826 response no longer includes cashfree_order_id; internal billing persistence and verification still use the field. | Present locally; live verified in v22 per PDF. Retest privacy regression. |
| 5 | ID 1 safe provider status/fallback | ai_engine.py:760-909, 1910-1934, 2060-2085; configured fallback is encrypted in persistence and used by the selected-provider helper. Safe 429 status reaches server.py:2818-2838. | Local controlled 429 fallback passes; imbalanced character-vs-block translation is now rejected with HTTP 422 and no download. Live deployed provider still fails content discrimination in the 10-page matrix; keep ID 1 PARTIAL. |
| 6 | ID 246 CSP and nginx version disclosure | deploy/nginx.conf.template:1-2, 70+ has server_tokens off and CSP; deploy/nginx-http.conf.template:1-2 disables tokens. | Present in templates; live verified by v22 per PDF. Recheck current served response read-only. |
| 7 | ID 220 PDF/A profile handling | Dockerfile:40-48 installs ICC profiles and copies sRGB; converters.py:1411-1503 finds profile and validates PDF/A metadata/OutputIntent. Prior WSL artifacts exist only in V21 reports. | Code is present; live verified by v22 per PDF. Production-image veraPDF validation still owed; do not reopen live fix on that alone. |
| 8 | Full suite 488 twice | Current clean baseline run: 488 passed twice, one warning each. | Confirmed. |
| 9 | 176 responsive route checks | V22 evidence `reports/launch-audit-v22/route-layout-matrix.json` is not present in this checkout. The attached v23 PDF records the later defects at 846/1024 and 390px. | V22 route-matrix claim is unverified here; v23 P0 340/341 reproduced and retested locally below. |
| 10 | 44-operation catalog 39 completed and P0 status report | V21 evidence folder exists, while the referenced V22 catalog/P0 artifacts are absent. | V22 claim is not current proof; rerun of the local catalog is in progress. |

This audit confirms v22 code claims only where present above. It does not close any v23 item without the v23 reproduction and regression checks.

## V23 implementation and local reproduction

| Item | Change/reproduction | Result and evidence |
|---|---|---|
| ID 1: misleading partial Translate | `ai_engine.translate_pdf_layout` now records translated block fraction and refuses to emit output below 50%; the API reports `failed` and includes the measured fraction header for partial/complete outputs. Added `tests/test_launch_audit_v23.py::test_translation_below_half_fails_with_actual_fraction`. | Local deterministic-provider browser runs and the focused regression pass. Live public-site repeats against the five-page sample exposed inconsistent quality: Spanish translated-marker pages 5/5 then 3/5; Hindi attempt 1 returned HTTP 429 and attempt 2 showed a Hindi-script marker on only 1/5 pages. Both successful HTTP 200 PDFs retained substantial English. This is not a fixed live result; see `browser-live-ai.json` and `live-translation-*-attempt-*-5-pages.pdf`. |
| ID 2: offline brief presentation/summary quality | Long-document fallback now emits one clearly labeled Offline Analysis heading and scoped section notes, with explicit text that local notes cannot establish absence elsewhere. Provider prompt now requires exact source numerics/units and forbids unsupported currency/absence claims. UI labels offline extractive notes separately from AI synthesis. | The 24-page cancellation/deadline fixture is covered by unit tests; the 69-page browser output was exercised with the deterministic test provider. Live public summary returned HTTP 200 and citations for pages 1–5, but the response omitted `summary_mode`, so provider synthesis cannot be distinguished from offline fallback; the required provider-backed 69-page case remains unverified. See `browser-live-ai.json`. |
| ID 4: Drive and direct cloud import | Local Chromium called `/api/cloud/sync` twice for the correct W3C testfiles PDF and twice for the exact owner Drive `/view` URL from v23. | W3C attempts both returned HTTP 200 and content-checked one-page `dummy.pdf`. The exact Drive URL failed both times with the truthful `Google Drive returned image/png, not a PDF` response. The link does not currently point to a PDF, so the owner Drive import requirement cannot pass until a valid PDF link/file is supplied. Evidence: `browser-p0.json` (`cloud_import_p0_paths_twice`). |
| ID 93: account/data persistence | Initial process-restart test was followed by a current-image four-worker container replacement run on an isolated named volume. | Fixed locally: concurrent SQLite initialization was serialized; six cold-start initializers passed, all four workers became healthy, the account and feedback row survived container replacement, and Chromium login/authenticated `/api/auth/me` passed. The earlier Docker-engine-unavailable attempt is superseded. Evidence: `browser-id93-container-persistence.json`, `browser_id93_container_persistence.py`. |
| ID 101: admin secret code exposure | Confirmed required env-only startup settings, Gitleaks workflow `.github/workflows/secrets.yml`, and prepared purge script `scripts/prepare_admin_history_purge.py`. | Code side present. Script not run because it rewrites an isolated history mirror and user/PDF explicitly prohibit touching either history mirror. Rotation, coordinated history rewrite/force-push, cache purge, and Security Audits review remain owner-only. |
| ID 102: feedback delivery | Two local Chromium rounds submitted feedback through a browser same-origin request while an authenticated admin Feedback tab was open. | Both showed the new row via automatic polling without reload; the disposable feedback record was deleted. Evidence: `browser-p0.json` (`feedback_submission_visible_in_admin_poll_without_refresh`). |
| ID 207: 60 MiB Merge progress and output | Ran `scripts/browser_v14_smoke.py` twice against the current code, with a synthetic 60 MiB, 759-page PDF plus a 10-page PDF. | Both local Chromium runs observed XHR progress and cancel recovery, downloaded the merge output, and content-checked 769 valid pages. Second run output: `browser-full-smoke-round2.log`. Owner's image-heavy fixture was unavailable. |
| ID 6: false authorship claim with blank PDF metadata | Uploaded a one-page PDF with neither author metadata nor an author statement and asked whether Albert Einstein wrote it. | Three focused regression tests passed. Local Chromium request to `/api/ai/chat` returned HTTP 200 with “I can't verify that authorship claim…” and no citations. Evidence: `browser-p0.json`; test: `test_false_author_claim_is_corrected_when_metadata_and_text_have_no_author`. |
| ID 9: Smart Metadata section-number/date and first-run viewer | The local extractor returned a stable section-number result; a two-round Chrome test then exercised an invoice upload/view/export flow, a controlled first-attempt 502, and a delayed response interrupted by navigating to another tool. | Section-like `3.3.1` is neither date nor topic. Transient 502 retried to HTTP 200; viewer mounted, actual JSON download parsed, result card survived close. Tool switch cancelled/invalidated the delayed request and no stale viewer/result appeared. Zero page errors. Provider availability remains unproven. Evidence: `browser-p0.json`, `browser-id9-metadata-viewer-e2e.json`, `browser_id9_metadata_viewer_e2e.py`. |
| ID 35: greeting with an active document | Posted a real one-page PDF with “Hello, how are you?” to local `/api/ai/chat` through Chromium. | HTTP 200 greeting response, no citations, no document-retrieval fallback. Evidence: `browser-p0.json` (`general_greeting_works_with_document_loaded`). |
| ID 10: Studio Extract no automatic download | Opened a one-page PDF in Studio and clicked the visible Extract button. Repeated the real browser flow twice. | Both runs triggered Chromium downloads; downloaded PDFs reopened with one page and the expected page text. No page errors. Latest run recorded in `browser-p0.json` (`studio_single_page_extract_download_content_checked`). |
| ID 11: blank/stale canvas during deep page jump | Loaded a synthetic 69-page PDF in Chromium, waited for its canvas, navigated to page 69, then returned to page 1. Repeated twice. | Each target active page rendered visible (non-white pixel) content. No page errors. `browser-p0.json` (`studio_page_jump_1_69_1_canvas_rendered`). |
| ID 14: Annotate succeeds but Redact misses the same keyword | Submitted the same fixture containing “Important” to local Chromium requests for `/api/pdf/annotate` and `/api/studio/security/redact`. Repeated twice. | Both endpoints returned HTTP 200; annotation output had one annotation, while redaction removed “Important” from extracted text and preserved “review note”. Evidence: `browser-p0.json` (`annotate_and_redact_find_same_keyword`). |
| ID 12: raw Markdown and duplicated nested page tokens in chat | Uploaded a source PDF in the local browser and asked a document-summary question with the AI provider disabled. | Removed duplicate citation emission from deterministic extraction. Two browser runs rendered a single inline citation tag and a single matching verified-page chip, with no raw markdown or nested `[[Page N]]`. Provider-backed LaTeX/format variance remains unverified. Evidence: `browser-p0.json`; regression in `tests/test_launch_audit_v23.py`. |
| ID 13: Studio page delete delay | In two browser runs, opened a 69-page PDF, deleted page 34, then verified page count and the shifted page content. | Page count updated to 68 and page 34 became former page 35 in 0.763s and 0.765s. Evidence: `browser-p0.json` (`studio_delete_one_page_updates_count_and_content`). |
| ID 15: sticky navigation allegedly overlaps tool headers | Scrolled `/ocr-pdf` and `/remove-pages-pdf` to 560px at 1104×760 in two Chromium runs; measured tool-title, topbar, and mobile-nav rectangles. | No measured overlap: the topbar had scrolled out of view and the title was above the viewport. Exact reported sticky-pill screenshot behavior was not reproduced, so the item remains partial. Evidence: `browser-p0.json` (`tool_heading_not_obscured_after_scroll_1104px`). |
| ID 16: developer page spec links and footer API Docs loop | Added CSP-compatible Swagger/ReDoc pages and generated OpenAPI JSON, then checked developer and legacy URLs. | Two browser runs verified Swagger, ReDoc, and schema routes (200+ paths), with all developer/footer links and `/docs`, `/api-docs`, `/redoc` resolving without the old loop. Browser had no page errors. Regression: `test_public_api_spec_links_resolve_without_developer_page_loop`. |
| IDs 17–21: Tool Desk, route aliases, Studio panel/toolbar geometry, Run label, first page render | Chromium loaded `/tool-desk`, followed both aliases, toggled Studio Pages at desktop width, measured the Run label at 390 px, and opened a real one-page PDF in Studio. | Directory and both routes resolved, toolbar remained visible beside the Pages panel, no midword label break was found, and first page canvas rendered in 1.035s. Evidence: `browser-p0.json` cases `tool_desk_view_and_tool_route_aliases`, `studio_sidebar_toggle_does_not_cover_toolbar`, `run_button_label_does_not_split_midword`, `studio_first_page_canvas_paints_within_5_seconds`. |
| ID 5: summary citation nondeterminism | Set all Executive Brief provider calls to temperature zero and verified provider wire payloads for OpenAI-compatible, Anthropic, and Gemini. Repeated browser summary calls against the local deterministic offline mode. | Provider payload tests passed; both offline runs returned identical text and the same page chips, exactly aligned with inline citations. Live provider nondeterminism remains unverified; item partial. Evidence: `browser-p0.json` (`executive_brief_repeated_citation_parity`) and tests in v23 suite. |
| ID 8: Remove Pages first-attempt latency | Built a content-heavy 10-page PDF of 5,050,539 bytes and removed page 2 via two local browser `/api/jobs` runs. | Both first attempts completed without retry in 1.621s and 1.533s. Downloaded PDFs were parsed: each has 9 pages and former page 3 now appears at page 2. Exact owner fixture unavailable. Evidence: `browser-p0.json` (`remove_pages_first_attempt_latency_on_5mb_pdf`). |
| ID 98: Cashfree | No real payment or production credentials were used. | Sandbox can be exercised by existing regression; production keys and one real payment are owner-only. Guest checkout/account-required wording still needs an explicit local browser retest. |
| IDs 317/318: Protect and Sign downloads | Chromium at local server, signed-in disposable Pro, two rounds each. Captured downloads and parsed actual PDFs. | Protect: 1,479 bytes twice, one encrypted page each. Sign: 1,554 bytes twice, signer text present on one page each. No page errors. `browser-p0.json`. |
| ID 340: fixed mobile bar covers actions | Added bottom safe-area padding to the tool shell. Chromium at 846×712 uploaded a synthetic PDF, scrolled the action into view, measured geometry for Split, Merge and Compress. | All three primary actions were above/nonintersecting the fixed bar (`button bottom 380px`, bar top 646px). `browser-p0.json`. |
| ID 341: breadcrumb collapses | Ancestor breadcrumb items do not flex-shrink; active leaf alone may shrink. | Chromium at 1280×800 and 1024×768 showed full `Paperplane / Workspace / AI Document Intelligence`; no single-letter collapse. `browser-p0.json`. |
| ID 314: Executive Brief PDF download | Delayed object-URL revocation after anchor click. Invoked the production browser-side PDF generation/download path in Chromium. | Captured a 986-byte, one-page PDF; opened with PyMuPDF and verified the synthetic content. `browser-p0.json`. |
| 44-operation content browser sweep | Local Chromium audit via `scripts/browser_v21_catalog.py` against isolated app/database. | 39 completed; OCR, Summarize, Translate unavailable without local services; PDF/A failed in this container; HTML-to-PDF was correctly blocked by SSRF policy. Full item-level results: `browser-catalog.json`. This is not 44/44 successful functionality. |

### Post-change test status

Focused regressions: `tests/test_launch_audit_v23.py` and `tests/test_ai_workflows.py` pass. The standalone account/feedback persistence and v23 fraction-gate checks pass. This earlier 490-test note is superseded by the continuation below.

## Continuation: targeted fixes, browser checks, and final local suites

Additional code work covered checklist defects 315, 319, 321, 323, 333–335, 337–338, 342–343, and 352:

- Studio opens now show a loading overlay immediately; a delayed second open and first Text-tool activation were checked in Chromium.
- Compression stores the explicit missed-target warning in the job record. A noisy image PDF sent through a real local Chromium `/api/jobs` request with the 100 KB preset returned the actual output size, the warning, and a rendered non-black page.
- Progress uses the same rounded measured upload percentage for the bar and label; processing uses an indeterminate bar instead of a fabricated percent. Toast pointer hit testing confirmed the notification cannot capture the underlying click.
- PDF metadata editing retains unedited author/creator/producer/date fields. A browser-produced PDF was downloaded and parsed.
- PDF-to-Markdown no longer uses the storage filename as its H1; glyph geometry restores spaces in the targeted no-space regression. The local browser download was content checked.
- Two-dimension photo resizing letterboxes instead of stretching; the browser downloaded and inspected a 100×100 output.
- Smart Metadata fallback rejects common attribution boilerplate and favors a prominent centered heading; synthetic PDF regression passes. The reported real source PDF was unavailable.
- Local-result Blob handoff opened the merge result in Studio and rendered the page. Full coverage across every local PDF/photo tool, route changes, and reloads remains open.
- The signed guest quota was exercised in a separate local browser context: ten accepted server jobs were reflected as 10/10 usage, and job eleven was rejected with HTTP 402 / `TIER_LIMIT_REACHED`.
- Pricing now renders limits for every operation and tool pages link to the table. The privacy copy marks itself as a draft and removes unsupported provider-training and at-rest-encryption claims. `/refund`, `/contact`, and `/status` now resolve to pages that clearly disclose missing owner-approved policy/monitoring details instead of returning 404.
- ID 45 Studio/footer regression: Chromium first exposed that a trailing `.app-global-footer { visibility: visible }` rule overrode the earlier hide-until-scroll rule. Removed the override. A subsequent 41-check Chromium run confirmed no Studio save banner, four toolbar rows (166 px, 33 buttons), no desktop horizontal overflow, hidden footer at initial position, and footer reveal after scrolling. Mobile and every other view/width are not yet covered, so the item remains partial. Evidence: `browser-p0.json` (`studio_desktop_has_no_persistent_save_banner_and_fits`), source fix in `web/assets/styles.css`.

ID 3 Studio retention was rechecked in guest Chromium twice: delete page 1 from a 10-page fixture, confirm persisted nine-page IndexedDB content, reload, wait 30 seconds, and verify page count plus former page 2 text. Both rounds had zero page errors; see `browser-p0-round8.json` and `browser-p0-round9.json`.

ID 49 export retries: controlled Chromium tests aborted the first POST and separately injected a first-attempt HTTP 503. Both retry paths succeeded in two consecutive runs. Each downloaded an 867-byte PDF verified by PyMuPDF for page count and expected source text. The v23 prompt keeps closure pending the owner’s decision; see `browser-p0-round12.json` and `browser-p0-round13.json`.

ID 184 guest quota isolation was repeated twice using separate Chromium contexts: one accepted operation showed 1/10 for the active guest and 0/10 for the independent browser; the active guest then reached 10/10 and the eleventh operation returned 402. Evidence: `browser-p0-round21.json` and `browser-p0-round22.json`.

ID 296 trusted-proxy attribution was rechecked in two browser rounds; two distinct forwarded client IPs were stored on the matching audit events. A focused regression additionally verified the untrusted direct-client spoof case is ignored. Evidence: `browser-p0-round23.json`, `browser-p0-round24.json`, and `tests/test_launch_audit_v10.py::test_trusted_proxy_ip_is_attributed_and_untrusted_forwarding_is_ignored`.

ID 293 Flatten was checked in a local browser with a real Highlight annotation: the downloaded PDF retained the source text, rendered the yellow highlight appearance, and had zero active annotations. Evidence: `browser-p0-round25.json` and `tests/test_launch_audit_v20.py::test_flatten_bakes_highlight_annotation_and_removes_annotation_record`.

ID 292 Split was checked in Chromium on a labeled 10-page PDF. The `1-2`, `1`, and `1,1,2` outputs were downloaded and each page's text/count was checked against the exact requested pages. Evidence: `browser-p0-round26.json` and `tests/test_launch_audit_v20.py::test_split_ranges_return_the_requested_page_content_and_count`.

Latest local browser evidence: `browser-p0-round3.json` through `browser-p0-round34.json`, plus `browser-p0.json`; rounds 3–5 each contain 18 assertions and zero page errors, rounds 6–7 cover pricing/legal routes, rounds 8–9 verify ID 3 retention, rounds 10–13 verify ID 49 retry paths, rounds 19–20 verify ID 168 first paint/Studio restore, rounds 21–22 verify ID 184 guest quota isolation, rounds 23–24 verify local ID 296 proxy attribution, round 25 verifies ID 293 flattening, round 26 verifies ID 292 split ranges, and round 29 verifies ID 137 Studio theme synchronization and Studio restore toast geometry; round 30 verifies ID 7 SPA workflow/FAQ copy transitions from Merge to Split; round 31 verifies ID 22 upload wording and empty-state restoration after clearing chat; round 32 verifies ID 23 authenticated Free quota enforcement; round 33 verifies ID 24 AI readiness-status consistency; round 34 verifies ID 26 Aadhaar redaction in the downloaded PDF. The latest P0 run covers 60 checks with zero page errors. The latest route/viewport matrix passed 176/176; ID 36 checked rendered copy on 46 public/tool routes, ID 167 checked headings across all 44 tool routes, ID 221 checked an authenticated first-visit feedback prompt and dismissal at 390×844, ID 205 visually/measurably checked the desktop workspace navigation pill, and ID 313 measured signature/security dialogs at 390/820/1366/1920 px (8 measurements) with no horizontal clipping and internal scrolling on the phone security dialog. ID 90 was tested separately: two four-job concurrent Merge rounds completed and downloaded valid PDFs, and the OTP header-leak test passed.

The current 506-test suite passed twice after the final tree update (runs 3 and 4), with one existing Starlette/httpx deprecation warning on each run. Logs: `pytest-final-run3.log`, `pytest-final-run4.log`.

After the mobile Pricing limits table was converted to stacked rows, `node --check web/assets/app.js` passed and the full 506-test suite passed twice more (runs 5 and 6). The local Chromium mobile visual sweep passed 9 view/route combinations (Home, Merge, Pricing at 320×740, 390×844, and 820×900), with no document overflow or page errors. At both 320 and 390 px it separately checked all 44 Pricing rows and each of the five displayed data labels; evidence and screenshots: `browser-mobile-visual.json`, `mobile-pricing-limits-row.png`, and 320/390/820 px screenshots.

Live public-site smoke: downloaded TotPDF's five-page numbered sample, confirmed the fixture's source text/page count, uploaded it to the deployed Merge and Split routes in server mode using a fresh guest browser, and opened/content-checked the results. Two copies merged to 10 searchable pages; split-all returned five one-page PDFs in source order 1–5. No page errors and no payment. Evidence: `browser-live-smoke.json`, `live-merge-10-pages.pdf`, `live-split-5-pages.zip`. This produced two transient job records on the deployed service; no production account/admin state changed.

Intermediate repeat runs found three Cashfree tests reusing fixed emails in the persistent test database; changed those probes to unique addresses. They also exposed two API-doc tests asserting the prior production redirect behavior; updated them to assert the new working spec route while keeping default FastAPI `/openapi.json` disabled. The final post-change full suite passed **506 tests twice**, one existing Starlette/httpx deprecation warning each. This does not complete the 353-item checklist. Production-provider, deployment, owner-wording, and broad per-tool checks remain open as stated in `FINAL-REPORT.md`.



ID 137 theme and mobile toast overlap follow-up: first screenshot review caught that the canvas surround remained dark after light controls were fixed. Added theme-aware Studio stage, empty-state, and loading surfaces. A second screenshot then exposed the restore toast over the mobile toolbar; `showToast` now positions Studio notices below the measured variable-height toolbar and tracks viewport resize. Chromium exercised the real Settings dark→light controls, reload persistence, and restore toast placement on desktop and 390 px mobile. Both toast geometries had zero toolbar intersections; the mobile document width stayed 390 px. Evidence: `browser-p0-round29.json`, `studio-loaded-390.png`; implementation: `web/assets/styles.css`, `web/assets/app.js`.


ID 7 SPA workflow/FAQ transition: started on the Merge tool page, then selected Split from the in-app sidebar. The downloaded data contexts had distinct headings and FAQ labels. After navigation, the visible SEO workflow contained the Split heading and FAQ and neither the prior Merge heading nor prior Merge FAQ. Evidence: `browser-p0-round30.json`; source behavior in `web/assets/app.js::syncSeoContent`. This verifies final SPA state on the local build, not every tool pair.


ID 22 AI empty state: a clean Chromium context showed the exact “Upload PDF to chat” instruction and Choose PDF control on desktop and 390 px mobile, with no content overflow. Then sent a general greeting and clicked Clear Chat; first reproduction left the empty-state card hidden after the conversation cleared. Fixed the clear handler to run `updateAiDocBar()` after resetting the conversation. The same browser test now verifies the empty state and upload copy return. Evidence: `browser-p0-round31.json`; source: `web/index.html`, `web/assets/app.js`.


ID 23 Free-tier quota bypass: in Chromium with the seeded authenticated Free account, submitted ten real `/api/jobs` requests and confirmed all returned 202, `/api/billing/status` reported 10/10, and request eleven returned 402 `TIER_LIMIT_REACHED`, tier `free`, usage 10. Evidence: `browser-p0-round32.json`.

ID 24 AI readiness status: in the controlled local environment with no provider credentials, `/api/ai/capabilities` reported `executive_brief_available: false`; public `/api/ai/test-connection` reported `configuration_missing`; authenticated `/api/admin/ai-health` also reported `configuration_missing` and `configured: false`. Evidence: `browser-p0-round33.json`.


ID 26 Aadhaar output verification: uploaded a synthetic PDF containing `1234 5678 9012` through the real Mask Aadhaar job, downloaded the returned PDF, and checked its text layer contains no first eight digits while retaining `9012` and the `XXXX XXXX` replacement. Rendered pixels inside the replacement text bounds had mean luminance below 90, confirming a dark rendered mask. Evidence: `browser-p0-round34.json`.


ID 25 catalog coverage: the saved local 44-operation catalog records 39 completed operations, OCR/Summarize/Translate unavailable due unconfigured local services, and PDF/A failure in this Windows host. These gaps leave the historical 38/41 tool pass only partially revalidated. Evidence: `browser-catalog.json`; production/provider and production-image checks remain open.

## Continuation: ID 1 provider retry/fallback visibility

The local v23 AI dispatcher already retries transient upstream failures and can use a separately configured provider. Extended its sanitized runtime health snapshot to record the last request outcome, a rate-limit flag, and whether the configured fallback handled the request; the admin response excludes credentials and raw provider bodies. Self-review found four production workers, so the state is persisted in the shared SQLite settings table, with an allowlist that stores no provider body or credential. State for an old provider is not presented as the current provider's status. The Admin AI Settings health banner now explains an HTTP 429 and fallback status. A controlled local integration test forced primary HTTP 429, ran translation through the fallback provider, parsed the downloaded one-page PDF, and verified the translated Spanish text. The test also checked health state and confirmed both test credentials were absent. A separate SQLite readback test verifies another worker can read the allowlisted state and that secret fields are discarded. Local Chromium opened `/admin` using controlled admin API responses and verified the visible health banner, rate-limit wording, fallback wording, credential absence, and cache-busted `admin.js?v=15` (5/5 checks, no page errors). Evidence: `tests/test_ai_workflows.py::test_translation_falls_back_after_primary_rate_limit_and_reports_admin_health`, `tests/test_launch_audit_v23.py::test_ai_provider_health_is_shared_storage_sanitized_and_worker_readable`, `browser-id1-admin-health.json`, `browser-id1-admin-health.png`. The final two complete suite runs passed 508 tests each: `pytest-cont-id1-run7.log` and `pytest-cont-id1-run8.log`.

Additional local regression: the translation acceptance gate used to count source characters only, allowing one long block to make a result appear sufficiently translated even when most shorter blocks remained in the source language. It now requires at least 50% of both blocks and source characters, surfaces both coverage values for partial results, and rejects zero-block results before coverage evaluation so upstream 429/empty-result classifications survive. A deliberately imbalanced PDF (98% of characters but 25% of blocks translated) now returns HTTP 422 without offering a download in the local Chromium flow. Two local browser rounds × Spanish/Hindi each passed the 10-page 429→configured-fallback path and downloaded content-checked PDFs. Evidence: `browser-id1-imbalanced-coverage.json`, `browser-id1-10page-rate-limit-fallback.json`, `browser_id1_10page_rate_limit_fallback.py`, `tests/test_launch_audit_v23.py::test_translation_rejects_one_large_block_when_other_blocks_are_preserved`.

The deployed live 10-page Spanish/Hindi matrix still fails: the Spanish run marked complete contained only source markers, and the three other downloads were partial with source markers and no target-language markers. ID 1 remains PARTIAL pending deployed-provider/configuration correction and a passing content-discrimination retest.

## Continuation: ID 2 69-page summary mode

Chromium uploaded a generated 69-page labeled PDF through `/ai-intelligence`, clicked Generate Executive Brief, and downloaded/parsed the actual `/api/ai/summarize` response. With no local provider configured, the API returned HTTP 200 and `summary_mode=offline_extractive`; all 69 page citations were present, including page 69, and the final-page fact remained in the brief. The visible result contained exactly one “Executive Summary (Offline Analysis)” heading and a single corresponding mode badge. Screenshot review found the old header badge was statically “Synthesis”, even on local fallback responses; changed it to report “Offline Analysis”, “AI Synthesis”, or “Mode Unreported” based on the API field and explicit fallback heading. Chromium then tested the actual offline response and controlled provider-synthesis and missing-mode responses; all three labels matched, with no page errors. Evidence: `browser-id2-69page-summary.json`, `id2-summary-route.png`, `id2-summary-mode-mapping.png`; script `browser_id2_69page_summary.py`.

This closes a misleading local presentation bug and verifies the local 69-page offline path. The deployed summary omitted `summary_mode` in the prior public check and the provider-backed 69-page synthesis/quality requirement remains open.

ID 34 layout recheck: before and after the generated 69-page brief, measured AI Chat, Smart Metadata, and Executive Summarizer card rectangles at 390×844, 820×900, 1280×720, and 1920×1080. At desktop sizes, chat remained in the left column and both panels stayed in the right column. At 390/820, all three occupied the mobile stacked column. Every measured card stayed inside viewport bounds, the document had no horizontal overflow, and all three columns retained the same coordinates/widths after summary generation. This matches the stated reference composition; ID 34 is marked FIXED LOCALLY for the current build. Evidence is in `browser-id2-69page-summary.json` (`before_summary_layout`, `post_summary_layout_checks`).

## Continuation: IDs 37, 39, and 242 local processing and AI directory grouping

### ID 242 current live mode reconciliation

The contradictory older live observations are resolved against the currently served UI. Two fresh Chromium contexts visited Merge, Split, Remove, and Rotate; every route returned HTTP 200 and loaded the local-processing checkbox checked with no `localStorage` override. In each context, changing Merge to Server survived reload and switching to Rotate, with zero page errors. This verifies the live default and preference behavior; content-checked local execution, quota separation, and controlled server fallback are evidenced separately in `browser-id37-id242-local-processing.json`. Evidence: `browser-live-id242-processing-mode.json`, harness `browser_live_id242_processing_mode.py`.

The latest Chromium run visited all 44 operation routes in a fresh context. Nine client-side workflows (Merge, Split, Remove, Rotate, Organize, Photo Compress, Photo Resize, Photo Merge, and Exam Photo Resizer) generated downloadable outputs; PDF page text/order/rotation and image decodability/dimensions were parsed, with zero `/api/jobs` requests for each local run. Toggling the visible switch to Server and back to Local survived reload. The test then replaced the frozen local PDF runtime with a controlled failing implementation; the UI disclosed that server retry uses the daily allowance, made exactly one server job, and returned a content-checked merge while retaining Local as the saved preference. No browser errors occurred. Evidence: `browser-id37-id242-local-processing.json`; `browser_id37_id242_local_processing.py`.

The v23 local Tool Desk now exposes AI Chat, Smart Metadata, and Executive Brief through its AI Intelligence workspace, rather than repeating three individual cards in the directory. AI Translate remains distinct; legacy `/ai-pdf-chat` still returns a working page. Local Chromium verified 41 distinct directory cards, the AI category filter, the workspace, the legacy route, and 390 px layout bounds. The live deployed page still shows the AI PDF Chat duplicate card and remains a post-deploy retest item. Evidence: `browser-id39-ai-tool-dedup.json`, `browser_id39_ai_tool_dedup.py`, and `id39-*.png`.

After the final client-side changes, `node --check web/assets/app.js` and changed-file whitespace checks passed. Two fresh full-suite runs passed 508 tests each: `pytest-cont-id39-run1.log` and `pytest-cont-id39-run2.log` (one existing Starlette/httpx deprecation warning per run).

## Continuation: IDs 340 and 341 mobile P0s

Chromium with enabled Run buttons and uploaded PDF fixtures reproduced the bottom-navigation obstruction at 820 px: the button center landed under the fixed mobile bar. The new mobile CTA dock stays 8 px above the nav, and `main-area` has enough bottom scroll padding for the CTA and nav; all nine Merge/Split/Compress hit tests passed at 320, 390, and 820 px with no overlap, interception, overflow, or page errors. For ID 341, the breadcrumb's current-page segment was measured at zero width inside a 56.6 px trail at 820 px. On widths up to 900 px the shortened breadcrumb is hidden and the mobile workspace indicator now says “AI Intelligence”; 320/390/820 px all fit with no overflow. Evidence: `browser-p0-340-341-mobile-layout.json`, `browser_p0_340_341_mobile.py`, and `p0-340-split-*.png` / `p0-341-ai-*.png`.

## Continuation: ID 314 Executive Brief PDF download

Local Chromium generated the actual 69-page offline Executive Brief and clicked its PDF download button in two consecutive runs. Both browser downloads were captured, saved, opened with PyMuPDF, and checked for a valid multi-page PDF, the Executive Summary heading, and findings from both source page 1 and source page 69. Each was 4,523 bytes / 3 pages, and neither run produced browser page errors. Evidence: `browser-id314-summary-pdf-round1.json`, `browser-id314-summary-pdf-round2.json`, and `id314-executive-brief.pdf`; harness: `browser_id314_summary_pdf.py`.

The complete current P0 Chromium sweep was rerun after correcting two timing assumptions in its harness (wait for initial route reconciliation before the footer test, and hold `/api/auth/me` long enough to capture the signed-in first paint). It completed all 60 assertions with zero page errors. Evidence: `browser-p0.json`; harness: `browser_p0.py`.

## Continuation: ID 173 Rotate copy accuracy

Opened `/rotate-pdf` in Chromium and checked the rendered SEO copy, not only the server catalog: the heading says “Rotate the entire PDF document,” and the intro says a single angle applies to every page, with selected-page rotations in Page Organizer. Followed the Page Organizer related link and confirmed the SPA showed the reorder-page workflow. No obsolete “page-by-page rotation workflow” copy or browser page errors. The existing focused catalog regression test also passes under the full suite. Evidence: `browser-id173-rotate-copy.json`, `id173-rotate-copy.png`, `tests/test_launch_audit_v23.py::test_rotate_landing_copy_matches_whole_document_behavior`.

## Continuation: ID 338 Smart Metadata title

Recreated the discriminator in a one-page PDF: a small Google attribution/permission notice precedes a large centered “Attention Is All You Need” title. Uploaded through AI Intelligence and clicked Extract Structured Entities. The `/api/ai/extract` response and the opened Developer JSON view both report the paper title; attribution is not selected as the document title, contacts/topics remain available, and the browser recorded zero page errors. Evidence: `browser-id338-smart-metadata-title.json`, `id338-smart-metadata-title.png`, `browser_id338_smart_metadata_title.py`, and `tests/test_launch_audit_v23.py::test_smart_metadata_skips_attribution_and_uses_prominent_title`.

## Continuation: ID 315 Studio fresh first-open tools

In two independent fresh Chromium contexts, uploaded a new one-page PDF through Studio's actual file input and waited for the first page canvas to render. Without reloading, selected Text, clicked the page, and verified the text input panel appeared; then selected Stamp, clicked the page, and verified the stamp picker appeared. Both runs had zero page exceptions and zero unexpected console errors. The observed 401 was the expected guest `/api/auth/me` response. This exercises the reported first-open failure path; the historical live null-style exception itself did not occur locally. Evidence: `browser-id315-first-open-tools.json`, `id315-first-open-tools-round1.png`, `id315-first-open-tools-round2.png`; harness: `browser_id315_first_open_tools.py`.

## Continuation: ID 316 PDF Metadata JSON view/export

Added an accessible preview and JSON download to the Metadata tool result. An initial browser experiment showed that parsing the output by fetching its guest PDF download URL consumed the one-time guest capability, leaving the expected PDF download to fail. Reworked this so the owner-scoped job status response supplies an allowlisted summary read from the completed PDF; opening or exporting the summary does not access or consume the PDF download. Chromium changed title, author, and subject, downloaded/parsed the JSON, then downloaded the PDF and matched title, author, subject, keywords, creator, producer, and dates to PyMuPDF metadata. The PDF was 990 bytes / one page, JSON download was 316 bytes, and the browser had zero page errors. A regression test proves job status does not consume the guest capability and the PDF can still be downloaded once. Evidence: `browser-id316-metadata-json-export.json`, `id316-metadata-json-export.png`, `browser_id316_metadata_json_export.py`, `tests/test_launch_audit_v23.py::test_metadata_job_exposes_output_metadata_without_consuming_guest_download`.

After the ID 316 code change, two complete full-suite runs passed with 509 tests each: `pytest-cont-id316-run1.log` and `pytest-cont-id316-run2.log`.


## Continuation: IDs 320, 327, 330, 331, 332, and 339

ID 320: Chromium uploaded and rendered a one-page PDF in a clean Studio browser, clicked Clear Studio PDF with no other Paperplane tab open, and verified the document cleared with no “Close other tabs” warning. The handler now only gives the other-tab guidance for the explicit IndexedDB blocked error; other storage failures explain that browser storage could not be cleared. Failed database opens no longer poison the cached promise, and database connections close on version changes. Evidence: `browser-id320-clear-studio.json`, `id320-clear-studio.png`, `browser_id320_clear_studio.py`.

For ID 327, Chromium opened PDF to JPG and verified the selected-pages FAQ honestly states the current all-pages behavior and directs users to Split first. The same browser pass confirmed the footer label “Temporary results” for `/history` (ID 330), Light Paper is marked as the default active theme (ID 331), `/developers` sets a developer-specific document title (ID 332), and the FAQ contains eight questions covering pricing, limits, privacy, refunds, and support (ID 339). The server regression test checks the SEO capability text, navigation label, theme choice presence, and FAQ count. Evidence: `browser-id327-330-331-332-339.json`; test `tests/test_launch_audit_v23.py::test_seo_and_navigation_copy_matches_pdf_tool_capabilities`.


## Continuation: ID 344 guest auth response and badge state

Changed `/api/auth/me` to return HTTP 200 with `authenticated: false` for guest and revoked sessions. The browser opened `/tool-desk`, `/merge-pdf`, `/settings`, `/faq`, and `/history`; all five auth responses returned 200. There were zero auth 401s, browser page exceptions, or console errors. On `/merge-pdf`, the plan badge was hidden while auth was pending, then displayed “Free Guest Tool” after the guest response resolved. Updated tests cover anonymous profile, OTP pending signup, revoked logout session, and the production profile contract. Evidence: `browser-id344-guest-auth.json`.

The complete suite then passed twice: 510 tests in `pytest-cont-id344-final-run1.log` and 510 in `pytest-cont-id344-final-run2.log`, each with four deprecation warnings.


## Continuation: ID 329 history disclosure

The `/history` page now clearly states that Paperplane does not keep a job or download history list. Its page heading and SPA browser title say “Temporary results — no saved history,” and the footer link now reads “Temporary results.” Chromium verified the rendered disclosure and matching browser title; the focused server regression test checks the route HTML. Evidence: `browser-id327-330-331-332-339.json`.


After the ID 329 page title and history disclosure updates, the full suite passed twice again: 510 passed in `pytest-cont-id329-final-run1.log` and `pytest-cont-id329-final-run2.log`, each with four deprecation warnings.


## Continuation: ID 43 delayed Studio deletion and Undo

On a 10-page PDF in Chromium, delayed the successful Studio page-delete result by 12 seconds. The Undo banner stayed absent before the updated document loaded; after the resulting 9-page document rendered, the Undo button remained visible and enabled for another 12 seconds. Clicking it restored the original 10-page document. There were zero page exceptions. This verifies the undo window begins after deletion/reload completes rather than expiring during the operation. Evidence: `browser-id43-slow-delete-undo.json`, `id43-slow-delete-undo.png`, harness `browser_id43_slow_delete_undo.py`.


## Continuation: ID 41 PDF to Markdown processing budget

Added an explicit 480-second bound for long PDF-to-Markdown conversion through `run_converter_with_timeout`; the operation does not retry automatically and suggests splitting into page ranges if the budget is exceeded. The existing 4.98 MB / 69-page project `notes-69page.pdf` was uploaded through the visible `/pdf-to-markdown` route twice. Both runs returned HTTP 202, downloaded 130,305-byte Markdown in 4.7–5.3 seconds, contained exactly 69 generated page sections and first/last-page content, did not leak the job identifier, and produced no page errors. A focused test verifies the budget and timeout metadata. Evidence: `browser-id41-markdown-69page.json`, `id41-markdown-round1.png`, `id41-markdown-round2.png`; test `tests/test_launch_audit_v23.py::test_pdf_to_markdown_uses_a_bounded_long_document_budget`.

Full suite after this change: 511 passed twice in `pytest-cont-id41-markdown-run1.log` and `pytest-cont-id41-markdown-run2.log`, each with four deprecation warnings.


## Continuation: ID 50 Developer API copy

The rendered `/developers` page now has a single “Copy Snippet” label and the intro has a space between “API keys” and the parenthesized `sk_live_...` example. Verified the rendered text in Chromium and added a focused server HTML regression test. Evidence: `browser-id327-330-331-332-339.json`; test `tests/test_launch_audit_v23.py::test_developer_api_copy_has_one_copy_label_and_spaces_before_key_example`.


## Continuation: ID 38 combobox and progress states

Shortened the Split all-pages select label to “All 10 pages as PDFs (ZIP)” and the SSC preset to “SSC Photo (3.5×4.5 cm · 20–50 KB).” Chromium measured each label against the actual option field width at 390 and 1366 px; both fit. It also exercised Exam Resizer, Flatten, and Sign processing states; the progress bar was indeterminate with “Processing” status and no fabricated percent, and there were no page errors. ID 38 also mentions guessed-slug 404s, but the extracted source truncates before listing those paths, so that portion remains open pending the exact paths. Evidence: `browser-id38-options-progress.json`; harness `browser_id38_options_progress.py`.


ID 38 guessed-slug follow-up: added canonical redirects for `/resize-photo` and `/photo-resize` → `/resize-image-dimensions`, `/compress-photo` → `/compress-image-online`, and `/add-page-numbers` → `/add-page-numbers-to-pdf`. In two Chromium rounds, all four followed to the expected page and title; scanning Tool Desk card anchors found none of those stale paths. Focused route alias tests pass. Evidence: `browser-id38-legacy-slugs.json`, tests `test_132_181_route_aliases_resolve` and `test_common_guessed_tool_slugs_redirect_to_canonical_pages`.


Full suite after ID 38 changes passed twice: 516 tests in `pytest-cont-id38-full-run1.log` and 516 in `pytest-cont-id38-full-run2.log`, each with four deprecation warnings.


## Continuation: ID 40 plan-name consistency

The pricing page and the account/client views used inconsistent names for the exam and student plans. Standardized the public pricing titles and the exam account label to the billing catalog: Free, Exam Pass, Student & Educator, and All-In-One Pro & Developer. Two independent Chromium page loads rendered all four exact names and reported zero page errors. The targeted regression test compares every pricing card name against `public_pricing_catalog()` and checks the client account label. Evidence: `browser-id40-plan-names.json`, two screenshots, and `tests/test_launch_audit_v23.py::test_public_plan_names_match_billing_catalog_across_pricing_and_account_views`.

## Continuation: IDs 44 and 46 AI banner and quota copy

Chromium at 390 px and 1366 px opened AI Intelligence and confirmed the obsolete claim that the PDF and full chat history are saved in this browser is absent. In the same rounds the Tool Desk sidebar displayed “Operations Today” and the live guest usage count; Settings distinguished Free daily operations from paid per-file size and batch limits. The contradictory “Unlimited · 500 MB · 100 files” phrase was absent, with zero browser page errors. Evidence: `browser-id44-46-ai-quota-copy.json`, `id44-46-390.png`, `id44-46-1366.png`; focused regression test `tests/test_launch_audit_v23.py::test_ai_workspace_and_quota_copy_avoid_outdated_storage_and_limit_claims`.

## Continuation: IDs 28, 29, and 42 scope review

ID 28: the current 44-operation Chromium catalog contains content-checked Merge, PDF-to-JPG, Protect, and Fill Form downloads. OCR could not run on this host, so the output-content item remains partial. ID 29 remains partial: the earlier v23 browser rounds verify isolated guest quota and valid-password Unlock, and Cashfree order creation has mocked tests; this does not cover live checkout, every guest flow, production TLS, or a built production Docker image. ID 42 remains partial: moved the primary chat/upload card before the How-To explainer at viewport widths through 900px; desktop keeps its existing reference order. Two real Chromium rounds at 320×740, 390×844, and 820×1180 measured chat at y=212 (AI topbar ends y=200), confirmed the upload control is above the fixed mobile navigation, uploaded a one-page PDF and observed the loaded-document bar, and found no horizontal overflow or page errors. Two 1366×900 checks confirmed the desktop how-to-before-chat ordering remains unchanged. The prior 44-route/four-width matrix still passes. Rendered v23 PDF page 61: it names screenshot 5 but contains no embedded reference image and truncates the design description after 'clean …'. Keep the exact all-view redesign partial rather than guessing from incomplete requirements. Evidence: `browser-id42-local-ai-layout-round1.json`, `browser-id42-local-ai-layout-round2.json`, `browser_id42_local_ai_layout.py`, `source-id42-page61.png`, `web/assets/styles.css` (`styles.css?v=51`).

## Continuation: IDs 51, 52, 53, 55, and 56 layout and waitlist checks

At 1104 px, Chromium verified the Settings Storage & Privacy secondary label stays within its selected card, the paid Student plan's sidebar quota reads “Operations Today / No daily operation cap” without overflow, and each Windows/macOS/Linux/Android/iOS “Join Waitlist” action selects that platform and leaves the signup form visible. The AI Chat empty prompt is fully below its header, but the checklist's after-Clear/document-still-present case remains untested (ID 52 stays partial). A 67-page PDF loaded in Studio at 1104 px; the toolbar and Export button remained visible at their initial positions. The scroll action did not establish the original scrolled screenshot state, so ID 53 remains open. Evidence: `browser-id51-52-53-55-56.json`, `id51-52-53-55-56-1104.png`, `browser-id53-studio-header-scroll.json`, `id53-studio-header-before-scroll.png`, `id53-studio-header-after-scroll.png`.

ID 52 follow-up: two isolated Chromium contexts each uploaded a one-page PDF through AI Intelligence, confirmed its active document was visible, clicked Clear, and verified the active document bar was hidden, the page-citation empty state was restored, and the PDF's unique text marker was absent from the workspace. No page errors. Evidence: `browser-id52-ai-clear-document.json`, `id52-ai-clear-round1.png`, `id52-ai-clear-round2.png`.

## Continuation: ID 72 mobile View in Studio scroll reset

In two 390×844 Chromium rounds, ran Merge using Local processing with two real one-page PDFs, scrolled to the result at window scroll 1986 px, and clicked “View in Studio.” The transition reset the window to y=0, loaded both merged pages, and kept the Studio toolbar and Export control within the viewport. No browser page errors. Evidence: `browser-id72-mobile-view-studio-scroll.json`, `id72-mobile-result-round1.png`, `id72-mobile-studio-round1.png`, and the round 2 screenshots.

## Continuation: ID 73 Studio export after responsive resize

Reproduced a control restoration failure after resizing Studio from 390 px to desktop: the Export group had been moved to a mobile slot, while the resize selector only searched its former direct parent. Updated `placeStudioControl` to recover the node from its mobile slot, return it to its desktop origin, and use `moveBefore()` when supported with the existing append/insert fallback. Two Chromium rounds loaded a five-page PDF at 390×844, focused Export, resized to 1366×900, navigated through pages 4 and 5, and verified focus remained on Export. Both output downloads parsed as five-page PDFs and contained every unique source marker. `node --check web/assets/app.js` passed; browser evidence: `browser-id73-export-after-resize.json`, `id73-resize-round1.png`, `id73-resize-round2.png`; harness `browser_id73_export_after_resize.py`.

## Continuation: ID 77 mobile Studio page actions

Reproduced the clipping at 390×844: in Organize mode, the Resize, Earlier, Later, and OCR controls overflowed to the right beyond the mobile panel. Changed the Organizer action groups to wrap into rows and let the batch panel scroll vertically only when its contents exceed the available space. Chromium then measured all four 44 px controls within the viewport and action panel, the action row had no horizontal overflow, and the Zoom selector showed 100% rather than a truncated value. Zero browser page errors. Evidence: `browser-id77-mobile-studio-page-actions.json`, `id77-mobile-studio-actions.png`; harness `browser_id77_mobile_studio_page_actions.py`.

## Continuation: ID 80 mobile Settings width

At both 320 px and 390 px, authenticated Chromium measured the Settings page and all five tabs. The page and tab strip fit within the viewport with no horizontal overflow, every tab button fit its label and accepted a click, and there were zero page errors. Evidence: `browser-id80-mobile-settings.json`, `id80-settings-320.png`, and `id80-settings-390.png`; harness `browser_id80_mobile_settings_overflow.py`.

## Continuation: IDs 82 and 84 first-paint and Escape behavior

ID 82: all nine reported tool routes returned HTTP 200 and had substantive `.seo-content` on `DOMContentLoaded`; no route displayed a “Loading … details” placeholder immediately or after 250 ms. ID 84: the mobile sidebar closed on Escape and reset `aria-expanded` to false. When the Upgrade and Auth overlays were both open, first Escape closed only Auth and left Upgrade visible; second Escape closed Upgrade. No page errors. Evidence: `browser-id82-tool-details-first-paint.json`, `browser-id84-escape-overlay-stack.json`, `id84-mobile-drawer-after-escape.png`, `id84-overlays-after-first-escape.png`.

ID 85/87 mobile follow-up: on the Merge result card at 390 px, two rounds measured Download File, View in Studio, Process Another File, and All Tools within the viewport and confirmed none were covered; the run button was already checked against the bottom bar at 320/390/820 px in IDs 340/341. Follow-up rounds exercised actual Split and Rotate outputs at 320×844 and 390×844: ZIP pages and rotated PDF text/orientation were checked; all result actions fit, stayed unobscured, and the success toast overlapped neither Run nor the bottom bar. The 38 px Download File control was raised to 44 px and cache-busted as styles.css?v=50. This closes the result-card/toast cases locally. The same earlier rounds measured all four bottom-navigation labels at 11 px, closing ID 87. Evidence: `browser-id85-mobile-result-cards.json`, `browser_id85_mobile_result_cards.py`, `browser-id72-mobile-view-studio-scroll.json`, `browser-p0-340-341-mobile-layout.json`.


ID 92 New Page: two fresh Chromium contexts uploaded and rendered a one-page synthetic source PDF. Clicking New Page opened the confirmation dialog. Cancel left the source page count/canvas and selected file intact. Confirm rendered a single 596×842 A4 canvas. Reload returned to the normal empty Studio (`0` pages), not a failed zero-byte PDF, and showed no Studio error, toast, page exception, or console error. Evidence: `browser-id92-new-page-confirmation.json`, `id92-blank-page-round1.png`, `id92-blank-page-round2.png`; harness `browser_id92_new_page_confirmation.py`.


ID 119 Studio Organize mobile: at 390×844 in two fresh Chromium contexts, uploaded a five-page synthetic PDF, selected Organize, verified `.studio-pages-open`, and measured the visible thumbnail panel at x=8/y=345/w=374/h=300 with five page cards. The Pages drawer control closed it; no page errors. Evidence: `browser-id119-mobile-organize.json`, `id119-organize-mobile-round1.png`, `id119-organize-mobile-round2.png`; harness `browser_id119_mobile_organize.py`.


ID 104 Cloud Import auto-open: Chromium repeated actual PDF selection twice each on `/compress-pdf` and `/pdf-to-text`. On all four route/context combinations, `#cloud-modal` remained hidden while `cloud-modal-check.pdf` appeared in the selected-file list. No page errors. Evidence: `browser-id104-cloud-import-auto-open.json` and route screenshots; harness `browser_id104_cloud_autoopen.py`.


ID 115 Feedback widget: in two 390×844 Chromium contexts, measured the launcher against the final visible Tool Desk card and Studio zoom selector; neither overlapped. Open Auth and Upgrade backdrops caused `#pp-feedback-container` to compute as `display:none`. No page errors. Evidence: `browser-id115-feedback-overlap.json`, `id115-widget-studio-round1.png`, `id115-widget-studio-round2.png`; harness `browser_id115_feedback_overlap.py`. The test enabled the launcher explicitly because guest sessions do not meet the widget's signed-in prompt condition.


ID 123 local downloads: in two clean Chromium contexts, merged two marker PDFs with browser-local processing. Result metadata showed `merged-PDF.pdf · 998 B`, and the Download link remained visible for re-download. Each downloaded file parsed as a two-page PDF with both markers. No page errors. Evidence: `browser-id123-local-download-result.json`, `id123-local-merge-round1.png`, `id123-local-merge-round2.png`; harness `browser_id123_local_download_result.py`.


ID 126 standalone security entry points: in two Chromium rounds per route, uploaded `audit.pdf` on `/protect-pdf` and `/unlock-pdf`, clicked Open Security Audit & Sanitize, and confirmed the modal opened on the Audit tab. `window.PaperplaneSecurityForms.currentFile.name` was `audit.pdf` for all four cases; no page errors. Evidence: `browser-id126-security-entrypoints.json`; harness and screenshots.

ID 125 Advanced Studio toolbar: at 1920×1080, two Chromium runs measured the toolbar at 80px high; primary row controls fit within the viewport without horizontal overflow, while annotate tools occupy a second 36px row. Since the reported request asks for smaller tools and the full toolbar still spans two rows, left PARTIAL. Evidence: `browser-id125-studio-toolbar-geometry.json`, screenshots.


ID 139 Available Tools sidebar: two fresh Chromium rounds covered `/apps`, `/download`, `/privacy`, `/terms`, and `/mask-aadhaar-card-online`. Each returned 200; seven sidebar tool entries appeared on first paint and remained after 1.1 seconds. No page errors. Evidence: `browser-id139-sidebar-tools-deep-routes.json`, `id139-sidebar-deep-routes-round1.png`, `id139-sidebar-deep-routes-round2.png`; harness `browser_id139_sidebar_routes.py`.


P0 full browser rerun: after correcting Studio light-theme control foreground behavior and making the contrast probe wait for the theme state, local Chromium completed all 60 checks with zero page errors. ID 137 switched Dark→Light on the responsive Studio flow, verified the toolbar foreground and canvas colors, and verified persistence after reload. Evidence: `browser-p0.json`; `browser_p0.py`; CSS `styles.css?v=30`.


ID 127 Tool Desk links/routes: two local Chromium rounds confirmed all 41 tool cards render as distinct `<a href>` links and every canonical route returned HTTP 200. `/scan-pdf` redirects to `/scan-to-pdf`; `/tools` and `/all-tools` redirect to `/tool-desk` (301). No page errors. Evidence: `browser-id127-tool-card-routes.json`, `id127-tool-card-links-round1.png`, `id127-tool-card-links-round2.png`; test `test_tool_directory_aliases_redirect_to_canonical_pages` passed.


ID 128 Feedback lifecycle: two isolated signed-in synthetic accounts checked first-time launcher visibility. In one context, dismiss hid the launcher and persisted an account-scoped flag; Settings > Privacy reopened the form. In the second, selecting rating 4/Idea and submitting a synthetic comment returned HTTP 200 from the local feedback endpoint; the launcher hid after submit, and Settings > Privacy reopened it. No page errors. Evidence: `browser-id128-feedback-lifecycle.json`, `id128-feedback-settings-round1.png`; harness `browser_id128_feedback_lifecycle.py`.


ID 129 duplicate Sanitize action: two browser rounds uploaded a synthetic PDF through `/protect-pdf` and `/unlock-pdf`, opened Security Audit & Sanitize, selected the Audit tab, and counted the pane actions. Exactly one visible “Sanitize Document Now” button appeared in all four cases; no page errors. Evidence: `browser-id129-sanitize-action-count.json`, `id129-sanitize-dialog-round1.png`, round2; harness `browser_id129_sanitize_button.py`.


ID 131 1104px sidebar clipping: at 1104×760 in two Chromium rounds, loaded `/download` and `/developers`. The download heading began at x=347; the developer Limits & Reset card began at x=867.5; both were fully in bounds to x=1104, did not intersect the sidebar (x=0..270), document width stayed 1104, and there were no page errors. Evidence: `browser-id131-1104-sidebar-layout.json`, `id131-1104-layout-round1.png`, round2; harness `browser_id131_1104_layout.py`.


ID 135 tool limits copy: in two Chromium rounds, `/summarize-pdf` displayed “PDF files up to 50 MB each on Free and 500 MB each on paid plans · This tool processes 1 file per run”; `/mask-aadhaar-card-online` displayed the same size limits for PDFs and images and one file per run. No Merge mention or truncation; both included a Pricing limits link and had no page errors. Evidence: `browser-id135-tool-specific-limits.json`; harness `browser_id135_limits_copy.py`.


ID 142 search grammar: at 390×844, two local Chromium rounds searched “translate”. The live label read “1 tool found for “translate”” and the result was one `/translate-pdf` link; no page errors. Evidence: `browser-id142-search-singular.json`, `id142-search-grammar-round1.png`, round2; harness `browser_id142_search_grammar.py`.


ID 143 Developer banner copy: two Chromium runs at 1104×760 loaded `/developers`; the rendered banner ended with “dedicated API keys (sk_live_...)” and did not contain “keys(”. No page errors. Evidence: `browser-id143-developer-banner-spacing.json`, `id143-developer-banner-round1.png`, round2; harness `browser_id143_banner_spacing.py`.


ID 144 custom 404 navigation: the server-rendered unknown-route page now includes a responsive top navigation for Tool Desk, Studio, AI Intelligence, and Pricing. In two Chromium rounds at 390px and 1366px, the route retained HTTP 404, all mobile links fit within the viewport, document width matched viewport width, and no page errors occurred. Evidence: `browser-id144-404-navigation.json`, `id144-404-mobile-round1.png`, round2; `test_html_404_page_has_responsive_workspace_navigation` passed.


ID 145 empty uploader strip: in two browser rounds, inspected `/merge-pdf`, `/compress-pdf`, and `/rotate-pdf` before file selection. For each, `#file-list` had 0px height, zero children, no text, and no background spacer; its 14px gap beneath the dropzone was the only separation. No page errors. Evidence: `browser-id145-empty-uploader-space.json`, screenshots; harness `browser_id145_empty_uploader.py`.


ID 146 Translate disabled CTA: the isolated local environment reports its Translate provider unavailable. For the exact no-file CTA state, a controlled in-browser override marked the UI operation available, then Chromium rendered “Select files to continue” while disabled. At 390×844 in two rounds, foreground #5e6f72 on #f8faf9 yielded 5.02:1 contrast and opacity 1; no page errors. This controlled check does not establish a provider-backed enabled operation. Evidence: `browser-id146-translate-cta-contrast.json`, screenshots; harness `browser_id146_translate_cta.py`.


ID 147 inconsistent Feedback mounting: fixed prompt visibility so a prior `seen` flag no longer hides it on subsequent page loads; submitted/dismissed account flags still suppress it. Two signed-in synthetic account runs at 390×844 checked `/tool-desk`, `/scan-to-pdf`, `/merge-pdf`, and `/settings`; all four returned 200 and had the widget in DOM and visible. Dismissing then navigating to Merge kept the launcher hidden. No page errors. Evidence: `browser-id147-feedback-across-routes.json`, `id147-feedback-settings-round1.png`, round2; harness `browser_id147_feedback_routes.py`.


ID 148 Processing Mode state: two browser rounds checked local mode initially across Merge/Split, switched to Server, then loaded Rotate and Settings > Privacy (all unchecked with stored `server`), switched back to Local in Settings, then loaded Remove (checked with stored `local`). No page errors. Evidence: `browser-id148-processing-mode-persistence.json`, `id148-processing-mode-round1.png`, round2; harness `browser_id148_processing_mode.py`.


ID 156 Split mode label/output: two local Chromium rounds uploaded a 3-page marker PDF and selected “All 3 pages as PDFs (ZIP)”. Each download was `split-pages.zip` with page-1.pdf/page-2.pdf/page-3.pdf; every member parsed as one page with the matching page marker, in order. No page errors. Evidence: `browser-id156-split-label-output.json`, `id156-split-all-pages-round1.png`, round2; harness `browser_id156_split_mode.py`.


ID 157 AI welcome: two clean Chromium rounds sampled 150 ms, 1 s, and 2.5 s after page entry. All six samples had exactly one welcome container and heading, zero `.ai-message` greeting duplicates, and no page errors. Evidence: `browser-id157-ai-welcome-count.json`, `id157-ai-welcome-round1.png`, `id157-ai-welcome-round2.png`.

ID 159 Home first paint: two clean Chromium rounds sampled at DOMContentLoaded and at 100 ms, 500 ms, 1.5 s, and 3 s. No visible “Loading tools…” text, width overflow, or browser page errors appeared; each returned HTTP 200. Evidence: `browser-id159-home-first-paint.json`, `id159-home-first-paint-round1.png`, `id159-home-first-paint-round2.png`.


ID 162 Photo Resize 50%: two Chromium runs uploaded a 120×80 PNG with the 50% value retained in the form and downloaded valid 60×40 JPEGs. No browser page errors. Evidence: `browser-id162-resize-50-percent.json`, `id162-resize-50-round1.png`, `id162-resize-50-round2.png`.

ID 163 local Merge progress: the fixed progress renderer now labels local stages “Read files locally”, “Process in browser”, “Prepare output”, and “Ready”; server mode uses upload/server/download labels. Two local Chromium runs performed Merge, observed those local labels and no “Stream Upload”, then downloaded a two-page PDF containing both source text markers. No page errors. Evidence: `browser-id163-local-merge-progress-copy.json`, `id163-local-merge-progress-round1.png`, round2; `web/assets/app.js` (`app.js?v=38`).

After the ID 163 JavaScript change, `node --check web/assets/app.js` and `py_compile` passed; the full Python suite passed twice with 520 tests and four existing deprecation warnings each. Logs: `pytest-cont-id163-run1.log`, `pytest-cont-id163-run2.log`.


ID 158 “Process Another File”: in two Chromium rounds on `/merge-pdf`, clicked the result action, verified the result panel hid and file queue cleared, then uploaded a different pair and completed a second content-checked Merge. Both outputs were valid two-page PDFs with the correct respective marker pairs; no page errors. Evidence: `browser-id158-process-another-workflow.json`, `id158-process-another-round1.png`, round2. The action intentionally retains the selected tool, but does not navigate/reload into a loop or re-trigger the old result.


ID 160 Settings entry-point consistency: Chromium reproduced a 27-character Storage & Privacy mismatch: the modal said Local Processing was the default for five operations, while `/settings` said only four tools were available. Updated shared preference-aware copy and refresh it when opening/mounting Settings. Two Chromium rounds compared Account, Appearance, Billing, API, and Privacy on both entry points under Local and Server defaults; all tab text matched in all cases, with mode-accurate local/server copy and no page errors. Evidence: `browser-id160-settings-entrypoints.json`; `id160-{modal,page}-{local,server}-round{1,2}.png`.


ID 164 Studio signature warning: two Chromium rounds placed a typed signature on the first page and confirmed the editor dirty state. A reload triggered the native `beforeunload` confirmation both times; after accepting, the unsaved mark was absent. No page errors. Evidence: `browser-id164-signature-beforeunload.json`.

ID 165 Photo Resize preset retention: two Chromium runs selected Passport before uploading a 600×400 PNG; selection remained Passport after upload, and each downloaded JPEG was independently opened at 350×450. No page errors. Evidence: `browser-id165-photo-preset-retained.json`.

ID 166 Page Organizer local processing: two Chromium runs confirmed the Local Processing toggle, reordered a three-page marker PDF to 3,1,2, and content-checked matching output order. The runs made zero `/api/jobs` requests and had no page errors. Evidence: `browser-id166-organize-client-side.json`.

ID 176 stale toast/breadcrumb: after creating a visible toast on Merge, two Chromium runs selected Rotate through the sidebar; the toast disappeared and the breadcrumb immediately updated to Rotate PDF. Added stale-toast clearing on operation changes; no page errors. Evidence: `browser-id176-toast-breadcrumb-navigation.json`; `web/assets/app.js` (`app.js?v=42`).

ID 178 Photo & Exam navigation: two mobile Chromium rounds expanded the sidebar and selected Photo & Exam; the Photo filter and four Photo cards were visible, the AI view remained hidden, and no browser errors occurred. Evidence: `browser-id178-photo-suite-selection.json`.


After the ID 160 Settings entry-point copy change, `node --check web/assets/app.js` and `py_compile` passed. The full suite passed twice: 520 tests each, with four existing deprecation warnings. Logs: `pytest-cont-id160-run1.log`, `pytest-cont-id160-run2.log`.


ID 172 steps with explanatory body copy: changed SEO How-it-works cards to include cautious, control-accurate guidance; added three explanatory steps to the Tool Desk and the Apps waitlist. Chromium loaded all 44 tool routes at 390 and 820px (88 views), asserted three visible step bodies per tool, and checked no horizontal overflow. Tool Desk and Apps waitlist step copy also passed. No page errors. Evidence: `browser-id172-step-body-responsive.json`; screenshots `id172-download-waitlist-390.png`, `id172-tool-desk-820.png`.
ID 183 Home privacy claim and footer; ID 189 tablet navigation: changed pricing copy that promised “100% locally” to accurately say browser processing runs locally when Local Processing is selected, added a regression assertion, and used Chromium in two rounds to verify the footer and processing-language state. The same rounds visited all 44 tool routes at 820px and 1024px (176 route/viewport checks): 820px displayed one mobile topbar, hamburger, off-canvas sidebar and bottom workspace bar; 1024px displayed desktop navigation; neither width overflowed and there were no page errors. Evidence: `browser-id183-189.json`, `browser_id183_189.py`, `id183-home-390-round*.png`, `id189-tool-desk-*-round*.png`.

ID 188 Mask Aadhaar image upload: in two local Chromium contexts, uploaded the same synthetic 950×210 PNG containing a spaced 12-digit test number through `/mask-aadhaar-card-online`; the browser input advertised PDF/JPEG/PNG/WebP, each operation returned HTTP 200 and a valid PNG download. Pixel checks confirmed the first eight digits were blacked out and the last four were unchanged; no page errors. Evidence: `browser-id188-aadhaar-image.json`, `browser_id188_aadhaar_image.py`, `id188-aadhaar-image-round*.png`. The image support was already present in the current code; this closes the stale report claim with current end-to-end evidence.

ID 190 Feedback pill vs primary CTA: a signed-in Chromium reproduction on `/merge-pdf` at 390×844 confirmed the Feedback launcher intersected the enabled Run button. Raised the launcher 54px above the mobile navigation strip and bumped the asset URL. Two fresh signed-in rounds measured no intersection and completed the Merge action; both downloaded PDFs were parsed and their source marker verified. No page errors. Evidence: `browser-id190-feedback-cta.json`, `browser_id190_feedback_cta.py`, `id190-feedback-cta-round*.png`.

ID 191 Photo Merge grid regression: reproduced the exact 4× 2400×1800 input case twice in Chromium using the Grid layout. Each output decoded as 4800×3600 JPEG; pixel samples verified the four distinct input colors in the expected 2×2 cell positions, with no page errors. Added a non-uniform-size grid unit regression. Evidence: `browser-id191-variable-grid.json`, `browser_id191_variable_grid.py`, `id191-grid-round*.png`, and `test_merge_photos_grid_uses_distinct_row_and_column_extents`.

ID 192 plan labels/pricing: two local Chromium rounds opened the Upgrade modal and compared every displayed price to `/api/billing/status`. Values matched the current catalog (Free ₹0, Exam Pass ₹19, Student & Educator ₹49, All-In-One Pro & Developer ₹299); sidebar and topbar said “View plans”; old “Pro Power User”, ₹250, and ₹750 copy was absent. Removed an obsolete CSS comment that named the retired legacy prices; no browser errors. Evidence: `browser-id192-pricing-catalog.json`, `browser_id192_pricing_catalog.py`, `id192-pricing-round*.png`.

ID 193 Studio quota-blocked export: in two Chromium rounds, loaded a synthetic one-page PDF in Studio and intercepted the export API with a controlled structured HTTP 402 `TIER_LIMIT_REACHED` response. Both rounds displayed the readable quota message in the Upgrade modal; no `[object Object]` string or page error appeared. Evidence: `browser-id193-quota-export.json`, `browser_id193_quota_export.py`, `id193-studio-quota-round*.png`.

ID 194 Photo Compress 50 KB target: a 428,615-byte, 1200×900 high-detail JPEG reproduced the oversized-output condition when compressed by quality alone. Updated the compressor to retry with proportional downscaling whenever the target remains unmet. Two Chromium runs produced valid 960×720 JPEGs of 48,415 bytes for the 50 KB target; downloads decoded successfully and had no browser errors. Added unit regression. Evidence: `browser-id194-exact-photo-size.json`, `browser_id194_exact_photo_size.py`, `id194-50kb-round*.png`, `test_compress_photo_reduces_dimensions_when_quality_alone_misses_target`.

ID 195 Photo Resize empty inputs: in two Chromium contexts on `/resize-image-dimensions`, uploaded a real test PNG with the Custom preset and all width/height/scale inputs empty. The Run action stayed disabled with the “Enter a size or scale” message; a programmatic click produced no result and zero `/api/jobs` submissions. No page errors. Evidence: `browser-id195-resize-validation.json`, `browser_id195_resize_requires_dimensions.py`, `id195-resize-validation-round*.png`.

ID 196 Master Audit #17 copy/polish set: two local Chromium rounds removed page 2 from a three-page PDF and verified `removed-pages.pdf` plus page markers 1 and 3; Split’s 12-page placeholder was `e.g. 1-3, 5, 8-12`; the Photo Resize upload accept list was JPEG/PNG/WebP; the admin console Logout button’s fetch returned 200, cleared sessionStorage, returned to sign-in, and the revoked token returned 401. Admin logout used a fresh temporary local server/session in each round; no live admin access occurred. Evidence: `browser-id196-copy-polish.json`, `browser_id196_copy_polish.py`, `browser-id196-admin-logout.json`, `browser_id196_admin_logout.py`.

ID 200 Admin Last Active: two isolated local server rounds used separate synthetic accounts, visited Paperplane while signed in, and then opened the admin console with a fresh synthetic owner session. The user row displayed a non-empty localized Last Active timestamp, and the users API returned a positive `last_active_at` value for each; no browser errors. Evidence: `browser-id200-admin-last-active.json`, `browser_id200_admin_last_active.py`, `id200-admin-last-active-round*.png`.

ID 201 Admin login location: ran the existing controlled regression for `_lookup_admin_location`: a private loopback address returns no location; a public address returns only city, region, and country from a supplied GeoIP database. The admin interface labels the column “Approximate location”. Exact device GPS and the production GeoIP database were not verified; no precise location collection was introduced. This checklist requirement remains PARTIAL because IP geolocation cannot establish an exact physical location.

ID 213 mobile result panels and Studio export filename: reproduced Protect’s Download link at y=1094 on a 390×844 viewport. Updated result handling to scroll the result card into view on narrow screens. Two browser rounds ran Protect, Unlock, and Sign; each Download link fit in the viewport and each output was content/structure checked. Also changed Studio Export’s success toast to include the actual output filename; two rounds verified both browser download name and toast name against a valid one-page exported PDF. Evidence: `browser-id213-mobile-download-visibility.json`, `browser_id213_mobile_download_visibility.py`, `browser-id213-studio-export-name.json`, `browser_id213_studio_export_name.py`.

IDs 214–218 current-code retest: Chromium rendered the workspace at 390×844. The command palette had category labels only and no API search results (215); all ten Page Organizer labels fit without overlapping arrows (216); a controlled reload marker produced a filename-specific retry message (217). AI Intelligence restored a real 10-page PDF after reload, hid the empty state, and rendered one document greeting in each of two rounds (218). This also confirms local mobile viewport browser tests are available (214). Evidence: `browser-ids214-218.json`, `browser-id218-ai-restore-race.json` and corresponding scripts/screenshots.

ID 222: two 390×844 Chromium rounds verified Log In remains visible in the topbar, and the guest profile in the mobile drawer opens Settings with visible Sign In/Create Account actions; Sign In opens the auth modal without horizontal overflow. Evidence: `browser-id222-mobile-signin.json` and screenshots.

ID 223: initial Protect → View in Studio reproduction failed. Root cause was a race: switching to Studio started restoration of an old saved document while the protected result was being loaded. Changed the handoff to skip saved-document restoration for that switch and passed the entered password only to the in-memory PDF.js load. Two Chromium rounds verified the protected output PDF rendered, its encrypted source marker remained present, and the password was not stored in session storage. Evidence: `browser-id223-protect-studio-handoff.json` and screenshots.

ID 224: current local Chrome runs did not reproduce the historical toast overlap. Content-checked four-page Merge downloads at 1366×900 and 390×844 showed no intersection between toast and result actions; Protect/Unlock/Sign downloads at 390×844 also showed no intersection in two rounds. Marked locally fixed based on current geometry; retain live retest after deployment. Evidence: `browser-id224-download-toast-overlap.json`, `browser-id213-mobile-download-visibility.json`, and screenshots.

ID 225: reproduced a displayed Summarize error and removed the selected source. Before the fix the stale result stayed visible. Clearing the result and persisting the empty session on file removal resolves it; two Chromium rounds confirmed the result panel, file rows, and metadata clear and Run stays disabled. Evidence: `browser-id225-remove-file-error.json`.

ID 227: `/crop-pdf` displays the corrected SEO lead copy in two Chromium rounds; no page errors. Evidence: `browser-id227-crop-copy.json`.

ID 228: controlled Cloud Import of a one-page PDF displayed “1 page” (singular) in two rounds. Evidence: `browser-id228-cloud-import-plural.json`.

ID 229: selecting Passport populated width/height as 350×450 before and after upload; both downloaded JPEGs decoded at 350×450. Evidence: `browser-id229-passport-fields.json`.

ID 231: four `/faq` questions and answers match the homepage FAQ. Chromium parity check and the `test_faq_workspace_matches_the_four_home_page_faqs` regression passed. Evidence: `browser-id231-faq-parity.json`.

ID 232: controlled Legacy Pro rendering hides the Settings upgrade button in two Chromium rounds. Evidence: `browser-id232-legacy-pro-settings.json`.

ID 233: pricing feature copy changed to “Document Stamps & Watermarks.” ID 234: plan badges are inside each card boundary in two rounds. Evidence: `browser-ids233-234-pricing.json`.

ID 235: two free-account Chromium sessions navigated five tool routes each with usage resolved to 0 / 10. A controlled 503 during quota refresh resolves to “Usage unavailable” in two rounds instead of leaving “Checking usage…”. Evidence: `browser-id235-quota-navigation.json`, `browser-id235-quota-failure.json`.

ID 236: Merge file hint exposes “Merge supports up to 100 PDF files per run” in two rounds. ID 239: `/history` explains no saved history and the footer link says “Temporary results”; both confirmed in two rounds. Evidence: `browser-ids236-239-copy-history.json`.

ID 245: corrected Merge SEO content to match the plain ordered file list: files merge in add order; users remove and add again to change that order. Two Chromium rounds confirmed the lead, steps, and FAQ no longer promise unavailable thumbnails/reordering. Added server-rendered regression. Evidence: `browser-id245-merge-copy.json`.

ID 248: two 390×844 Chromium rounds on `/pricing` confirmed the mobile pill reads “Pricing”, fits the available width, and remains inside the viewport. Evidence: `browser-id248-pricing-pill.json`.

ID 253: two local browser runs uploaded 2400×1800 image scans with Original 200 DPI selected. Each output PDF page measured 864×648 pt, independently parsed with PyMuPDF; no browser errors. Evidence: `browser-id253-scan-dpi.json`.

ID 254: the HTML to PDF catalog now accurately says the URL form does not accept pasted HTML. Two browser runs submitted loopback URLs and displayed `Security Guard: Access to host '127.0.0.1' is forbidden.` Evidence: `browser-id254-html-url.json`.

ID 255: two Chromium runs left the Photo Compress target at its initial 100 KB value, downloaded and decoded valid JPEGs, and measured 101,201 bytes (within 100 KiB) both times. Evidence: `browser-id255-default-photo-target.json`.

ID 257: with a one-page PDF loaded in Studio, two Chromium rounds opened Digital Signatures and remained at `/studio`; no page errors. Evidence: `browser-id257-signature-modal.json`.

ID 260: two browser sweeps confirmed `/resize-photo`, `/photo-resize`, `/compress-photo`, and `/add-page-numbers` redirect to canonical routes; no matching obsolete links were present on home. Evidence: `browser-id260-legacy-aliases.json`.

ID 261: footer now renders `Version <running app version>` from FastAPI's configured release version (`PAPERPLANE_RELEASE_VERSION`, default 2.0.0). Two browser rounds show Version 2.0.0; added a server-rendered assertion. Evidence: `browser-id261-app-version.json`.

ID 263/264: current Scan to PDF copy does not promise deskewing and its page-size selector is available; JPG to PDF copy does not promise page-size controls its form lacks. Two Chromium rounds each; no page errors. Evidence: `browser-ids263-264-copy.json`.

ID 265: added a semantically labeled AI Intelligence guide with three accurate steps. Chromium checked desktop, 390 px mobile, and 320 px narrow layouts twice; no horizontal overflow or page errors. ID 266: added explicit browser-PDF availability while native apps are pending and verified the existing waitlist steps at the same widths. The 320 px browser run also found footer-left overflow (336 px document width); wrapping footer copy fixed it, and the re-run has no overflow. Evidence: `browser-ids265-266-howto.json`.

ID 270: added `renderTranslationResult` and a View in Studio action that passes the translated PDF blob into Studio while skipping stale document restoration. Two controlled translation-result Chromium runs opened and rendered the one-page PDF in Studio with no page errors. Evidence: `browser-id270-translation-studio.json`.

ID 272/273: two runs seeded an uploaded temporary file and Studio as the prior view. The reload notice names the unavailable temporary PDF and appears only once; it clears on the next tool navigation. Loading `/` now remains at the Tool Desk rather than auto-switching back to Studio. Evidence: `browser-ids272-273-navigation.json`.

Self-found responsive bug: Apps waitlist at 320 px had a 336 px document width, caused by the unwrapped footer metadata row. Added narrow-screen wrapping and re-ran AI and Apps pages at 320/390/1366 px in two rounds; all fit and had no browser errors. Evidence: `browser-ids265-266-howto.json`.


ID 122 heavy pages: two Chrome rounds with 4× CPU throttling covered home, Compress PDF, Organize PDF, Grayscale PDF, Excel to PDF, and Studio (12 navigations). All returned 200, had no page errors or tab crashes, and fit the desktop viewport. DOMContentLoaded ranged 438–2,385 ms; longest observed main-thread task was 460 ms on the home page. This did not reproduce the reported freeze, but it leaves meaningful main-thread work and does not verify low-end mobile or heavy-document export. Evidence: `browser-id122-heavy-pages.json`.

ID 124 copy nits: two clean Chromium rounds opened `/merge-pdf` and `/html-to-pdf`. Merge's initial hint showed the plan file size and “Merge supports up to 100 PDF files per run”; HTML-to-PDF showed public HTTP/HTTPS URL input and “No file upload required,” without claiming PDF upload. Zero page errors. Evidence: `browser-id124-copy-ux.json`, `id124-copy-round1.png`, `id124-copy-round2.png`.

Latest full-suite rerun after the ID 122/124 browser checks: 552 passed with four warnings in each run (95.64s and 90.64s); logs `pytest-cont-id122-124-run1.log` and `pytest-cont-id122-124-run2.log`.


ID 125: compacted wide-desktop Studio controls via a min-width:1200px rule (25px tool buttons, 13px icons). Two 1920×1080 Chromium runs measured the full toolbar at 76px versus the earlier 80px and had no page errors or horizontal overflow. At 390px, the page remained 390px wide and visible tool targets remained 48px high. Evidence: browser-id125-studio-toolbar-geometry.json, browser-id125-mobile-geometry.json, and screenshots.


IDs 130/132/133/134: two local Chromium rounds verified direct /settings renders the Settings page with five tabs and a working Privacy pane; /dashboard redirects to /tool-desk; /history, /faq and /feedback render expected content; and /download waitlist form is visible within 273/288 ms and remains after 20 seconds. Zero page errors. Evidence: browser-ids130-134-routes-waitlist.json.

ID 136: found one stale 100/day free workflow claim on /developers while runtime quota is 10/day. Replaced the literal with the server-rendered FREE_DAILY placeholder and added a page regression. Two Chromium rounds across Home, FAQ, Terms, Settings, Pricing, Developers, and AI Intelligence found no stale 100/250 operations-per-day text; Developers displays 10 operations/day.

ID 138: /ai-intelligence returned 200 and displayed the AI Intelligence workspace in both Chrome rounds. Evidence for IDs 136/138: browser-ids136-138-quota-ai-routes.json and ids136-138-round*.png.


ID 140: pre-fix browser sweep reproduced an auth-pending profile card hidden at DOMContentLoaded on /apps and /faq, with the profile appearing after 1.1 seconds. Updated the auth-pending/restoring styling to retain the card frame and conceal unresolved name/plan fields. Two Chromium rounds across /apps, /download, /privacy, /terms, and /faq now show the card immediately and after hydration, with no browser errors. Guest identity was verified; signed-in Pro hydration remains unverified. Evidence: browser-id140-sidebar-profile.json (before), browser-id140-sidebar-profile-fixed.json (after), screenshots.


ID 150: downloaded the exact 20,597-byte public orimi pdf-test.pdf; PyMuPDF sees an unencrypted one-page PDF, while PyPDF sets is_encrypted but decrypts with an empty password. Two real Chromium server-mode rounds each completed Merge (two pages with original text) and Rotate (one page, 90 degrees), with content-checked downloads, no password warning, and no browser errors. Evidence: orimi-pdf-test.pdf, browser-id150-orimi-server-workflows.json, id150-orimi-browser-round*.png. Recheck deployed server after release because the earlier failure was production-only.


ID 149: two Chromium rounds on /merge-photos-online uploaded four unique 1200×800 photos, selected Grid, and downloaded merged-photos.jpg. Each output was 2400×1600; color samples in all four quadrants matched their respective source images. No page errors. The first harness pass confirmed the default layout is vertical stacking; the reproduction was corrected to explicitly select Grid as the prior report required. Evidence: browser-id149-photo-merge-content.json and id149-photo-merge-round*.png.


ID 151: with a seeded local student_pro session, two Chromium rounds covered Home, Compress PDF, and Settings. The signed-in Pro state was confirmed on each route. No visible ad container, SPONSORED copy, Google/AdSense network request, or page error appeared. Evidence: browser-id151-pro-ad-visibility.json and id151-pro-ad-round*.png.


ID 152: exercised all four photo tools in two Chromium rounds (Exam Resizer, Photo Compress, 50% Resize, and 2-image Grid Merge). Content-checked JPEG downloads measured 350×450, 1200×800, 600×400, and 2400×800 respectively. The browser made no /api/jobs file-processing requests and raised no page errors. Evidence: browser-id152-photo-local-processing.json and id152-photo-local-round*.png. First attempted assertion expected 4-image dimensions while only 2 source files were queued; corrected the harness expectation and completed both rounds.


ID 155: aligned static browser-processing support copy in sidebar and Settings to cover Merge, Split/extract, Remove, Rotate, Page Organizer, and photo tools. Two Chrome rounds checked six representative routes; the local toggle remained enabled and each tool page stated that files stay on device and are not uploaded. Settings states photo tools always run in browser. No page errors. Evidence: browser-id155-processing-copy-consistency.json and id155-processing-copy-round*.png. Added a rendered-copy regression test.


ID 173: updated verified missing-control claims: PDF-to-Text FAQ now directs page subsets through Split / extract; PDF-to-JPG intro states every page is exported; Compare description says plain-text report; Metadata description/FAQ names only title, author, and subject fields. Two Chromium rounds across Rotate, PDF-to-Text, PDF-to-JPG, Compare, and Metadata verified rendered steps against available controls. No page errors. The 44-route copy audit remains partial. Evidence: browser-id173-controls-copy-audit.json. Added API-content regression test.


ID 174: two 1920×999 Chromium runs loaded a 10-page PDF. The first page rendered; no phantom Page 1 loading state appeared. Seven offscreen pages remained lazy placeholders until scrolled into view. Sequential scrolling the internal canvas caused pages 1–10 to render; the last page was reachable within the scroller although the outer document stayed fixed to viewport height. The default annotation mode/Pan tool state did not change. Zero page errors. Evidence: browser-id174-studio-state.json, browser-id174-studio-sequential-scroll.json and screenshots.


IDs 185–186: in two fresh Chromium contexts, loaded Merge, toggled Browser Processing off and on through its visible slider, and confirmed preference storage, checkbox state, and accessible mode copy stayed consistent after updateButton synchronization. Submitted a five-page source PDF locally, waited for a Blob result, then navigated away to FAQ; both navigations returned HTTP 200 and completed in 0.135s and 0.129s with visible content and no page errors. Neither report reproduced; current behavior verified. Evidence: `browser-ids185-186.json`, `browser_ids185_186.py`.

ID 187: revisited two rounds of the local photo suite matrix; Exam Photo & Signature Resizer exported a decoded 350×450 JPEG and no `/api/jobs` requests were made across any photo workflow. Confirms this exam-specific operation runs browser-side rather than spending server quota. Evidence: `browser-id152-photo-local-processing.json`, `browser_id152_photo_local_processing.py`.

IDs 197–198: seeded two independent authenticated sessions; each signed out through the actual Settings UI. `/api/auth/me` returned `authenticated:false`, auth cookie and last-auth email key were absent, Guest Explorer displayed immediately and after full reload, and the reopened Settings pane showed Sign in. Zero page errors. Evidence: `browser-ids197-198.json`, `browser_ids197_198.py`.


IDs 206, 208, 209, 211: current browser evidence confirms browser-local Merge generated a Blob and the tab navigated without freezing. Prior two-round local sweeps verify one-time/no-renewal copy across Pricing/Terms/FAQ/Billing, aligned current plan names across Pricing/Settings, and matching local/server-processing preference scope across six supported tool pages and Settings. Evidence: browser-ids185-186.json, browser-ids74-81-83-policies.json, browser-id183-189.json, browser-id192-pricing-catalog.json, browser-id155-processing-copy-consistency.json.


IDs 202–204: two clean local admin-console browser runs used seeded test identities. For each, set the disposable user to Exam Pass and reset only that user's usage; both endpoints returned 200 and UI rendered the changed plan. The admin sessions panel rendered count 1. Focused pytest tests additionally verify two configured superadmin accounts can authenticate independently and one can revoke the targeted other session, plus plan/usage update targeting and audit logging. Browser logout-other was not exercised with two concurrent sessions; live OTP email delivery is unverified. Evidence: browser-ids202-204-admin-actions.json and `pytest-admin-202-204.log`.


ID 219: two Chromium uploads of the audit workbook completed Excel to PDF. Downloaded outputs each parsed as a one-page PDF (2,013 bytes, 122 text characters) with `AUDIT_OFFICE_EXCEL_OUTPUT`; no browser errors. Evidence: browser-id219-excel-download.json, browser_id219_excel_download.py, id219-excel-output-round*.pdf.


ID 210: reproduced the reported Studio page-order workflow at 1920×1080. In two rounds, the Later and Earlier buttons were visible, within the viewport, and received mouse clicks. Downloaded editor PDFs showed the order changed from Alpha/Beta/Gamma to Alpha/Gamma/Beta, then back to Alpha/Beta/Gamma. No browser errors. Evidence: browser-id210-studio-reorder-buttons.json, browser_id210_studio_reorder_buttons.py, id210-reordered-round*.pdf.


ID 220: Windows app host reports the PDF/A Ghostscript dependency unavailable. WSL Ghostscript 10.02.1 ran the PDF/A conversion command against a clean synthetic one-page PDF and produced a 7,371-byte output. PyMuPDF found PDF/A part 1 XMP, an OutputIntent array with GTS_PDFA1 and a destination profile, Ghostscript producer metadata, one page, and retained source text. The exact public `orimi-pdf-test.pdf` has a non-printing annotation and Ghostscript correctly rejected it for PDF/A. Docker engine and an independent veraPDF-style validator were unavailable; status PARTIAL. Evidence: id220-wsl-gs.pdf, id220-clean-source.pdf, id220_generate_wsl.sh.


Current full-suite confirmation after the latest audit/harness updates: 556 passed, 4 warnings in 96.35s and 556 passed, 4 warnings in 92.84s. Logs: `pytest-cont-current-run1.log`, `pytest-cont-current-run2.log`.


ID 202: seeded both configured owner sessions in the isolated local app, opened the admin sessions panel in Chromium, and clicked the other session's Log out button. The count fell from 2 to 1; the target session received 401 while the acting owner's session remained 200. No page errors. Evidence: browser-id202-two-admin-revoke.json, browser_id202_two_admin_revoke.py, id202-two-admin-sessions.png.


ID 230: two signed-in Chromium rounds scanned Pricing, Terms, and Settings → Plans & Billing for the stale automatic renewal footer and Legacy Pro renewal date. Neither appeared; Pricing displays one-time purchase wording. No browser errors. Evidence: browser-id230-renewal-copy.json and browser_id230_renewal_copy.py.


ID 237: v17 failure superseded by ID 49's local retry behavior. Two browser rounds captured and parsed actual Studio Export downloads after a dropped first fetch and first-attempt 503. The output is one-page PDF with expected text. Production retest remains attached to ID 49. Evidence: browser-p0-round12.json and browser-p0-round13.json.


IDs 240–241: two browser-p0 Sign runs captured one-page PDFs with signer text content-checked. Current catalog round 1 and round 2 also generated Page Numbers output from a two-page source; parsed content includes Page 1 of 2 and Page 2 of 2. Evidence: browser-p0.json and browser-catalog*.json.


ID 243: reproduced the Settings UI gap: API key creation returned 403 for Free/Student Pro but the Generate Key form was visible. The form now hides for non-API tiers and shows upgrade guidance. Two Chromium rounds verified Free and Student Pro hide it and direct creation is rejected; the API-enabled tier shows the form and successfully generates a disposable key. The evidence records no key secret. Added a focused API/UI-contract regression test. Evidence: browser-id243-api-key-tier-gate.json, browser_id243_api_key_tier_gate.py, test_developer_api_key_creation_is_tier_gated_in_ui_and_server.


Current full-suite confirmation after ID 243 implementation: 557 passed, four warnings in 105.62s, then 557 passed, four warnings in 101.53s. Evidence: pytest-id243-final-run1.log and pytest-id243-final-run2.log.


ID 118/246/296 current-source Docker/Nginx integration: one isolated production-mode app container mounted current workspace files behind the project Nginx template, using tmpfs data, synthetic secrets, a temporary localhost TLS certificate, and a private bridge network. Chromium verified HTML/current JS/API responses, HTTPS security headers, asset cache policy, hidden Nginx version, and HTTP→HTTPS redirect. Two failed logins sent distinct forged `X-Forwarded-For` values; both audit rows recorded the actual proxy-side client address `192.168.254.1`. Three failed admin step-one attempts with three different forged values returned 401/401/423, and a fourth forged value still saw the same locked status; the DB stored one 3-attempt bucket for the actual client address. All browser page-error checks passed; test containers and network were removed. IDs 118 and 246 are fixed locally; ID 296 remains partial pending live proxy-chain and audit-event retest. Evidence: `browser-id246-nginx-container-integration.json`, `browser_id246_nginx_container_integration.py`, `id246-nginx-proxy-home.png`.

ID 304 (Elite v23): two local Chromium rounds sent representative Markdown through the actual Summary Desk render function. Headings, lists, and bold text became semantic HTML; the visible text contained no raw `##`/`**`, and no page errors occurred. Evidence: `browser-id304-summary-markdown-render.json`.

ID 305 (Elite v23): uploaded the same attribution-leading PDF to Smart Metadata and AI Chat in one Chromium session. Both returned “Attention Is All You Need” as the on-page title, and Chat included the original filename; both endpoints returned 200 with no page errors. Evidence: `browser-id305-chat-metadata-consistency.json`.

ID 306 (Elite v23): two real Chromium runs deleted one page from a 69-page PDF. The UI showed “Deleting 1 page(s)…”, the page count reached 68 in 1.159s and 1.087s, and no page errors occurred. No artificial delay was injected in these measurements. Evidence: `browser-id306-studio-delete-69-pages.json`.

ID 307 (Elite v23): two real Chromium Protect → Unlock flows downloaded the protected output and then unlocked it from the in-memory file in the same modal/session, without selecting the downloaded file again. The encrypted intermediate and decrypted output were content-checked; unlock returned HTTP 200 and no page errors occurred. Evidence: `browser-id307-protect-unlock-same-session.json`.

ID 310 (Elite v23): corrected the SSC photo preset to treat the listed KB ceiling as decimal (50,000 bytes), with the same decimal unit for the minimum and final validation. Two actual Chromium downloads were valid 350×450 JPEGs at 49,982 bytes / 48.8 KB, under the published maximum; no browser errors. Evidence: `browser-id325-exam-resizer-stability.json`, two rounds.

IDs 311–313 responsive follow-up: two Chromium rounds measured Settings at 820px, Studio at 820px, and the signature dialog at 390px. Settings bounds were x=112–708 with document width 820; the canvas was visible below the toolbar; the signature dialog stayed within x=36–354 and the page stayed 390px wide. No page errors. The old tablet sidebar obstruction and signature dialog clipping were not reproduced. Physical-device touch/safe-area behavior remains unverified for the broader Studio mobile issue. Evidence: `browser-id311-312-313-mobile-layout.json`.

Full-suite check after the ID 310 decimal-KB implementation: `python -m pytest -q` passed 561 tests with 4 existing deprecation warnings in 105.24s, then passed 561 tests with 4 warnings in 101.26s. Logs: `pytest-id310-final-run1.log`, `pytest-id310-final-run2.log`.

ID 308 (Elite v23): current browser app converted a mixed-content PDF containing editable text, a vector-bordered table, and an embedded image to DOCX twice. Download inspection found the title/body paragraphs, a real Word 3×3 table with all six data cells and headers, and an embedded `word/media/image1.jpg`; both downloads were 38,255 bytes with no page errors. The Round 12 6.34 MB original fixture was unavailable, so this verifies a controlled equivalent, not that exact source file. Evidence: `browser-id308-word-mixed-page-fidelity.json`.

ID 299: in two local Chromium rounds, checked `/api/billing/status` as both guest and authenticated user (four responses total). Every response returned 200 and contained no `cashfree_order_id` or `order_id`; no browser errors. Evidence: `browser-id299-billing-status-disclosure.json`.

ID 2 follow-up: reproduced a provider failure in the 69-page Summary route with the local AI provider unconfigured. Added an extractive fallback regression for a failed middle section, which exposed that the fallback kept only each page's first line. Changed it to retain every eligible extracted line per page. Focused test passed; two actual Chromium rounds then uploaded 69-page PDFs and verified HTTP 200, explicit Offline Analysis badge, the page-24 decision, the page-69 final condition, and all 69 citations, with no page errors. Evidence: `browser-id2-69page-provider-failure-fallback.json`; `test_large_summary_chunk_failure_falls_back_with_all_section_lines_and_citations`. Provider-backed synthesis and live provider reliability remain unverified.

Full suite after the ID 2 fallback change: 562 passed, 4 warnings in 133.17s and 562 passed, 4 warnings in 147.75s. Logs: `pytest-id2-fallback-run1.log`, `pytest-id2-fallback-run2.log`.

Additional live issue found: `/merge-pdf` returns 200 but serves stale `app.js?v=22` and `editor.js?v=13` while the current source versions are `app.js?v=68` and `editor.js?v=14`. In real Chrome the live `#file-input` had no `multiple` attribute (so two-file selection was rejected), and a one-file test did not expose the download link within 60 seconds. This confirms deployment drift; local current-source success does not prove the live service. No deploy was performed. Evidence: `browser-live-deploy-drift.json`, `browser_live_smoke.py`.

Docker runtime follow-up for IDs 25/220 and OCR: built and ran the isolated current application image. Chromium content-checked browser downloads for 5-page Merge and Split, then PDF/A-1b and OCR. PDF/A output has the expected source text, `pdfaid:part=1`, and dereferenced `/GTS_PDFA1` OutputIntent. A 300-DPI, image-only scanned golden PDF with zero source text gained the expected OCR text (`PAPERPLANE OCR GOLDEN CHECK`, `Invoice 54821`, `Total: $124.50`) in the downloaded one-page PDF. No page errors. Evidence: `browser-docker-runtime-smoke.json`, `docker-runtime-verification.json`, `ocr-golden-source.pdf`; image metadata and health in `docker-runtime-verification.json`.

ID 78: the conflicting result-handoff claim was retested in the current code. Two Chromium runs handed translated output into Studio; the broader two-round local matrix handed Merge, Rotate, Split, and Remove results into Studio, rendered them, and retained content markers after reload. Evidence: `browser-id270-translation-studio.json`, `browser-id342-local-pdf-studio-handoff.json`.

ID 79: verified the existing no-history decision on current routes. Two browser rounds confirm `/history` clearly says jobs are not saved and the footer calls results temporary. Evidence: `browser-ids236-239-copy-history.json`.

ID 47: current Studio reorder behavior meets the mouse-click criterion. Two Chromium rounds clicked the visible Later/Earlier controls, checked they were the hit targets, and content-parsed the reordered then restored PDF. Evidence: `browser-id210-studio-reorder-buttons.json`, `browser_id210_studio_reorder_buttons.py`.

ID 48: reproduced the reported Studio Duplicate operation in the current local app. Two Chromium rounds duplicated a one-page PDF; downloaded/editor PDF bytes parsed as two pages and both retained the original marker, with no page errors. Evidence: `browser-id48-studio-duplicate.json`, `browser_id48_studio_duplicate.py`.

ID 4 live follow-up: the public 5-page TotPDF sample imported successfully on the deployed site through both `/api/cloud/sync` and the real Cloud Import modal in two Chromium rounds. Each UI round showed `Imported totpdf-sample-5-pages.pdf · 0.00 MB · 5 pages`, one file row with the expected filename, and no page errors. A second current W3C direct PDF URL also returned a valid one-page PDF. The older path embedded in the checklist currently returns upstream HTTP 404. The exact owner Drive link is not present in this workspace; prior v23 evidence for it was `image/png`, not a PDF, so item stays PARTIAL. Fixture: `totpdf-sample-5-pages.pdf` (3,785 bytes, 5 pages). Evidence: `browser-live-id4-cloud-import.json`.


## ID 100 — short mobile drawer viewport

The existing phone layout evidence used an 844px-tall viewport and did not exercise the reported short-height laptop/mobile case. Started the current local app and ran two independent Chrome contexts at 390×500. Opened the mobile menu, scrolled the sidebar to its bottom, checked profile and settings gear bounds against viewport height, and opened Settings via the gear. The profile and gear stayed visible (gear 48×48) in both rounds; no page errors. Evidence: `browser-id100-mobile-drawer-viewport.json`, `browser_id100_mobile_drawer_viewport.py`.


## ID 99 — attached PDF with neutral question

Created a one-page source with Item A=100, Item B=200, Item C=300. In two fresh Chromium contexts, attached it to AI Chat and asked only “What is the value for Item B?”—without document-reference wording. Both answers included the source value 200, showed one Page 1 citation and “Local document extract · AI provider is disabled,” and had no page errors. Evidence: `browser-id99-neutral-question-attached-pdf.json`, `browser_id99_neutral_question_uses_attached_pdf.py`.


## ID 181 — legacy tool slugs

In two Chromium rounds, checked the raw redirect response and then navigated each alias: `/metadata`→`/pdf-metadata`, `/photo-compress` and `/compress-photos`→`/compress-image-online`, `/ai-chat`, `/chat-pdf`, and `/pdf-chat`→`/ai-pdf-chat` (which the app routes to `/ai-intelligence`). Every redirect was HTTP 301 and every final page HTTP 200, with no page errors. Evidence: `browser-id181-legacy-slug-redirects.json`, `browser_id181_legacy_slug_redirects.py`.


## ID 113 — recover a PDF with damaged xref marker

Built a one-page PDF with two unique text markers, replaced its `startxref` token with `startxxxx`, and uploaded those bytes from two fresh Chromium pages to `/api/studio/repair` in automatic mode. Both responses were HTTP 200, `X-Repair-Valid: True`, and reported one recovered page. Parsed each returned PDF with PyMuPDF and confirmed both markers remained; no browser errors. Evidence: `browser-id113-repair-damaged-xref.json`, `browser_id113_repair_damaged_xref.py`.


## ID 116 — Sanitize Document Now feedback

Loaded a PDF with custom title, author, subject, and a unique page marker in Studio. Opened More Tools → Protect & Unlock PDF → Audit & Sanitize and clicked Sanitize Document Now. Two Chromium rounds displayed “Sanitization complete,” offered the sanitized download, and delivered valid one-page PDFs preserving the marker while removing the metadata. No page errors. Evidence: `browser-id116-sanitize-feedback.json`, `browser_id116_sanitize_feedback.py`.


## ID 171 — footer on every route

Using the current 46-route copy/layout matrix, visited each route in two independent Chromium rounds. Scrolled the main page to reveal the deferred footer and checked visible state, © 2026, and at least 12 link/button controls. All 92 checks returned HTTP 200 with zero page errors. Evidence: `browser-id171-footer-all-routes.json`, `browser_id171_footer_all_routes.py`.


## ID 180 — Developer API reference version and docs links

Two fresh Chromium rounds opened `/developers`. Each showed one visible “Developer REST API v1 reference” heading, `/api/v1` base URL, no stale v2.0 label, and working Swagger, ReDoc, and OpenAPI schema responses (200). `/api-docs` returned the expected 307 redirect to `/spec/swagger`. No page errors. Evidence: `browser-id180-developer-reference.json`, `browser_id180_developer_reference.py`.


## IDs 141/177 — pricing page grid and reachable checkout controls

Reproduced four pricing tiers in one row at 1920px despite the accepted 2×2 layout. The embedded inline `auto-fit` grid style overrode the stylesheet. Removed it so the existing explicit two-column desktop grid and narrow single-column breakpoint apply. Added a regression test. Two fresh Chrome rounds confirmed 4 tiers in 2 columns at 1920×1080, no modal overlay, and all three pay buttons visible after one 400px scroll. At 390×844 the pay buttons remain within viewport after scrolling. No checkout button was clicked. Evidence: `browser-ids141-177-pricing-layout.json`, `ids141-177-pricing-round1.png`, `ids141-177-pricing-round2.png`.


## ID 154 — stale pricing text

In two Chromium rounds, inspected the full rendered `/pricing` content. Current ₹19, ₹49, and ₹299 prices were present; stale ₹750 and $299/month were absent. No checkout was initiated. Evidence: `browser-ids141-177-pricing-layout.json`.


## ID 153 — reconcile tool counts with grouped AI features

Reproduced “44 PDF TOOLS” beside only 41 Tool Desk cards. Three valid AI operations are intentionally grouped in AI Intelligence and excluded from the card grid. Changed displayed total, category counts, sidebar badges, search result count, and All filter label to include these integrated workflows while preserving one shared workspace; the note identifies Chat, Smart Metadata, and Executive Brief. Added a pytest regression. Two Chromium rounds confirmed 41 cards + 3 grouped AI workflows = 44; per-category logical counts sum to 44, sidebar category badges sum to 44, and Smart Metadata search links to AI Intelligence instead of returning an empty result. Evidence: `browser-id153-tool-count-labels.json`, `browser_id153_tool_count_labels.py`.


## ID 170 — paid user tool badge

Started an isolated local server with a disposable test user, changed only that test account to Legacy Pro, and visited all 44 operation routes in two separate Chromium rounds. All 43 actual tool pages showed “Legacy Pro · no daily operation cap”; `/ai-pdf-chat` resolved to the AI Intelligence workspace without a visible guest badge. All 88 route checks had no page errors. Evidence: `browser-id170-paid-tool-badges.json`, `browser_id170_paid_tool_badges.py`.


## IDs 61 and 300 — transactional mail sender hardening

Confirmed the dispatcher previously attempted SMTP before the configured Resend API, allowing a personal mailbox transport to take precedence over the authenticated transactional provider. Updated dispatch to prefer Resend, reject consumer mailbox From domains, and return failure when no eligible transactional provider accepts the message. Two focused regressions prove Gmail sender refusal even when providers are configured and prove Resend is selected before SMTP. A separate local app ran with synthetic Gmail From plus synthetic SMTP/Resend credentials: two Chromium signup rounds received HTTP 503, no OTP pane, no session/token, and zero page errors. Evidence: `browser-id61-consumer-sender-refused.json`, `browser_id61_consumer_sender_refused.py`. Actual inbox placement and SPF/DKIM/DMARC alignment remain a verified-domain/post-deploy check. Current full-suite evidence, including this mail change: `pytest-final-id85-run1.log`, `pytest-final-id85-run2.log`.


## Continuation: ID 323 heavy-document page rendering

Two earlier delayed-read Chromium runs verify the prior Studio PDF remains behind the loading overlay while a replacement document loads. Follow-up test generated a 69-page, 76.6 MB image-heavy PDF by repeating the available scanned page, uploaded it to the current local Studio build at 390×844 and 1366×900, and explicitly waited for content canvases on pages 4, 5, 20, and 69. Render times were 0.066–0.542 seconds; each target canvas had nonzero dimensions, document width matched its viewport, and there were no page errors. This is synthetic image-heavy coverage; the exact owner PDF and deployed app remain retest evidence. Marked FIXED LOCALLY. Evidence: `browser-id323-69-image-page-render.json`, `browser_id323_heavy_page_render.py`, and screenshots.


## Continuation: ID 45 full Studio responsive check

Two local Chromium rounds uploaded a real one-page PDF at 320×740, 360×800, 390×844, 820×1180, 1024×768, 1104×760, 1366×900, and 1920×1080. The persistent-save banner was absent, Save remained visible, toolbar height measured 76–118 px, the footer was hidden at initial scroll and visible after scrolling, and document width matched the viewport at every size. No page errors. Marked FIXED LOCALLY; this is current-source desktop Chrome viewport coverage, not physical-device evidence. Evidence: `browser-id45-responsive-studio-layout-round1.json`, `browser-id45-responsive-studio-layout-round2.json`, `browser_id45_responsive_studio_layout.py`, and screenshots.

ID 173 full-route copy sweep and corrections: two fresh Chromium rounds opened all 44 operation routes (88 views, all HTTP 200, zero page errors), recorded rendered how-to copy, SEO descriptions, and visible pre-upload form fields. The capture rechecked existing fixes and surfaced remaining claims that Word-to-PDF exposed conversion/page settings, PowerPoint-to-PDF exposed orientation/output settings, Annotate supported freehand drawings/shapes, and HTML-to-PDF offered controlled page sizing. Corrected those claims in the operation/SEO catalog and rendered step details. Focused API/content regressions and browser checks passed. The inventory remains PARTIAL because controls that mount only after file selection and the resulting downloads were not semantically tested for every route.


## Continuation: ID 343 real Deutsche Bahn 12-page PDF-to-Word

Downloaded Deutsche Bahn Group's official 355-page 2025 annual report, derived a 12-page management-report excerpt, and uploaded it through `/pdf-to-word` in two fresh local Chromium rounds. Both rounds downloaded and parsed valid DOCX files; all six sampled page markers survived, four extracted tables with 62 rows and 11 embedded images were present, and all 13 DOCX XML parts decoded successfully. No browser errors. Evidence: `browser-id343-deutschebahn-real-excerpt.json`, `browser_id343_deutschebahn_real_excerpt.py`, `fixtures/deutschebahn-2025-annual-report.pdf`, `fixtures/deutschebahn-2025-annual-report-excerpt-12p.pdf`.


## Continuation: current production Docker image catalog

Built the current source with a unique local tag, started it in production mode with four workers, safe test-only session/admin values, an isolated new named volume, and Cashfree test payments disabled. The first container start correctly failed closed because this mode requires a public HTTPS URL and session secret; after supplying dummy local values the container became healthy. Two Chromium catalog rounds against the current image each content-checked 41 downloaded operation results; SSRF blocking passed, provider-backed Summary/Translate remained honestly unavailable without credentials, and browser page errors were zero. Stopped the container after testing. Docker emitted a SecretsUsedInArgOrEnv warning for the non-secret `PAPERPLANE_REQUIRE_AUTH=false` name; `.dockerignore` excludes `.env` files and no actual secrets were sent to the build. Evidence: `docker-current-image-verification.json`, `browser-id28-current-image-catalog.json`, with output files under `docker-catalog-fixtures-current-20261118/`.


## ID 90 — current Docker image concurrency follow-up

The rebuilt four-worker production image received four simultaneous Merge submissions in each of two Chromium rounds. All eight jobs completed, returned HTTP 200 downloads, and each one-page PDF preserved the expected marker; no browser page errors. The isolated test container was stopped afterward. This verifies this local image/runtime's concurrency path; it does not establish live production traffic capacity. Evidence: `browser-id90-current-image-concurrency.json`, `browser_id90_current_image_concurrency.py`.


## ID 271 — Hindi translation download text-layer check

The deterministic fallback-provider browser sweep now checks the exact `प्लेन` and `टेस्ट` strings in every page of each downloaded ten-page Hindi PDF. Two rounds passed; PyMuPDF found both strings in all pages, source English markers were absent, and there was no replacement-character mojibake or browser error. This verifies local font embedding and downloadable text extraction, not the live provider; keep the post-deploy check outstanding. Evidence: `browser-id1-10page-rate-limit-fallback.json`, `browser_id1_10page_rate_limit_fallback.py`.


## ID 161 — available real 69-page PDF compression retest

Uploaded `C:/Users/mdham/Downloads/notes.pdf` through the local `/compress-pdf` page twice in Chromium using the 100 KB preset. Both downloaded PDFs retained 69 pages and all 92,651 extracted text characters; rendered pages differed by a mean 0.0205/255 RGB (maximum page 0.8108/255). Output size remained 5,414,364 bytes and the app displayed its warning that the target could not be reached while preserving content. Source profiling found 36 unique embedded images totaling 5,190,357 bytes and 21 embedded font programs totaling 253,127 bytes. This is distinct from the report's historical `notes_test.pdf`; the reported 5.20 MB to 89.7 KB case remains unverified against its original input. Evidence: `browser-id161-download-notes-compress.json`, `browser_id161_download_notes_compress.py`.


## ID 29 — guest checkout account gate on current Docker image

In two fresh Chromium guest contexts, opened the upgrade dialog and clicked Student Pro checkout against the current production-mode local Docker image. Each run opened the sign-in/register modal with account-required copy, sent no `/api/billing/checkout-session` request, and had zero page errors. This confirms the client-side gate only; mocked backend checkout, guest quotas/password unlock, live checkout, and production TLS remain independent checks. Evidence: `browser-id29-guest-checkout-gate.json`, `browser_id29_guest_checkout_gate.py`.


## ID 37 — local Flatten PDF Forms workflow

Added `flatten` to the browser-local supported PDF operations. The PDF worker loads the selected form, calls PDF-Lib `getForm().flatten()`, and returns `flattened.pdf`; privacy disclosures now include Flatten PDF Forms. Two complete 44-route Chromium rounds downloaded the local result from a synthetic fillable PDF, confirmed the filled Applicant value and source text were preserved, confirmed the widget was removed, and observed zero `/api/jobs` posts during the operation. Overall local processing coverage is now 11 of 41 requested tools; the ID remains PARTIAL. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, updated harness `browser_id37_id242_local_processing.py`.


## ID 357 — current source offline shell and scan retest

After the app JS/cache update, two mobile Chromium rounds on the isolated current-source server verified service-worker shell v4 and `/assets/app.js?v=78`, the install prompt lifecycle, and offline shell response HTTP 200. A camera-style scan fixture produced a parsed one-page 612×792 PDF in each round; no horizontal overflow or page errors. This validates local browser simulation and shell fallback; physical-device camera and native install remain post-deployment checks. Evidence: `browser-id357-mobile-scan-pwa.json`, `browser_id357_local_source_wrapper.py`, updated `browser_id357_mobile_scan_pwa.py`.


## ID 106 — duplicate-safe retry of accepted job submissions

Added hashed app submission idempotency records scoped to authenticated-user ID or a hash of the guest request identity. The client sends one cryptographically random key across standard `/api/jobs` retries and chunked `/commit` retries; the server replays the existing job and guest capability before charging quota or rate limits. A focused API test proves guest retry returns the same job, restores its download cookie, rejects a different guest scope, stores only one job, and never stores the raw key.

Two local Chromium scenarios injected a synthetic client-visible HTTP 502 after the backend had actually returned the accepted response: one standard upload and one 10.07 MiB image-heavy chunked upload. In both cases, the retry carried the exact key, got the same job ID with an idempotent HTTP 200, and created only one job/key record. Each output parsed as a one-page PDF, preserved its source marker, and had 90° rotation. The 502 was injected at the client safeFetch adapter; this verifies replay and retry code paths, not the live reverse proxy. Evidence: `browser-id106-idempotent-submit-retry.json`, `browser_id106_submission_retry.py`, `tests/test_launch_audit_v23.py::test_app_job_idempotency_replays_guest_job_and_rejects_other_scope`.


## ID 37 — local Fill PDF Forms

Added browser worker fill support for PDF text fields, checkboxes, dropdowns, radio groups, and option lists. The full two-round 44-route local processing harness filled the Applicant field to `LOCAL-FORM-FILLED`, downloaded a valid PDF, verified the interactive widget/value remained present, and recorded zero `/api/jobs` calls for this workflow and all 12 local workflows. The first pass revealed the frontend local dispatcher did not include textarea JSON in the worker options; although the worker succeeded in a direct probe, the UI fell back to the server. Passed the JSON from the Forms tool into the worker options and reran two clean rounds. PWA shell v7 and app asset v81 also passed the two-round offline-shell/camera-scan retest. ID 37 remains PARTIAL at 12 of 41 tools. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser-id357-mobile-scan-pwa.json`, `browser_id37_id242_local_processing.py`, `browser_id357_local_source_wrapper.py`.

## ID 37 — local Edit PDF Metadata

Added browser-worker metadata editing for Title, Author, and Subject, and return an allowlisted output metadata summary for the visible JSON panel/export. Two current-source Chromium rounds tested through the actual local Processing Mode UI: changed Title and Author, retained the original Subject and Creator, preserved page text, parsed the output PDF and JSON metadata download, and observed zero `/api/jobs` submissions. The first UI run exposed that browser-local results were not receiving the worker's metadata summary; wired that summary into the result renderer and repeated both rounds. The full 44-route harness now content-checks 13 local workflows. PWA shell v8 and app asset v82 passed two isolated current-source mobile rounds, including a parsed scan PDF and HTTP 200 offline shell. Five focused regressions passed; Python compilation, JS syntax, and CRLF-aware diff checks passed. Two subsequent full-suite runs passed 581 tests each with four existing deprecation warnings (111.87s and 116.26s); logs: `pytest-id37-metadata-run1.log`, `pytest-id37-metadata-run2.log`. ID 37 remains PARTIAL at 13 of 41 workflows. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser-id357-mobile-scan-pwa.json`, `browser_id37_id242_local_processing.py`, `browser_id357_mobile_scan_pwa.py`.


## ID 27 — narrow-width layout self-analysis

Added two local Chromium rounds across all 44 tool routes at 683px and 512px CSS viewport widths, 176 route/viewport checks total. Every route returned HTTP 200, `documentElement.scrollWidth` matched the viewport, and no visible element crossed the viewport edge. The first draft falsely counted the intentionally translated off-canvas sidebar; after restricting edge checks to visible elements intersecting the viewport, the complete repeat passed. This is zoom-equivalent responsive stress, not native browser zoom or physical-device evidence. ID 27 remains PARTIAL until the owner's M-1–M-11 handset comparison. Evidence: `browser-id27-narrow-zoom-layout.json`, `browser_id27_narrow_zoom_layout.py`.


## ID 37 — current production Docker image worker verification

Rebuilt final current tag `paperplane-v23-audit:final-current` from the time-sliced workspace; image ID `sha256:fe12cd487a4e276329db9dc2b6df26e517bb666efda59089c65fbd0eda4273a6`. Started it in production mode with four workers, test-only dummy session/admin settings, Cashfree TEST configuration without credentials, and a UID-1001 tmpfs at `/data`. The health endpoint returned HTTP 200. Local Chromium filled a real PDF AcroForm and checked Metadata PDF/JSON output as documented above. Then two further mobile Chromium rounds at 4× CPU throttle uploaded the actual 69-page `notes.pdf` into Studio, exported it, and parsed every page; both outputs retained all source text/order, contained 69 pages, measured 390px document width, and had no browser errors. Stopped the container and discarded tmpfs. No production volume or payment provider was touched. Evidence: `browser-id37-docker-worker-smoke.json`, `browser_id37_docker_worker_smoke.py`, `browser-id122-docker-studio-smoke.json`, `browser_id122_docker_studio_smoke.py`.


## ID 122 — real 69-page mobile Studio export and performance optimization

The first mobile/4× CPU test exposed a bug in the attempted batch optimization: `createStudioPageSlot` still appended through an out-of-scope `stack` binding, so the page count updated but no page canvas was created. Fixed the factory to accept an append target, then time-sliced construction into 16-slot batches with zero-delay yields, computed the initial width once, and committed one `DocumentFragment` only if the load epoch remains current. With the real 5,456,746-byte, 69-page `C:/Users/mdham/Downloads/notes.pdf`, two 390×844 Chromium 4× CPU performance rounds exported all pages and preserved text/order. Load-to-first-page: 4.21–4.60s; export: 0.73–1.17s; end-to-end: 5.49–5.67s. The longest tasks were 436–446ms, below the prior 1,096ms peak, though still above 250ms. A separate two-round check deleted page 2 and verified the live-stack fallback recreated and rendered it. No overflow or browser errors; the test also passed at 1× CPU. Bumped current app/PWA assets to v84/v10. Hardware profiling remains open. Evidence: `browser-id122-mobile-69page-studio-perf.json`, `browser-id122-mobile-69page-studio-export.json`, `browser_id122_mobile_69page_studio_export.py`, `tests/test_launch_audit_v23.py::test_studio_bulk_page_stack_uses_one_layout_measurement_and_fragment`, `browser-id357-mobile-scan-pwa.json`.

ID 37 follow-up — browser-local Page Numbers: added Page Numbers to the worker's supported operation set and wired position, format, starting page/number, and mark color through the UI dispatcher. Two fresh 44-route Chromium rounds content-checked 14 local workflows (including the generated Page Numbers PDF), with zero job posts for local operations. Separate two-round option coverage used Header-left, `{n}`, start number 7 and start page 2; it verified preserved source text, page 1 unnumbered, page 2 numbered 7, and zero API posts/page errors. Updated truthful privacy copy and cache versions to app v85, shell v11, PDF runtime v15, worker v17. The focused regression passed as part of fresh full suite run 1 (582 passed, 109.57s, 4 existing deprecation warnings); run 2 is underway. Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser-id37-page-number-options.json`, `pytest-final-run1.log`.

Final v23 continuation verification: after Page Numbers integration, full suite passed twice at 582 tests (109.57s and 106.21s; 4 existing Starlette/httpx warnings each). JS syntax, Python compilation, and CRLF-aware diff checks passed. Rebuilt local production-mode Docker image `sha256:3f46c6172318c2edaad5377fbab595e30e90ef729a46d786a363db24d4904fcb`; four-worker health was `ok`. Chromium content-checked Fill Forms and Metadata PDF/JSON output in the image with zero API job posts and no page errors. Container used synthetic-only credentials and tmpfs, then stopped. Docker lint flagged `PAPERPLANE_REQUIRE_AUTH=false` as a sensitive-looking environment variable name; no secret value was included. Evidence: `pytest-final-run1.log`, `pytest-final-run2.log`, `browser-id37-docker-worker-smoke.json`.

ID 122 Studio follow-up: current organizer thumbnail rendering now builds its card DOM in bounded time slices using `scheduler.yield()` with `setTimeout(0)` fallback and rejects stale render epochs. Two 4× CPU mobile Chromium rounds waited for all 69 organizer cards, exercised Select All/Invert and page-slot fallback, and verified all 69 exported pages' text/order with no overflow/page errors. Organizer construction measured 45–66ms, but full load-to-first-page was 4.63–6.21s and longest tasks were 544–961ms; this is not a verified performance improvement and remains partial. `pytest-id122-thumbnail-slicing-run1.log` passed 583 tests; run 2 underway. Evidence: `browser-id122-mobile-69page-studio-export.json`.

ID 37 follow-up — browser-local Crop PDF: added PDF-Lib crop-box changes with margin validation, connected the Crop UI fields to local worker options, disclosed the workflow in privacy/support copy, and bumped the worker/runtime/app/PWA cache versions. Two independent Chromium rounds scanned all 44 routes and content-checked 15 local workflows. The crop output preserved both page text markers and measured 270×160pt per page after margins of left 10, top 15, right 20, bottom 25 on 300×200pt pages; zero `/api/jobs` posts occurred during local operations. ID 37 remains PARTIAL (15/41 workflows; 26 remain). Evidence: `browser-id37-local-text-round1.json`, `browser-id37-local-text-round2.json`, `browser_id37_id242_local_processing.py`.

Post-Crop full regression and production-image check: two sequential current-source full-suite runs passed 583 tests (180.08s and 150.46s, 4 existing deprecation warnings each). The initial run exposed three stale expectations for the new truthful local-processing disclosure; fixed the older tests and FAQ route so they match. Latest production-mode local Docker build `sha256:971fb2ec8c8a17df78dbccc3fb66de5db879e4e510a86b0f98e24452b754a5d6` passed four-worker `/api/health`, and Chromium content-checked Forms, Metadata PDF/JSON, and Crop output (270×160pt with text retained). Zero `/api/jobs` and page errors; tmpfs only, container stopped. Docker linter still warns about the non-secret `PAPERPLANE_REQUIRE_AUTH=false` environment variable name. Evidence: `pytest-id37-local-crop-run1.log`, `pytest-id37-local-crop-run2.log`, `browser-id37-docker-worker-smoke.json`.
