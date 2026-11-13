# Phase 0 — tooling

- Pehle se available aur verified: Python 3.14.4, pytest 9.1.1, Playwright for Python, bundled Chromium 1217, PyMuPDF 1.27.2.3, Chrome, Poppler `pdfinfo`/`pdftotext`, aur browser console/network capture.
- Is audit ke liye koi package, plugin, MCP server, ya browser extension install nahi kiya. UI Design Guide skill pehle apply ki gayi thi; yeh repository dependency nahi hai.
- Docker CLI 29.6.2 maujood hai, lekin Docker Engine/Desktop Linux daemon ka named pipe `npipe:////./pipe/dockerDesktopLinuxEngine` available nahi tha. Image build aur container smoke run nahi ho saka.
- Phase 0 smoke: localhost par 375px emulation mein 69-page PDF Studio mein khula. Grayscale tool ne 14,951-byte PDF download ki; PyMuPDF ne 1 page khola aur rendered output ke 502,428 sampled pixels mein 0 colored pixels mile. Us smoke ke browser console/page errors 0 the. Evidence: `phase0-smoke.json`, `phase0-studio-375.png`, `phase0_color-audit_grayscale.pdf`.

# Launch status — HOLD

Is working tree ko production-ready sign-off nahi diya ja sakta. Khaas pending risks:

- AI provider local environment mein configured nahi hai. Real translation, grounded chat, summaries, injection guards, aur streaming ko provider ke saath verify nahi kiya.
- Catalog ke 37 locally available operations synthetic inputs se run hue; downloads kholkar page count, text, forms, spreadsheet/slides aur image content verify kiya. OCR ke liye Tesseract missing hai; AI Chat/Summary/Translate ke liye provider config missing hai. Har tool ke large/complex files aur har option combination abhi cover nahi hue.
- Studio ka page 1 first paint par 0.08s mein abhi blank/loading tha; 5s par render hua. Page jumps sahi render hue, lekin repeated fresh-open runs aur continuous wheel-scroll synchronization ka proof nahi hai.
- Reload test mein ek deletion aur page 5 do reloads tak restore hue; duplicate/reorder, AI document + poori chat-history restore, aur annotation reload ke poore flows nahi chalaye gaye.
- 500 MiB multipart upload, Docker image, production TLS, real device, native browser zoom, payment, OTP claims, Dropbox aur negative cloud-link cases pending hain.
- M-8 responsive sweep mein viewport overflow/unlabeled-control checks pass hue, lekin screenshot-level content/word-wrap review har state ke liye complete nahi hua. Emulation physical phone verification nahi hai.
- `pytest -q` pass hua, lekin suite pass hona akela launch proof nahi hai. Local testing mein 1 Starlette/httpx deprecation warning aayi.

Koi deployment, git push, payment, live account setting change, password/OTP attempt, ya API key update nahi kiya. Sab changes working tree mein uncommitted hain.

## Run aur test evidence

| Check | Result | Evidence / limit |
|---|---|---|
| Full suite, final source/test code | PASS — 265 passed, 0 failed, 116.00s, 1 deprecation warning | `pytest -q` |
| Python compile, JS syntax, diff whitespace | PASS | `python -m py_compile ...`, `node --check web/assets/app.js`, `node --check web/assets/page_organizer.js`, `git diff --check` |
| Responsive route matrix, final CSS/JS | Latest source: 48 routes × 5 widths × 4 zoom simulations × 2 themes × 2 sidebar states = 3,840 cases; 0 horizontal overflow, 0 unlabeled controls, 0 console errors, 0 page errors; 48 route screenshots. | `mobile-layout-matrix.json`; native browser zoom tested: `false` |
| Studio extract, desktop + phone | 1-page and 2-page selection each downloaded and opened in PyMuPDF; output page counts/text verified | `extract-1366-pages-1.pdf`, `extract-1366-pages-1-2.pdf`, `extract-375-pages-1.pdf`, `extract-375-pages-1-2.pdf` |
| Studio render/jumps | Latest 69-page trial blank/loading at 0.104s and rendered at 5.009s; a separate fresh trial showed “Page 1 is loading…” at 0.093s and the rendered page by 0.5s. Jumps 69/1/35 recorded the numeric input and active page slot immediately after Enter, before waiting for PDF.js render; both matched on every jump. | `final-browser-checks.json`, `studio-first-paint-375-after.png`, `studio-page1-375-after.png` |
| Studio reload/deletion | Page 69 deleted; 69→68; page 5 and count 68 restored on two reloads with toast | `studio-delete-debug.json`, `final-browser-checks.json`, `studio-delete-375-after.png` |
| Studio sidebar/export | At 375px drawer open, toolbar z-index 130 over sidebar 90; export tapped; 49,296-byte 68-page PDF opened | `studio-export-375-after-sidebar-open.pdf`, `studio-sidebar-open-375-after.png` |
| Owner Drive link | Latest local import HTTP 200 in 4.38s; visible filename/size/pages toast, 1-page PDF loaded, modal remained through async startup, 0 CSP/page/console errors | `final-browser-checks.json`, `cloud-import-drive-1280-after.png` |
| Translation failure/partial UI contract | Mocked failed mode shows “Translation failed” with 0 visible download links; partial mode is labelled and links “Download partial translation”; 0 browser/page errors. This does not test a real provider translation. | `translation-ui-smoke.json` |
| SEO/workflow copy on all 41 tool routes | HTTP 200 on each route; route-specific visible heading, intro, 3 steps, 3 FAQs, and JSON-LD matched the route context. | `tool-copy-audit.json` |
| Fill Form long JSON layout and content | Reproduced old text-input clipping (1,183 chars -> 7,871px scroll width at 1366px and 375px). New auto-growing textarea wraps with no document overflow; generated 1-page PDF opened in PyMuPDF and all four values matched at both widths. | `p2-ui-checks.json`, paired `p2-fill-form-{1366,375}-{before,after}.png`, `p2-fill-form-{1366,375}-after.pdf` |
| Compress default preset label | Selected text exactly “Under 100 KB (Govt / SSC Exam Form)” at 1366px and 375px; no horizontal overflow. Local clipping could not be reproduced. | `p2-ui-checks.json`, `compress-preset-{1366,375}-after.png` |
| Remaining P2 UI checks | Eight named tool buttons measured at 1366px and 375px: 7 available actions show whole labels without word splitting/overflow; AI Summarize is clearly labelled unavailable and disabled while its provider is unconfigured. Category heading at 1366px/1104px remains 28px below the sticky header after scrolling through the real app scroll container; all navigation tabs stay on one row without horizontal overflow. A 10-page synthetic metadata result shows “1 topic” / “2 topics” and omits an absent date. Five mocked auth restores keep cached identity visible, suppress guest controls, show quota “—” while pending, then show `6 / 100`; cache is a display hint only and server auth remains authoritative. | `p2-remaining-checks.json`, `auth-restore-smoke.json`, `p2-run-button-*.png`, `p2-sticky-heading-*.png`, `p2-metadata-*.png`, `auth-restore-pending-375.png` |

The local browser app used a fresh temporary audit data directory for the final browser sweeps. Test runs also use a per-run temporary data directory via `tests/conftest.py`.

## Changed working-tree files

| File | Reason |
|---|---|
| `ai_engine.py` | No-document/false-premise handling, broader capital facts, citation normalization/filtering, summary citation instructions, and no-output translation failure. |
| `converters.py` | Excel/CSV to PDF wrapped-table renderer ab cell text clip nahi karta; OCR page counts/error behavior bhi report karta hai. |
| `server.py` | Real Tool Desk route and legacy aliases, honest AI/provider status and translation gating, AI/Studio quota accounting, cloud/import validation, and OCR result reporting. |
| `web/assets/app.js` | Studio/AI reload state, route/modal race, page render/jump behavior, cloud validation/feedback, Tool Desk navigation, quota/labels, responsive interactions, and honest translation failed/partial UI. |
| `web/assets/page_organizer.js` | Extract download fallback/error handling, mutation page preservation, delete confirmation/undo and reload page target. |
| `web/assets/styles.css` | Mobile Studio viewport/thumb/canvas layout, toolbar reachability, responsive cards/sidebar and overflow fixes. |
| `web/index.html` | Tool Desk/studio/AI work controls and accurate local-retention copy; removed misleading quota copy. |
| `tests/conftest.py` | Isolate persistent test state in a temporary per-run directory so quota tests do not consume the developer’s local app quota. |
| `tests/test_ai_workflows.py` | Assert translation failure rather than source-disguised success. |
| `tests/test_launch_audit_v3_hardening.py` | Align deterministic local-extraction assertion with the visible page citation marker. |
| `tests/test_platform.py` | Provide deterministic translated test blocks; no provider is required to test layout output. |
| `tests/test_launch_audit_v5.py` | Regression coverage for quota/provider/OCR/routes/citations/retention/CSP labels/cloud startup/translation UI contract and complete Excel/CSV cell output. |
| `reports/launch-audit-v5/` | Before/after screenshots, matrix/browser evidence, opened PDF outputs, scripts, JSON logs and this report. Exact artifact inventory is in `manifest.json`. |

## Section 4 — P0 launch blockers

| Item | Status | Before → after / remaining |
|---|---|---|
| P0-1 Studio Extract silent/no download | **PARTIAL** | Final desktop 1366px and emulated 375px: selections `[1]` and `[1,2]` downloaded as `extracted_1_...pdf` / `extracted_1-2_...pdf`; outputs opened in PyMuPDF as 1 and 2 pages with extracted text. The live report’s page-67 reproduction was not repeated; page 67 specifically and multiple selected non-adjacent pages remain unverified. |
| P0-2 Studio page-1 blank/render race | **PARTIAL** | Latest 69-page run A: blank/loading canvas at 0.104s, rendered at 5.009s, still rendered at 15.046s/30.038s. Fresh run B visibly showed “Page 1 is loading…” at 0.093s, then the rendered page at 0.5s. Jumps 69/1/35 rendered in 0.172–0.263s. The live persistent-blank report was not reproduced; first-render timing varied between runs and more fresh-open/device trials remain. |
| P0-3 reload loses position/deletes | **PARTIAL** | Before-fix local run already restored a document inconsistently; final scripted test loaded 69 pages, went to page 5, deleted page 69, then reloaded twice: both times page 5/count 68 restored with a toast. `Clear saved work` controls exist and the banner now distinguishes unsaved annotations. Duplicate/reorder, AI PDF + full chat history, and clear-control round-trip were not end-to-end tested. |
| P0-4 translation returns source as success | **PARTIAL** | Backend zero-translation path now errors without producing a translated output. Final browser mock verifies failed mode has no download; partial mode is explicitly labelled and warns that original-language text remains. Real Spanish/second-language translation and two-line content verification remain impossible locally because the provider is unavailable (`/api/operations` reports `SERVICE_UNAVAILABLE`). |
| P0-5 owner Drive link silent no-op | **FIXED for the reported success path** | Before: local startup race could close an explicitly opened cloud modal while `/api/operations` was pending. After: modal and URL survive route resolution. The owner’s supplied Drive link imported via `/api/cloud/sync` (200) in 4.38s; success toast named `cloud_imported.pdf`, 0.53 MB, 1 page; Studio showed page count 1. Negative-link outcomes are tracked under R-12 and Section 10-D. |

## Section 5 — P1

| Item | Status | Evidence / remaining |
|---|---|---|
| P1-6 Summary citation/chip nondeterminism | **PARTIAL** | Unit regression covers bracket, plain `Page`, `(p.)`, ranges, unsupported pages and template placeholders; formatting is deterministic in that test. Three real 69-page provider summaries with text/chip counts were not run. |
| P1-7 False facts: author/page/date/capital/no document | **PARTIAL** | Local no-document Shanghai test returns “Beijing is the capital of China, not Shanghai.” Broader local guard/capital list is covered in code/tests. False author/date/page-count with a real PDF and actual provider answer were not run. |
| P1-8 Incremental streaming | **PARTIAL** | Unit tests cover emitted deltas, stages and no restart after partial output. Provider is unavailable; no three timed long-answer browser observations were made. |
| P1-9 Slow delete/no success toast | **PARTIAL** | One selected page deletion changed count 69→68 and showed “Deleted 1 page(s).” Local browser run has a successful toast and reload persistence. Multi-page deletion and measured time-to-count/toast were not captured. |
| P1-10 Page Numbers first attempt hang | **NOT TESTED** | No three consecutive first-attempt Page Numbers output runs or stalled-job timeout simulation were performed. |
| P1-11 `/developers` dead spec links/footer self-loop | **PARTIAL** | Fail-closed docs and route/content contracts are covered by suite. Both spec links were not clicked through in a browser, and the footer self-loop behavior was not independently verified end-to-end. |
| P1-12 missing real Tool Desk | **PARTIAL** | `/tool-desk` now returns a real directory view (200) and a route regression asserts its container. From-home plus five distinct tool-page navigation was not scripted. |
| P1-13 `/fill-form` 404 / stale route aliases | **PARTIAL** | Local regression verifies `/fill-form` redirects to `/fill-pdf-form` and `/ai-translate` to `/translate-pdf`. Every historical alias was not enumerated/tested. |

## Section 6 — P2

| Item | Status | Evidence / remaining |
|---|---|---|
| P2-14 Copy/paste workflow/FAQ text on tool pages | **PARTIAL** | All 41 current server-rendered pages were checked: each visible heading, intro, 3 tool-specific steps, 3 FAQs, and matching structured data pass. The reported live duplicate/previous-tool baseline did not reproduce in this local build, so a live before/after comparison remains unverified. Full route text inventory: `tool-copy-audit.json`. |
| P2-15 Run-button labels break mid-word | **FIXED in current local build** | Captured all eight reported actions after uploading a sample PDF at 1366px and 375px. Seven available actions show their complete label, no word breaks or viewport overflow. AI Summarize is explicitly marked unavailable and disabled because no AI provider is configured. Cannot compare against the remote live build from this local run. |
| P2-16 Sticky top-nav overlaps headings/wraps | **FIXED in current local build** | Scrolled the actual `.main-area` container to Organize PDF at 1366px and 1104px. Heading remained 28px below the 76px sticky header; all five navigation tabs stayed on one row with no horizontal/document overflow. The first audit attempt incorrectly used window scrolling; corrected measurement and screenshots are in `p2-remaining-checks.json` and `p2-sticky-heading-{1366,1104}.png`. |
| P2-17 Compress preset truncates | **PARTIAL** | Full selected label and 0 document overflow verified at 1366px and 375px; no truncation reproduced locally. The reported live build could not be inspected or compared. Default was preserved exactly per owner direction. |
| P2-18 Page counter/spinbutton lag | **FIXED in current local build** | After Enter, before waiting for the PDF canvas, the numeric input and active page slot immediately matched 69, 1, and 35; each destination canvas then rendered. The earlier delayed counter state was not captured as a pre-fix artifact. See `final-browser-checks.json`. |
| P2-19 Quota “Checking usage…” flash | **FIXED in current local build** | Five route loads with delayed `/api/auth/me`: while pending quota displays a neutral “—” rather than “Checking usage…”, then switches to authoritative `6 / 100` after `/api/operations` responds. The auth response was mocked for this UI-timing check; local operations endpoint returned 200. |
| P2-20 User chip disappears during auth restore | **FIXED in current local UI state** | Five route loads with a delayed authenticated response kept the cached email/avatar visible, hid guest/upgrade controls, and did not grant cached entitlements. Server-auth response restored account/quota state. Browser auth response was mocked; a live signed-in account was not used. |
| P2-21 Metadata “1 topics” / “Not detected” | **PARTIAL** | Synthetic 10-page metadata result rendered “1 topic” and “2 topics” at 1366px and 375px, and omitted the absent Document Date row. The UI formatting is verified; a real AI extraction/provider result and its exported file remain untested. |
| P2-22 Fill Form JSON text overflow | **FIXED** | Reproduced the old single-line control: 1,183 JSON characters overflowed the input's 972px client width to 7,871px at desktop and phone. Replaced it with a wrapping, auto-growing textarea and included it in submitted job options. At 1366px and 375px the page had no horizontal overflow; the real filled form output opened as a 1-page PDF and all four AcroForm values matched exactly. Before/after screenshots and PDFs: `p2-ui-checks.json`. Regression test added. |

## Section 7 — Mobile

Decision: Studio phone layout now keeps its shell inside the viewport, uses a scrollable vertical two-column thumbnail grid, horizontally scrollable toolbar ribbons and a separately scrollable page canvas. Isse long 69-page thumbnail strip reachable hoti hai aur fixed bottom nav ke peeche canvas controls nahi jaate. Yeh emulated-browser decision hai; physical device se verify nahi hua.

| Item | Status | Evidence / remaining |
|---|---|---|
| M-1 Sidebar toolbar ke upar aa jata tha | **PARTIAL** | 375px emulation: sidebar z-index 90, toolbar 130; drawer khula rehne par Export PDF tap hua aur 68-page output khula. Physical phone tap abhi nahi. `studio-sidebar-open-375-after.png`. |
| M-2 Clipped/duplicate toolbar labels | **PARTIAL** | 48-route matrix mein horizontal overflow 0; toolbar screenshots mein controls reachable hain. Har toolbar button par text/pseudo-label uniqueness automated assertion nahi hai. |
| M-3 Mobile scroll model | **PARTIAL** | Sab controls contained scroll areas se accessible hain, canvas reachable hai. Prompt ke exact “header ke alawa sab document body ke saath scroll kare” model ka implementation nahi; mobile Studio apne panels/canvas mein scroll karta hai. |
| M-4 Blank thumbnail | **PARTIAL** | 69-page thumbnails 375px vertical grid mein navigable hain; screenshot evidence hai. Har thumbnail ka content pixel-by-pixel verify nahi hua. `studio-thumbnails-vertical-375-after.png`. |
| M-5 Blank/narrow main canvas | **PARTIAL** | 375px par canvas 346×489 render hua aur pixel samples non-white the. 333px target width separately re-run nahi hua. `studio-page1-375-after.png`. |
| M-6 AI Docs banner/Test AI spacing | **PARTIAL** | 375px AI Docs screenshot aur matrix available hain; visual spacing ka exact measurement/as-written content review nahi hua. `mobile-ai-docs-375.png`. |
| M-7 AI Docs empty/loaded/chat flow | **PARTIAL** | Exact phrase “Upload PDF to chat” code mein hai; memory/clear-work copy aur loaded-file UI exist karte hain. Provider unavailable hone se empty → pre-upload document error → loaded page citation → no-document answer ka complete 375px flow nahi chala. |
| M-8 Full phone self-audit | **PARTIAL** | Final source re-run: 48 routes (home, Tool Desk, Studio, AI Docs, Download, Settings, Pricing + 41 tool routes), 360/375/390/414/768px × 80/100/125/150% zoom simulation × light/dark × sidebar open/closed: 3,840 cases, 0 horizontal overflow, 0 unlabeled controls, 0 console/page errors, 48 route screenshots. Zoom `documentElement` simulation tha, native browser zoom nahi; content clipping, contrast/readability, every blank state, and all states manually inspect nahi hue. Full JSON and screenshots: `mobile-layout-matrix.json`. |
| M-9 CSP/eval/form labels | **PARTIAL** | PDF.js `isEvalSupported:false`; matrix control-label scan 0 missing labels; final Drive browser run mein CSP violations 0. Original live CSP-blocked resource/eval caller ko local par reproduce/identify nahi kiya. CSP still has `style-src 'unsafe-inline'` and `script-src 'wasm-unsafe-eval'`; exact need/residual review open hai. |
| M-10 Fixed bottom nav/top labels | **PARTIAL** | Matrix mein viewport overflow 0; 48 route screenshots available. AI Docs/Studio bottom scrolled copy + top labels ko every width par separate manually assert nahi kiya. |
| M-11 Tiny centered AI Docs column | **PARTIAL** | 375px screenshot/matrix mein viewport overflow nahi. Original shot ka exact 333px width record nahi tha aur 333px screenshot re-create nahi hua. |

## Section 8 — Code-level risks

| Risk | Status | Evidence / remaining |
|---|---|---|
| R-1 INR-only checkout/SEO/UI | **PARTIAL** | Local regression tests assert USD checkout returns HTTP 400 and checkout order currency is INR; SEO `priceCurrency` is INR. No real purchase/receipt/email was inspected. Local code’s displayed tiers: Free ₹0, Exam ₹19, Student ₹49/mo or ₹399/year, Pro ₹250/mo or ₹999/year, Cyber Café ₹299, Developer ₹750; every tier surface was not manually compared. |
| R-2 API docs fail-safe gating | **FIXED in local tests** | Automated test covers docs disabled by default and non-production/prod behavior. Production proxy deployment was not exercised. |
| R-3 Provider/model disclosure | **PARTIAL** | Automated test removes provider/model fields from Developer AI API output; no configured-provider chat/summarize/SSE/test-connection response capture was possible. |
| R-4 AI timeout/retry paths | **PARTIAL** | Provider calls have bounded timeouts/retry logic; tests cover transient retry before first output and no retry after partial streaming. No end-to-end timeout table/per-endpoint latency or Executive Brief three-run test was produced. |
| R-5 Merge timeout | **PARTIAL** | Code retains `MERGE_TIMEOUT_SECONDS = 120.0`; only tiny one-page merge smoke output was produced. Reverse-proxy timeout and largest tested page/MB size not established. |
| R-6 Quota/static fallback/single source of truth | **PARTIAL** | Misleading “Zero daily caps” copy removed; plan limits are returned via shared `plan_limits_payload`, and frontend updates from API. Delayed/failing planLimits response and all specialty tier limits were not exercised. |
| R-7 500 MiB boundary and full upload | **PARTIAL** | Automated test asserts exact 524,288,000-byte Pro limit and 50 MiB Free limit. A 500 MiB multipart upload/background-job run and Free >50 MiB 413/no-count integration check were not run. |
| R-8 CSP residual directives | **PARTIAL** | Verbatim local CSP is below; final Cloud run recorded no violation. `unsafe-inline` remains in style-src and `wasm-unsafe-eval` in script-src; each dependent resource was not isolated or independently justified. |
| R-9 Quota bypass | **PARTIAL** | AI/Studio successful billable endpoints increment usage and block-before-work paths have tests; invalid upload is tested not to increment. Free-tier account hammer test and complete audit of every billable endpoint are not done. |
| R-10 AI status endpoint truth | **PARTIAL** | Unit test with simulated Bluesminds key verifies `/api/integrations` and `/api/operations` reflect configured/unconfigured state. Real configured provider could not be used. |
| R-11 OCR zero-result success | **PARTIAL** | Synthetic all-page OCR failure raises an error and creates no output; page counts are included in results. A clean OCR document/text-layer viewer check was not run. |
| R-12 Cloud error feedback | **PARTIAL** | Owner Drive success provides filename/size/pages and async startup no longer dismisses the modal. Bad URL, denied/non-public Drive, direct PDF, Dropbox, non-PDF and timeout visible-error cases were not run. |

Local CSP response header (verbatim):

```text
default-src 'self'; script-src 'self' 'wasm-unsafe-eval' https://accounts.google.com https://sdk.cashfree.com https://cdn.jsdelivr.net; worker-src 'self' blob:; style-src 'self' 'unsafe-inline' https://accounts.google.com https://fonts.googleapis.com https://cdn.jsdelivr.net; font-src 'self' https://fonts.gstatic.com data:; img-src 'self' data: blob: https:; connect-src 'self' https://accounts.google.com https://api.cashfree.com https://sandbox.cashfree.com; frame-src 'self' https://accounts.google.com https://sdk.cashfree.com; object-src 'none';
```

## Section 9 — independent tester gaps

| Gap | Status | Reason/evidence |
|---|---|---|
| Guest mode, gating and pricing | **PARTIAL** | Local browser matrix was guest mode; role/tier gating and all pricing copy were not checked as separate journeys. |
| Correct-password Protect → Unlock round-trip | **FIXED for synthetic sample** | Protected output opens only after the supplied test password; correct Unlock returns readable content, and wrong password is rejected. |
| Downloaded output content | **PARTIAL** | 37 available catalog outputs plus Studio Extract were opened and checked; OCR and provider-backed AI outputs remain unavailable. Large and malformed cases are not covered. |
| Synthetic Aadhaar mask end-to-end | **FIXED for synthetic sample** | `1234 5678 9012` masks the first eight digits and leaves the last four in output text. |
| Extract filename/size | **FIXED for tested selection** | Desktop/mobile 1- and 2-page downloads have filenames, sizes and verified content in PyMuPDF. Page 67 selection remains pending. |
| Full 41-tool catalog | **PARTIAL** | 37 locally available operation jobs produced downloads that were opened and content/structure checked; OCR and three provider-backed AI tools are unavailable here. Large inputs, every option combination and all damaged-file cases remain open. See the per-tool table. |
| 1280/1366/mobile and physical devices | **PARTIAL** | Cloud at 1280, Extract at 1366 and responsive emulation at 5 widths; physical device/laptop hardware not tested. |
| TEST payment / INR confirmation / badges | **NOT TESTED** | Payment was not completed, consistent with the no-payment instruction. |
| Google/Dropbox | **PARTIAL** | Owner-provided Google Drive link succeeded. Dropbox and direct/bad/non-PDF links were not tested. |
| OTP code claims | **NOT TESTED** | No claims/expiry/reuse/attempt/cooldown/rate-limit verification was performed. No live OTP request or guessing occurred. |
| Production TLS certificate | **NOT TESTED** | No external production/TLS endpoint check. |
| Docker Engine image + smoke | **NOT TESTED** | Docker CLI exists, daemon pipe missing; `docker info` could not connect. |
| Production AI/payment providers | **NOT TESTED** | No production API key or payment provider used. |
| Excel wrong-type handling | **PARTIAL** | Valid XLSX and CSV to PDF workflows passed; rejection of invalid/non-Excel uploads was not exercised. |
| PDF Metadata 502 behavior | **PARTIAL** | Valid metadata update/readback passed; service error/502 path was not exercised. |
| PDF to Markdown timeout | **NOT TESTED** | No conversion run. |
| Cloud Import returning PNG | **PARTIAL** | Owner Drive success returned a valid one-page PDF which Studio opened; no non-PDF/image URL negative case. |
| Stale/dead tool routes | **PARTIAL** | `/fill-form` and `/ai-translate` aliases verified; every historical route was not checked. |

## Section 10 — A–H final protocol

| Protocol | Status | Result |
|---|---|---|
| A — 41 tools: upload/run/download/open/content | **PARTIAL** | 37 available catalog operations completed upload → job → download → output checks. OCR and AI Chat/Summary/Translate are unavailable due missing local dependencies/provider. Large-volume and edge-case inputs remain open. Per-tool table below. |
| B — AI flows/guards | **PARTIAL** | No-document false-premise guard and citation parser covered by local tests; provider workflows, six guards, summary repetitions, page 69 and translation content not tested. |
| C — Studio | **PARTIAL** | Render/jumps, page-69 delete/page-5 restore, one/multiple Extract, sidebar Export and PDF open tested. Continuous scrolling, 1+multi delete latency, annotation reload, page-67 Extract, thumbnail pixel audit not all verified. |
| D — Cloud | **PARTIAL** | Owner’s Drive link success/startup-race verified. Dropbox, direct PDF, bad/non-PDF and timeout responses not tested. |
| E — Pages/routes | **PARTIAL** | Tool Desk/studio/legacy aliases tested and 48 route UI shells loaded in matrix. `/developers` spec links, five-page navigation proof and Cloud modal Escape/backdrop/navigation-block tests not all run. |
| F — Mobile matrix | **PARTIAL** | 3,840 emulated CSS states, zero overflow/unlabeled/errors. Native zoom/physical devices and detailed copy/visual check every state not tested. |
| G — Regression | **PARTIAL** | Verified local false-premise, OCR all-failed, quota, routes, citation contract, Studio persistence, grayscale, Extract and Drive path. Provider/live/most catalog regressions remain open. |
| H — Full suite | **PASS** | Final source/test command after Excel/CSV renderer and regression test: `pytest -q`: 265 passed, 0 failed, 116.00 seconds, 1 Starlette/httpx deprecation warning. |

### A — Catalog content verification (41 named tools)

37 available operations completed an HTTP job, download, and output check. OCR and AI Chat/Summary/Translate were skipped because the local server reported their dependency/services unavailable. `catalog-output-audit.json` contains job outcomes; Office outputs use format-specific readback. Excel→PDF clipping was reproduced in LibreOffice output and corrected with a wrapped renderer, then rerun on the latest source. `catalog-excel-fixed-page-1.png` shows the complete table; the full cell-value assertions are covered by the final suite.

| Catalog tool | Input/output and content verification | Status |
|---|---|---|
| Merge PDF | Two 2-page synthetic PDFs merged; downloaded output opened as 4 pages with both page markers. | FIXED (sample) |
| Split / Extract | Selecting page 1 produced a 1-page PDF with expected text. “Split all pages” ZIP path was not run. | PARTIAL |
| Remove pages | Removed page 1 from a 2-page input; output opened as 1 page containing page 2 only. | FIXED (sample) |
| Rotate PDF | Output opened as 2 pages; PyMuPDF reports 90° rotation. | FIXED (sample) |
| Page Organizer | Reordered page 2 before page 1; first output page marker matched. | FIXED (sample) |
| Scan to PDF | Synthetic image produced an openable 1-page PDF. Deskew/contrast quality was not independently scored. | PARTIAL |
| Compress PDF | Output opened as 2 pages, retained text and shrank 5,053→1,587 bytes under the 100 KB target. Large/raster-heavy input not tested. | PARTIAL |
| Repair PDF | Valid 2-page input stayed readable; corrupt/truncated recovery was not exercised. | PARTIAL |
| OCR PDF | No successful OCR output text-layer check. All-failed case is covered by a unit test only. | NOT TESTED |
| JPG/PNG to PDF | Two PNG inputs produced a 2-page PDF; both pages opened. | FIXED (sample) |
| Word to PDF | Synthetic DOCX converted to a readable 1-page PDF; marker text survived. | FIXED (sample) |
| Excel to PDF | LibreOffice clipped cell values; wrapped renderer fix rerun preserved “Application” and the full long cell value. CSV readback is covered by a regression test. Large/legacy .xls cases remain. | FIXED (sample) |
| PowerPoint to PDF | Synthetic one-slide PPTX converted to a readable PDF with title/content marker. | FIXED (sample) |
| HTML to PDF | Public `example.com` rendered by local headless Chrome; PDF opened and expected page text survived. | FIXED (sample) |
| PDF to JPG | Two-page output ZIP opened; both entries are valid JPEGs. | FIXED (sample) |
| PDF to Word | DOCX opened with python-docx; both pages’ text and source markers survived. | FIXED (sample) |
| PDF to Excel | XLSX opened with openpyxl; table headers and all three rows/values match input. | FIXED (sample) |
| PDF to PowerPoint | PPTX opened with python-pptx; two slides each contain a valid full-page image. Editable mode was not tested. | PARTIAL |
| PDF to PDF/A | Output opens and carries the PDF/A-1b metadata marker; no independent ISO/veraPDF conformance validation. | PARTIAL |
| PDF to Text | Text output opened; page headings and exact source markers survived. | FIXED (sample) |
| PDF to Markdown | Markdown opened; page headings, markers and table rows survived. | FIXED (sample) |
| Edit PDF | Output reopened and contains the inserted text marker. | FIXED (sample) |
| Annotate PDF | Output reopened with inserted annotation text; highlight/shape/sticky-note variants were not all run. | PARTIAL |
| Crop PDF | Output reopened with both page dimensions reduced by the requested margins. | FIXED (sample) |
| Redact PDF | `TEST_SECRET` removed from output text after redaction. | FIXED (sample) |
| Watermark PDF | Output reopened with requested watermark text present. | FIXED (sample) |
| Page Numbers | Output reopened with “Page 1 of 2” text present. First-attempt timing was not measured here. | FIXED (sample) |
| Protect PDF | Output is encrypted; supplied password decrypts it and both pages remain readable. | FIXED (sample) |
| Unlock PDF | Correct password output reopened unencrypted with 2 pages; wrong password failed with “Incorrect password”. | FIXED (sample) |
| Sign PDF | Visual signature text is present in reopened output. Digital certificate signature/validation was not tested. | PARTIAL |
| Compare PDF | Text comparison output includes the known changed marker. | FIXED (sample) |
| Fill PDF Form | Reopened output reports all four AcroForm values exactly as submitted. | FIXED (sample) |
| PDF Metadata | Reopened output metadata contains the requested title. | FIXED (sample) |
| AI PDF Chat | Provider unavailable; no provider answer output. | NOT TESTED |
| Smart Metadata | Local fallback extraction returned readable structured JSON with expected keys; provider-backed accuracy on invoices/resumes was not tested. | PARTIAL |
| AI Summarize | Provider unavailable; no summary file/content verified. | NOT TESTED |
| AI Translate | Provider unavailable; no translated PDF/content verified. | NOT TESTED |
| SSC Photo Resizer | JPEG opened at 350×450 and 35 KB, inside the 20–50 KB preset range. Other presets were not tested. | FIXED (sample) |
| Mask Aadhaar Card | Synthetic `1234 5678 9012` input masks the first eight digits and leaves `9012`. Other layouts/formats were not exercised. | FIXED (sample) |
| Convert to Grayscale | Phase 0 output opened in PyMuPDF; 1 page, 0 colored pixels among 502,428 samples. | FIXED |
| Flatten PDF Forms | Filled-form output reopened with zero interactive widgets remaining. | FIXED (sample) |

### G — Section 3 regression gate, each item

| Regression | Status | Evidence / remaining |
|---|---|---|
| Configured AI connection and general/page answers | **NOT TESTED** | Local AI service unavailable; no provider key used. |
| General false-premise correction | **PARTIAL** | Unit test verifies Shanghai/China corrected to Beijing without document. |
| Executive Brief first-attempt 60–120s | **NOT TESTED** | No provider-backed request. |
| Page-69 honesty and missing-fields honesty | **NOT TESTED** | No provider-backed answer. |
| All six injection guards | **NOT TESTED** | No provider-backed guard test. |
| OCR succeeds on clean scanned notes | **PARTIAL** | Zero-success failure test passes; successful OCR content not tested. |
| AI Docs empty-state wording/card/loaded state | **PARTIAL** | Copy, card, banner and screenshots exist; full provider-driven chat sequence not tested. |
| Studio sidebar, thumbnails, continuous scroll sync | **PARTIAL** | Sidebar open/export and page jumps verified. Continuous wheel-scroll 5→36 and each thumbnail content not proven end-to-end. |
| Catalog PDF/image/office workflows | **PARTIAL** | 37 available outputs were opened and checked with synthetic inputs, including password protection, filled AcroForm values, redaction, photo dimensions/size and grayscale pixels. OCR and provider-backed AI are unavailable; Repair used a valid PDF and PDF/A was not checked with an independent conformance validator. |
| Cloud modal block/Escape/outside click | **NOT TESTED** | Cloud import startup race/positive import tested, not these close/block gestures. |
| Pricing INR, Compress default, one signed-in header, download waitlist | **PARTIAL** | INR checkout/SEO contracts in tests; Compress default unchanged; no authenticated reload/receipt; waitlist screen exists but no full download journey. |
| Prior code-confirmed fixes: IndexedDB, dialog, hidden file input, SEO docs aliases, quota, timeout, `/remove-pages` alias | **PARTIAL** | Reload/delete, route aliases, limits and docs covered in tests; complete feature-by-feature live regression not done. |

