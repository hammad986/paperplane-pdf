# Paperplane v7 Launch Audit — Final Report

Date: 8 November 2026  
Audit target: local repository build at http://127.0.0.1:8502  
Decision: **HOLD — deployment sign-off nahin diya ja sakta.**

## Pehle yeh zaroor padhein

Aapne confirm kiya tha ke koi local AI provider configured nahin hai. Isliye Executive Brief, AI Summary, Translate, document-grounded chat, citations, streaming, false-fact correction, injection guards aur AI-backed extraction ko provider ke saath run karke verify nahin kiya. Local endpoints ne do repeat probes mein sahi aur imaandaar state dikhayi: provider missing, summary unavailable/disabled, fallback active nahin, aur koi model-inference call nahin. Is limitation ko “pass” nahin maana gaya.

Cloud Import ke liye aapke diye public share se ek chhota 1-page PDF mila (554,620 bytes). Public-share/direct-download paths do consecutive probe runs mein PDF ke roop mein khule aur size/page count match hue. Restricted share ne public access/login wali wajah ke saath reject kiya. Yeh aapki 69-page, 5.46 MB notes.pdf ke Cloud Import ka proof nahin hai; UI toast, queued-file count aur retry ke baad duplicate na banne ka bhi browser proof nahin hai.

Aapki 69-page notes.pdf local layout probes mein use hui. P0-3 ki delete/reorder/duplicate + reload retention sequence is final round mein run nahin hui. Retention ka banner hata kar Clear controls Privacy Settings mein rakhe gaye, taaki unverified persistence ka promise na rahe. Isse retention kaam karta hai, yeh prove nahin hota.

100% bug-free ya deployment-ready kehne ke liye evidence nahin hai. Neeche har requested area ka status alag diya hai. “FIXED” sirf us scoped behavior ke liye hai jiska repeat evidence hai; composite/partial coverage ko PARTIAL hi rakha gaya hai.

## Kya badla

- AI Docs aur Studio ke empty/loaded layouts ke liye reserved regions aur stable panel sizing rakhi, taaki PDF load aur result slots khulne par cards ka measured geometry jump na kare (web/assets/styles.css:9471).
- Studio PDF.js canvas rendering ko per-page queue kiya, jisse ek hi page canvas par concurrent render race kam ho (web/assets/app.js:2377).
- Studio mobile pages drawer mein page actions ke liye alag slot aur wrapped controls add kiye; narrow widths ke liye toolbar sizing/wrapping sudhaari (web/index.html:373, web/assets/app.js:807, web/assets/styles.css:9605).
- Ambiguous memory/retention banners hataaye; AI/Studio saved-work clear controls Privacy Settings mein available rakhe (web/index.html:1732 onward).
- Cloud Import mein original response filename/size metadata preserve ki, supported Drive share URLs ko direct-download format mein map kiya, PDF signature/openability/page count validate kiye aur errors ko reason ke saath return kiya (converters.py:259, server.py:5540).
- Provider missing ho to AI status ko sach dikhaya; UI summary ko disabled state mein rakhti hai.
- Quota copy ko free web tools, paid web tools aur Developer API quotas ke alag scopes mein likha; Exam Photo & Signature Resizer naming ko relevant page/catalog headings mein align kiya.

Exact changed project files:

- converters.py
- server.py
- web/assets/app.js
- web/assets/styles.css
- web/index.html
- tests/test_launch_audit_v7.py

Audit scripts, reports, screenshots aur JSON/log evidence reports/launch-audit-v7/ ke andar hain. Koi commit, push, deploy, payment, credential/API-key change ya live-account setting change nahin hua.

## Test evidence

Final source par poora suite do consecutive runs hua:

- Command: **python -m pytest -q**
- Run 1: **282 passed, 0 failed, 1 warning; 95.01 s**
- Run 2, bina source change ke: **282 passed, 0 failed, 1 warning; 82.55 s**
- Warning: Starlette TestClient ke saath httpx use deprecated hai; Starlette message httpx2 install karne ko kehta hai. Warning suite fail nahin karti.

Consecutive browser probes:

- **python reports/launch-audit-v7/responsive_probe.py** — 49 measured states; phir same script dobara. Dono runs mein Chromium 147.0.7727.15, document/body width match, empty-vs-loaded measured geometry mismatch 0, clipped visible elements 0, page errors 0, console errors 0.
- **python reports/launch-audit-v7/tool_pages_responsive_scan.py** — phir same script dobara. Dono runs mein 41 tool cards, 6 sections, 30 selected-page screenshots; tested matrix mein overflow, wrapped run buttons, visible unlabelled controls aur duplicate how-to-step issue lists empty; page/console errors 0. Is scan ne tool pages ki layout/routes dekhi; 41 PDF outputs ka content open karke inspect nahin kiya.
- **python reports/launch-audit-v7/cloud_import_probe.py** — user-provided URLs ke saath do runs. Har run mein public share aur direct-download valid PDF ke roop mein khule; restricted share HTTP 400 with access/login explanation; invalid ID HTTP 400 with upstream 404. Dono successful public paths ne same 554,620-byte, 1-page file diya.
- **python reports/launch-audit-v7/provider_settings_probe.py** — do runs. Capabilities HTTP 200 par executive_brief_available=false / ai_service_not_configured; connection check HTTP 200 par configuration_missing; summary button disabled; inference calls 0; browser errors 0. AI task/output test isliye NOT TESTED hai.
- **node --check web/assets/app.js** — pass.
- **python -m py_compile server.py converters.py tests/test_launch_audit_v7.py reports/launch-audit-v7/responsive_probe.py reports/launch-audit-v7/tool_pages_responsive_scan.py reports/launch-audit-v7/provider_settings_probe.py** — pass.
- **git diff --check** — pass; Git ne changed files ke line-ending conversion warnings dikhaye (LF se CRLF), whitespace errors nahin.

PDF size/page-count evidence: supplied notes.pdf = 5,456,746 bytes, 69 pages. Layout probe ne loaded first-page state ko verify kiya; complete 69-page navigation/jump sequence is run mein nahin hui.

Important baseline gap: reports/launch-audit-v7/phase0-smoke.json ek pehle se chal rahe port 8501 ko hit karta tha aur 54,433-byte synthetic 69-page fixture dikhata hai, jabki final build port 8502 par test hui aur aapki notes.pdf 5,456,746 bytes thi. Isliye us artifact ko final build ka comparable pre-fix baseline nahin maana gaya. Before/after screenshots maujood hain, lekin har fix ke liye same machine, same PDF, same state ka paired measurement nahin.

## Section 3 — Aapke 5 reference screenshots aur layout

| Item | Status | Kya verify hua / kya baaki hai |
|---|---|---|
| 3A — AI Docs stable grid | PARTIAL | Empty aur loaded states 360, 375, 768, 1104, 1366, 1920 widths aur light/dark combinations mein responsive probe hue. Dono repeat runs mein measured empty-vs-loaded geometry mismatch 0 aur clipping 0. Executive Brief generated state provider ke bina nahin bana; target ke sab 15 brief-state screenshots bhi nahin hain. |
| 3B — document loaded hone par greeting | NOT TESTED | Provider configured nahin; hey/hello/how are you ke 6 exact answers aur document question citation test nahin hue. |
| 3C — Synthesis badge/pills | PARTIAL | Sampled AI layouts mein clipped visible elements 0 the. Har badge/pill ko 360–1920 aur 80–150% browser zoom par individually audit nahin kiya. |
| 3D — mobile Studio | PARTIAL | 360/375 par page-actions slot, wrapped toolbar controls aur canvas reachability ke responsive screenshots bane; 375px Pages drawer state mein 4 page actions mili. Sidebar ke saath Export tap, har toolbar action aur full phone workflow export test nahin hua. |
| 3E — all-view reference redesign | PARTIAL | Mobile, laptop aur desktop layout defects par targeted fixes hue; 3E ka naya visual structure poori tarah replace nahin hua. Purana Studio/AI/Tool layout abhi bhi shipped hai. Screenshot 5 jaisa top action row, bottom Pages/Properties bar aur slide-over panels end-to-end implement nahin hue. |

Screenshot evidence: layout-v7-ai-* aur layout-v7-studio-*; selected tool screenshots tool-merge-pdf-*, tool-compress-pdf-* aur tool-ai-translate-* mein hain. Studio/AI screenshots 375 aur 1104 par hain; anya listed widths automated measurement mein covered hain, har width par PNG nahin.

## Section 4 — regression gate

| Gate | Status | Result |
|---|---|---|
| Tool Desk directory | PARTIAL | Directory scan ne 41 tools / 6 sections dobara dekhe. Home aur tool page se har nav entry click-path separately nahin kiya. |
| /fill-form, /ai-translate, /remove-pages redirects | NOT TESTED | Is final v7 browser pass mein redirects ko request karke status/location assert nahin kiya. |
| Sidebar open/close ke saath Studio toolbar | PARTIAL | Mobile drawer/layout capture hua; open drawer ke saath Export PDF tap karke output arrival prove nahin hua. |
| Compress default preset ka full label | PARTIAL | Responsive page scan hua; exact full combobox value aur selection behavior ka repeat assertion nahin hua. |
| AI upload card, exact prompt, uploaded chip | PARTIAL | Empty/loaded geometry aur saved-work controls dekhe; provider-backed chat ke saath upload-card-hide, exact “upload pdf to chat” error aur chip ke name/size/pages sequence nahin chala. |
| Studio page 1, thumbnails, wheel/jump sync | PARTIAL | 69-page notes.pdf loaded state aur page canvas/screenshots verify hue; wheel synchronization, all counter/spinbutton jumps aur 69/middle-page instant paint do baar nahin hue. |
| Catalog ke 38/41 output files | PARTIAL | 41 operation pages ka layout check hua, lekin is final run mein downloaded outputs ko viewer mein nahin khola. |
| AI factual honesty, 6 injection prompts | NOT TESTED | Local provider absent. Koi model answer ya secret-value test nahin chalaya. |
| Paris/Germany false-premise response | NOT TESTED | Provider absent; historical evidence current final build ka re-test nahin hai. |
| Test AI Connection “AI Connected” | NOT TESTED | Final local state configuration_missing tha, jo environment ke mutabik expected hai. |
| Identity/pricing INR/cloud modal | PARTIAL | Kuch plan/quota copy code/tests se cover hui; browser mein poora pricing/identity/cloud modal interaction matrix nahin hua. |
| Extract single-page actual download | NOT TESTED | Is final run mein UI se download aur PDF viewer content assertion nahin hua. |
| Quota/AI status/OCR guard/500 MiB | PARTIAL | Full backend suite pass hua aur 500 MiB boundary test suite mein included hai. Free-tier cap par UI 402 flow, configured AI key aur blank-image OCR output final browser mein nahin test hue. |

## Section 5–6 — P0 aur P1 bug tracker

| Item | Status | Final round ka evidence |
|---|---|---|
| P0-1 — Executive Brief + AI Summarize, 69-page output, first-attempt timing | NOT TESTED | Local provider nahin. No inference; capabilities endpoint Brief unavailable batata hai. Backend provider failure ka asal cause nahin mila. |
| P0-2 — Translate Spanish 2x, second language, output viewer | NOT TESTED | Local provider nahin; koi translated output nahin. Failure path ka Spanish/second-language browser result nahin. |
| P0-3 — page 69 delete, reload/reload; reorder/duplicate retention; delete speed; Undo wording | PARTIAL | Purana unqualified retention banner hata diya; Clear controls Privacy Settings mein. Delete count, mutation save, reload restore, reorder/duplicate restore aur undo wording ko browser mein test nahin kiya. |
| P0-4 — Cloud Import filename/size/pages/open/toast/retry/duplicate/dropzone behavior | PARTIAL | API probe 2 consecutive runs mein public small PDF ko same filename metadata, 554,620 bytes aur 1 page ke saath open karta hai; restricted aur bad link reason ke saath reject. Original 69-page file/virus-scan case, visible UI success toast, retry duplicate prevention aur unrelated dropzone se modal trigger test nahin hue. |
| P1-5 — har tool par zero-upload claim | PARTIAL | 41 page scan mein 4 supported local tools available aur remaining server-only tools local-mode refusal/message dikhate hain. Do scan runs mein issue list clean thi. Har tool ka toast/actual processing route alag-alag run nahin hua. |
| P1-6 — SPA stale workflow/title race | PARTIAL | 41 route/page text scan do baar clean. 10+ rapid click navigation aur reverse-response race simulation final build par nahin chalayi. |
| P1-7 — sticky nav/H1 overlap | PARTIAL | Target widths par horizontal overflow nahin. Har route ke top/scrolled H1 coverage aur nav overlay coordinates scan nahin hue. |
| P1-8 — false author/date/page count premise | NOT TESTED | Provider absent; page count, author, date, extra capital aur no-document cases ke answers unavailable. |
| P1-9 — /developers, Swagger/ReDoc links | NOT TESTED | Final live-equivalent click/path audit nahin hua. |
| P1-10 — actual incremental streaming | NOT TESTED | Provider absent; first-token time/growing text measure nahin hua. |
| P1-11 — citations consistency, brief citations, 3 repeated summaries | NOT TESTED | Provider absent; text/chip counts aur 429 response nahin mile. |
| P1-12 — Metadata first-attempt 502/document date | NOT TESTED | Provider-backed extraction nahin hui; first attempt/date value/System health inspect nahin kiye. |
| P1-13 — Studio jump to page 69/1/middle at 0s/1s/5s | PARTIAL | Same-canvas concurrent render queue fix hua; 69-page loaded layout/page 1 screenshot hai. Jump-target render timing, all three target pages aur second consecutive jump sequence absent hain. |
| P1-14 — Annotate vs Redact same keyword | NOT TESTED | Same 10-page fixture + same keyword par dono output nahin chalaye. |
| P1-15 — Summary/Translate workflow controls match copy | PARTIAL | AI Translate/Summarize pages 41-tool layout scan mein hain; controls aur workflow steps ke semantic match ko har state mein interact karke verify nahin kiya. |

## Section 7 — copy, naming aur premium polish

| Item | Status | Evidence / gap |
|---|---|---|
| 7A — third-party brand / internal library names | PARTIAL | Historical audit mein known copy fixes the; current round mein har shipped/rendered string ko names list ke khilaaf full sweep nahin kiya. |
| 7B — spelling/grammar ke teen specific strings | PARTIAL | Known strings par edits repository mein hain; current full rendered-site/email/static-page proof nahin. |
| 7C — har tool how-to duplicate step | FIXED | 41-page scan do consecutive runs mein duplicate how-to-step count zero; full pytest suite bhi do baar pass. |
| 7D — route/tool/plan/category/quota naming consistency | PARTIAL | Exam Photo & Signature Resizer name aur quota-plan copy align hui. All categories, aliases, every plan label/price suffix aur all SEO headings ka exhaustive two-pass audit abhi nahin. |
| 7E — run buttons, layout, result/progress, honest product copy | PARTIAL | 41 tool pages ke tested widths mein run button wrapping/overflow 0, dono scan runs mein. Progress lag, dropdown truncation, footer/privacy/native-app claims, Redact placeholder, Markdown timeout, HTML-to-PDF finished label, password retention aur output correctness unresolved/unverified hain. |

## Section 8 — directory aur mobile acceptance

### 8A. Duplicate directory tab — FIXED

Duplicate AI-tools directory view/tab remove hai; Tool Desk dedicated directory ke roop mein retained hai. All Tools/home shortcut bhi usi directory ko kholta hai. AI Intelligence alag chat/extraction workspace hai, duplicate directory nahin. Final scan mein Tool Desk ke 41 tools aur 6 sections do baar mile. Retained directory entry point: Tool Desk.

### 8B. Mobile acceptance matrix

| ID | Status | Kya verify hua / missing |
|---|---|---|
| M-1 — sidebar drawer aur Export | PARTIAL | Layout/drawer state capture hui; sidebar open rakhkar Export tap aur downloaded PDF open nahin ki. |
| M-2 — 360/375 toolbar clipping/duplicate labels | PARTIAL | Responsive measurements mein document width viewport ke barabar; page action slot mein 4 controls; pages scan mein wrapping/clipping issues nahin. Har Studio button par single-label aur tap assertion repeat nahin hui. |
| M-3 — phone scroll model, only header sticky | PARTIAL | Narrow viewport par overflow/clipping nahin; all editor controls scroll ke saath move karte hain ya nahin, har panel/route par separately test nahin hua. |
| M-4 — 375px Studio screenshot scenario | PARTIAL | Drawer/actions/canvas phone layout evidence hai; full PAGES (4), selected page, all actions, canvas and export interaction chain nahin. |
| M-5 — thumbnails/canvas at phone/333px | PARTIAL | Actual 69-page notes.pdf loaded; page canvas render evidence. 333px width aur page 69/middle thumbnail visible raster content check nahin. |
| M-6 — AI upload/chat mobile sequence | PARTIAL | Empty/loaded geometry stable; provider chat replies and no-document error text sequence unavailable. |
| M-7 — CSP, eval aur form labels | PARTIAL | 49 responsive states aur 41 tool-page scans mein browser page/console errors zero; visible tool controls unlabelled zero. CSP blocked-resource ka origin/eval call network proof aur poore app ke saare fields ka audit nahin. |
| M-8 — every page phone/laptop | PARTIAL | 41 tool routes 360/375/768/1104/1366/1920 par do scan runs; selected Merge/Compress/Translate pages 375/768/1104/1366/1920 light/dark. 1280px missing; har route × theme × zoom × state, settings/auth/legal pages aur physical devices nahin. |

## Section 9 — code-level risks

| Risk | Status | Detail |
|---|---|---|
| Brief timeout/retry budget + Page Numbers timeout | NOT TESTED | Provider nahin; Page Numbers stall test nahin. |
| Streaming mechanics | NOT TESTED | Provider nahin. |
| Author/date content guard | NOT TESTED | Provider nahin. |
| Translate partial-mode warning/text | NOT TESTED | Translate output/provider nahin. |
| Free-tier 402 quota UI | NOT TESTED | Cap hit karke browser UX test nahin. |
| Large Drive/virus-scan file | PARTIAL | Public small share, direct-download, restricted aur invalid link tested; 69-page/large virus-scan case missing. |
| Playwright dependency/setup docs | PARTIAL | requirements-dev.txt mein Playwright dependency aur README mein Chromium install command maujood; installed Playwright 1.59.0 tha. Clean checkout se install/replay test nahin. |
| Studio render race / jump placeholder | PARTIAL | Per-page render queue add hua, page 1 canvas capture; jump 69/middle 0s/1s/5s timing nahin. |
| Extract multi-page auto-download | NOT TESTED | 69 individual PDFs/ZIP count aur browser downloads nahin dekhe. |
| AI status endpoints configured + unconfigured | PARTIAL | Unconfigured capabilities/connection endpoints 2 baar sahi; configured provider response nahin. |
| OCR blank-image zero-text guard | NOT TESTED | Blank scanned PDF ke OCR output nahin chalaye. |
| Cloud errors never swallowed | PARTIAL | Public/restricted/invalid API responses repeat; UI modal/dropzone/retry failure matrix nahin. |

## Section 10 — pehle uncovered test cases

| Test case | Status | Reason/result |
|---|---|---|
| Guest mode full tool workflow | NOT TESTED | Is round mein guest upload-to-download sequence nahin. |
| Correct-password Unlock | NOT TESTED | Throwaway protected PDF banakar open/verify nahin. |
| Payment sandbox | NOT TESTED | Payment flow intentionally nahin chala. |
| Settings save/reload | PARTIAL | Privacy Settings mein Clear saved work controls verify hue; baaki settings mutations save/reload nahin. |
| 41 tools ke output contents | PARTIAL | Layout/route scan hua; 41 outputs viewer mein open nahin hue. |
| 69-page Split ZIP mein 69 one-page files | NOT TESTED | ZIP entries/content count nahin. |
| OCR output text layer | NOT TESTED | Output text extract nahin kiya. |
| Filled PDF form values | NOT TESTED | Fields fill karke exported values inspect nahin kiye. |
| Mask Aadhaar synthetic ID output | NOT TESTED | Synthetic fixture/output verify nahin. |
| Phone, 1280px, 1366px | PARTIAL | Phone aur 1366 covered; 1280 missing, physical phone nahin. |
| Safari / Firefox | NOT TESTED | Sirf Chromium 147.0.7727.15. |
| Physical devices | NOT TESTED | Device lab/real phone test nahin. |
| OTP claims | NOT TESTED | Is v7 pass mein OTP code review nahin. |
| Non-proxied TLS | NOT TESTED | Localhost-only. |
| Docker image build + smoke | NOT TESTED | Build/run nahin. |
| Free-tier 402 UX | NOT TESTED | Free quota exhaust nahin ki. |
| Second Translate language | NOT TESTED | Provider absent. |
| Owner ke 5 screenshots, pixel-matched redesign | PARTIAL | Related empty/loaded layouts reproduce/measure hue, par new reference redesign poori nahin hui; generated brief and provider states missing. |

## Section 11 — final protocol checklist

| Protocol | Status | Final result |
|---|---|---|
| 1. Final full suite | FIXED | Do unchanged-source runs; har baar 282 pass, 0 fail, 1 deprecation warning. |
| 2. 41 tools ke output content ko viewer mein kholna | PARTIAL | Layout sweep pass hua; har operation ka output inspect nahin. |
| 3. AI: Brief/Summary/Translate/citations/facts/guards/greetings/streaming | NOT TESTED | Provider configured nahin; probe ne 0 inference calls ki. |
| 4. Studio delete/reorder/duplicate reload, Extract, page-jump timing | PARTIAL | Mobile geometry, loaded page 1 aur render queue covered; reload mutation, Extract downloads, jump timings missing. |
| 5. Cloud Import full matrix + original large file | PARTIAL | Public share/direct path, restricted share, invalid ID repeat; provided 69-page document/UI toast/no-duplicate test missing. |
| 6. Routes, SPA navigation, aliases, developers links | PARTIAL | 41 routes scan hue; exact redirects, 10-page rapid SPA race aur API-doc links not run. |
| 7. Mobile/redesign matrix | PARTIAL | Two repeat responsive sweeps and two repeat 41-tool sweeps; requested 3E redesign complete nahin, 1280/zoom/device gaps remain. |
| 8. Console/form fields | PARTIAL | Tested browser states mein 0 page/console errors; every form-field/CSP cause exhaustively verified nahin. |
| 9. Har fix ka repeat verification | PARTIAL | Layout, 41-tool and Cloud probes do runs mein consistent; AI-dependent items unavailable; mutation/export/redirect/alias interactions ka paired second run nahin. |
| 10. Regression gate | PARTIAL | Full suite repeated; Section 4 ke manual/live-equivalent regression actions sab re-run nahin. |

## Deployment se pehle baaki gates

1. Provider ko owner-managed local/staging environment mein configure karke Executive Brief/Summary, Spanish + second-language Translate, citation counts, greetings, false claims, six injection prompts, metadata/date behavior aur streaming ko do consecutive runs test karo.
2. Actual 69-page notes.pdf par delete page 69 → reload → reload; phir reorder aur duplicate reload; count/timing/Undo wording capture karo. Agar retention supported nahin, UI mein exactly kya persist hota hai woh batao.
3. Owner ke 69-page file ko Cloud Import se UI mein import karo; filename/size/pages, document open, success toast, retry-no-duplicate, permission/bad-link handling aur unrelated dropzone test karo.
4. Screenshot 5 reference structure ko actual Studio/AI/tool UI mein complete karo; 375/768/1104/1280/1366/1920, light/dark, requested zoom aur states par paired screenshots.
5. 41 tools ke outputs kholkar content verify karo, including ZIP count, OCR text layer, form values, grayscale/rotation/password/masking.
6. Guest, Free quota 402, correct-password Unlock, settings reload, Safari/Firefox, physical phone, Docker aur non-proxied TLS checks complete karo.
7. UI mein “AI provider not configured” clear state rakho jab tak provider configured na ho. Broken/missing AI ko available ya connected dikhana sahi nahin hoga.

## Audit artifacts

Core outputs:

- FINAL-REPORT.md — yeh report.
- Audit scripts: cloud_import_probe.py, layout_probe.py, phase0_smoke.py, provider_settings_probe.py, responsive_probe.py, tool_pages_responsive_scan.py.
- responsive-final.json — 49-state responsive matrix; final repeated run.
- tool-pages-responsive-scan.json — 41 tool pages, six sections, 30 screenshots, issue summary.
- cloud-import-final.json — final repeated Cloud Import API response matrix; is report mein URLs/IDs include nahin hain.
- provider-settings-final.json — provider unavailable state, clear-work controls, browser errors and inference count.
- pytest-final.txt and pytest-repeat.txt — consecutive full-suite records.
- layout-before-fix.json, phase0-smoke.json, phase0-before-375.png, phase0-before-1104.png — baseline artifacts; phase0 port/file mismatch caveat upar diya hai.
- phase0-server.log and phase0-server-error.log — baseline server logs.
- layout-v7-ai-empty-1104-dark.png, layout-v7-ai-empty-1104-light.png, layout-v7-ai-empty-375-dark.png, layout-v7-ai-empty-375-light.png.
- layout-v7-ai-loaded-1104-dark.png, layout-v7-ai-loaded-1104-light.png, layout-v7-ai-loaded-375-dark.png, layout-v7-ai-loaded-375-light.png.
- layout-v7-studio-empty-1104-dark.png, layout-v7-studio-empty-1104-light.png, layout-v7-studio-empty-375-dark.png, layout-v7-studio-empty-375-light.png.
- layout-v7-studio-loaded-1104-dark.png, layout-v7-studio-loaded-1104-light.png, layout-v7-studio-loaded-375-dark.png, layout-v7-studio-loaded-375-light.png.
- provider-unavailable-settings-1104.png.
- Tool screenshots: tool-merge-pdf-dark/light-{375,768,1104,1366,1920}.png; tool-compress-pdf-dark/light-{375,768,1104,1366,1920}.png; tool-ai-translate-dark/light-{375,768,1104,1366,1920}.png.

Launch status abhi **HOLD** hai. Is report ka 282-test pass count automated suite ki quality batata hai, deployment acceptance nahin. Sabse bada blocker configured AI ke bina unverified AI workflows, Studio retention proof, 41 tool output inspection aur requested full redesign ka incomplete hona hai.

