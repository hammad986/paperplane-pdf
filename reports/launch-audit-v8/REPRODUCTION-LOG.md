# Paperplane Launch Audit v8 — Phase -1 Reproduction Log

Reproduction date: 2026-11-09. Live target: `https://paperplane.qd.je` (page assets report v7, `app.js?v=3.6.7` and `styles.css?v=3.6.7`). Code baseline: `45f17eea2ee74bef872c839f6327fddc8afba627`, branch `launch-audit-v8`. App source was not modified before this log.

## Phase 0 — Security P0s

ITEM: P0-S1 — Register without OTP
REPRODUCED: yes
OBSERVED: Live `POST /api/auth/register` with only email and password returned HTTP 200 and `status: success`, set a `paperplane_token` cookie, and the same session returned HTTP 200 with `authenticated: true` from `/api/auth/me`. The response user identifier is omitted from this log.
EXPECTED: Registration without a verified OTP creates no session; `/api/auth/me` remains unauthenticated until `/api/auth/verify-signup-otp` succeeds.
ROOT CAUSE: `server.py:2453–2540`, Case 3 preserves a direct-registration branch when neither `otp` nor `require_otp` is supplied; it creates the user and session immediately.
FIX PLAN: Remove direct registration, require pending-user plus hashed OTP flow for all request formats, and issue a session only after successful OTP verification.

ITEM: P0-S2 — Cross-tenant job access / IDOR
REPRODUCED: partial
OBSERVED: Live user A’s new grayscale job completed. User A downloaded it (HTTP 200, 9,514 bytes, 10 pages). User B received 404 for status, alternate status, and download; anonymous status and download also returned 404. No live ownerless legacy job was available to probe. Code inspection shows `get_job` protects user-owned and guest-owned rows but returns a legacy row with neither owner nor guest token without an ownership check.
EXPECTED: User B and anonymous clients receive 404 for user A’s status and bytes; no job record is returned without an owner check; bearer links are not usable by another account or signed-out client.
ROOT CAUSE: `persistence.py:826–849` has an unchecked legacy return at the end of `get_job`. `server.py:5681–5846` contains status, download, and delete routes that must all rely on the same tenant authorization. The ownerless live-row branch could not be exercised because no such live job ID was available.
FIX PLAN: Close the ownerless legacy branch, audit all job routes including metadata and v1, stop exposing guest tokens, and make download authorization owner-scoped and short-lived.

ITEM: P0-S3 — OTP brute-force and lockout gap
REPRODUCED: yes
OBSERVED: A live OTP login challenge was requested for a probe account. Six consecutive wrong codes each returned HTTP 400; the sixth response had no `Retry-After` header and no lockout message.
EXPECTED: The sixth wrong OTP attempt within a minute returns HTTP 429 with `Retry-After`, after a per-account limit and lock period.
ROOT CAUSE: `server.py:2692–2722` limits OTP attempts by IP at 30/minute, while `persistence.py:527–574` only invalidates an OTP after repeated wrong attempts and does not lock the account or return 429.
FIX PLAN: Add per-account verification limits and lockout, invalidate the challenge at the limit, apply exponential resend backoff, return 429 with `Retry-After`, and add per-account throttles to registration, jobs, and AI routes.

## Phase 1 — Silent-fail tools

ITEM: P1-T1 — Annotate silently omits requested notes
REPRODUCED: partial
OBSERVED: On live `/annotate-pdf`, the page exposed only upload and Run controls, without annotation controls. An `annotate` job with empty options returned HTTP 202 then completed; its 9,713-byte, 10-page output contained a blank annotation but no `Test annotation note`. A second job with an explicit sticky-note payload completed at 9,728 bytes and its PDF text contained the requested note.
EXPECTED: A note entered in the tool reaches the worker and appears in the returned PDF; an empty annotation payload fails loudly instead of producing an unrelated blank annotation.
ROOT CAUSE: `server.py:2063–2073` supplies a default empty highlight when annotations are absent. `converters.py:2290–2347` can apply explicit notes, but the Tool Desk has no controls to create and send the requested payload.
FIX PLAN: Wire the annotation controls and payload end-to-end, and reject empty annotation requests.

ITEM: P1-T2 — Tool Desk Page Organizer has no reorder controls
REPRODUCED: yes
OBSERVED: Live `/organize-pdf` provided upload and Run only. An empty-order request completed with pages still in input order. A direct request with page order `[3,1,2]` returned three pages with “Page 3 of 10” first, showing that the backend accepts an explicit order.
EXPECTED: The user can set order `[3,1,2]` in the tool, and the output text follows that order; empty order cannot be reported as a successful reorder.
ROOT CAUSE: The Tool Desk has no page-order editor, so it sends no order. Backend order handling is in `server.py:2036–2057`; Studio drag wiring in `web/assets/page_organizer.js:767–798` listens to mouse drag only.
FIX PLAN: Add Tool Desk order controls or send users to Studio, reject an empty requested order where appropriate, and add pointer/touch drag support plus accessible Earlier/Later controls.

ITEM: P1-T3 — Drawn signature pad is dead
REPRODUCED: yes
OBSERVED: On live `/studio`, a real drag across `#editor-sig-canvas` left the pad blank. Clicking “Place Signature Mark” showed `Please draw your signature before placing.` The typed-signature mode rendered a `Test Signer` preview and closed after placement; its exported PDF was not content-checked in this reproduction.
EXPECTED: Pointer or touch drawing produces visible ink and the exported PDF contains that signature; the typed option continues to work.
ROOT CAUSE: `web/assets/editor.js:395–517` registers mouse/touch listeners and computes coordinates from the canvas bounds without a pointer-capture path; the working Studio draw tool uses a separate canvas.
FIX PLAN: Use pointer events with pointer capture and scale client coordinates by the canvas backing-store dimensions; verify rendered pixels in the exported file on desktop and touch.

ITEM: P1-T4 — Compare diff body leaks temporary hashes
REPRODUCED: yes
OBSERVED: Live Compare produced a real `.txt` file (519 bytes in this run) with a correct diff. The body headers were `--- <32-character hash>_test-text-10page.pdf` and `+++ <32-character hash>_test-text-10page-revised.pdf` rather than the original upload names.
EXPECTED: The diff body uses the original user-facing filenames and contains no temporary hash names or paths.
ROOT CAUSE: `server.py:1924–1925` assigns hashed temporary input names; `server.py:2146–2154` passes those names into the unified diff headers.
FIX PLAN: Preserve sanitized original upload names separately and use only those names in the diff body.

## Phase 2 — AI provider P0s

ITEM: P0-A1 — Executive Brief / Summarize on 69 pages
REPRODUCED: partial
OBSERVED: Live `/api/ai/summarize` returned HTTP 502 for the generated 2-page PDF after 102.3 seconds and for the generated 69-page, 4,980,286-byte PDF after 125.9 seconds; both returned `AI service could not be reached or timed out. Please try again.` In a later UI run, the same 2-page fixture did produce an executive summary. The 69-page failure remains reproduced; the small-file path is provider/state dependent.
EXPECTED: A brief and summary are produced from the full 69-page regression PDF, twice, with page-grounded content.
ROOT CAUSE: `ai_engine.py:980–1002` sends the full document through the provider under a page budget; `server.py:3722–3768` converts timeout/runtime failures to HTTP 502/504. The provider path is not reliable at this size.
FIX PLAN: Inspect provider limits, request sizing, timeouts, and retry behavior; chunk/summarize pages safely; return clear failure classes and prove 69-page output content.

ITEM: P0-A2 — AI Translate fails for small PDFs
REPRODUCED: yes
OBSERVED: Live `/api/ai/translate` returned HTTP 502 for 2 pages (26.9 seconds), 5 pages (30.1 seconds), and a valid 897-byte PDF (1.3 seconds). The response said `Translation could not be completed. Please retry with a shorter PDF or try again later.` and had no `Retry-After` header.
EXPECTED: 2-page and 5-page PDFs produce readable translated output; provider errors identify their actual class rather than blaming file length.
ROOT CAUSE: `server.py:3806–3861` maps runtime failures to a shorter-PDF hint; the provider call is in `ai_engine.py:1502–1617`.
FIX PLAN: Verify provider auth, quota, model, endpoint, and gateway timeout; add one bounded retry with backoff and expose the upstream failure class without the misleading length hint.

ITEM: P0-A3 — Cloud Import for the owner’s 69-page Drive document
REPRODUCED: partial
OBSERVED: The supplied public Drive link imported successfully in the live UI and showed `PAGES (1)`. A metadata-only API check resolved it as `SreeVarun_V.pdf`, 554,620 bytes, one page. The import worked, but this linked file does not match the audit’s described 69-page document, so the required 69-page import was not established.
EXPECTED: The owner’s 69-page PDF imports in the UI, with the correct filename, size, and 69-page count shown.
ROOT CAUSE: `server.py:5540–5626` validates and returns the file that Google Drive serves; `web/assets/app.js:3507–3553` counts its pages and displays its name, size, and page count. The observed link resolves to a different one-page PDF.
FIX PLAN: Keep the PDF-only and SSRF checks, show import metadata reliably, and retest once the link points to the exact 69-page regression document.

ITEM: P0-A4 — Studio Export “Failed to fetch” regression
REPRODUCED: no
OBSERVED: A 69-page synthetic document was edited by deleting one page. Live Studio displayed `Deleted 1 page(s).`; clicking Export downloaded `edited_notes-69page.pdf`. The saved output opened as a 4,979,414-byte, 68-page PDF with Page 2 first. No `Failed to fetch` error occurred after reloading Studio. Export and zoom controls did measure 0×0 after a mobile-to-desktop resize until reload; that separate behavior is logged as P1-3.4.
EXPECTED: Export downloads the edited document and opens with the edits present; it should remain available after viewport changes.
ROOT CAUSE: This export failure did not reproduce on the live path after a fresh desktop load. The separate zero-size control regression is caused by `web/assets/app.js:803–807` moving controls into the mobile dock without moving them back on desktop resize.
FIX PLAN: Preserve export controls across breakpoints, verify export after resize on pages 4–5, and retry the reported failure if it persists on the owner’s deployment.

## Phase 3 — Studio P1 items

ITEM: P1-3.1 — Studio header and toolbar clip in outer-scrolled state
REPRODUCED: yes
OBSERVED: On live Studio at 1104×542, scrolling the outer page set `main.main-area.scrollTop` to about 216.8. The global `.topbar` stayed at y=0–76, while `.studio-toolbar` moved to y=-140 and the top Studio controls were clipped. The footer moved into the viewport; the PAGES panel also moved with the Studio content rather than remaining pinned.
EXPECTED: Studio’s heading, tool rows, Export control, and PAGES panel stay available and do not sit underneath the sticky navigation when the outer page scrolls.
ROOT CAUSE: The Studio controls are in normal content flow inside the scrolling `main.main-area`; the global `.topbar` is sticky but the Studio header/panel are not.
FIX PLAN: Keep the Studio heading and required controls sticky within the workspace or constrain Studio to its own continuous canvas scroll region without clipping.

ITEM: P1-3.3 — PAGES panel cannot collapse on desktop
REPRODUCED: partial
OBSERVED: Live desktop Studio showed Split, Import, Select All, and Invert controls but no PAGES collapse button. At mobile/tablet widths, a `Pages` dock button exists and toggles the panel.
EXPECTED: The PAGES panel has a clear open/close control on laptop and mobile so the canvas can use the full width.
ROOT CAUSE: `web/index.html:720` defines only `#studio-mobile-pages-btn`; there is no equivalent desktop control around `#studio-thumbnails-bar`.
FIX PLAN: Add a persistent, accessible panel toggle for desktop and keep its expanded state and `aria-expanded` value synchronized with the mobile control.

ITEM: P1-3.4 — Export and zoom vanish after mobile-to-desktop resize
REPRODUCED: yes
OBSERVED: On live Studio at 390×844, Export measured 92×44 pixels. After resizing to 1104×542, Export and zoom measured 0×0 because they remained in the hidden mobile dock. Reloading at desktop restored Export to a visible 121.6×36 pixels.
EXPECTED: Export and zoom remain visible and usable after resizing in either direction without a reload.
ROOT CAUSE: `web/assets/app.js:803–807` reparents controls into mobile slots, while the re-layout does not reliably move them back on desktop; `web/index.html:714–724` places those slots in a dock hidden by desktop CSS.
FIX PLAN: Use one toolbar container with responsive CSS or move controls back on every breakpoint change; run layout synchronization on `resize` and verify export on pages 4–5.

ITEM: P1-3.6 — Clear Studio PDF retention (contested)
REPRODUCED: no
OBSERVED: On desktop and at 390×844, Clear Studio emptied the synthetic document, displayed `Saved PDF and page position cleared from this browser`, and after reload Studio remained empty. The desktop retention sequence also survived reloads as 69→68→67 pages.
EXPECTED: Clear removes all local PDF/page state on desktop and mobile; reload restores no document. Page deletions remain saved across reloads.
ROOT CAUSE: The reported restoration did not reproduce. Current `web/assets/app.js:267–338` removes Studio local work, resets in-memory state, and clears the session marker once no work remains.
FIX PLAN: Keep this behavior and retain desktop/mobile clear plus reload coverage; investigate again if the owner’s mobile reproduction returns.

ITEM: P1-3.7 — “View in Studio” handoff from Rotate, Merge, and Compress (contested)
REPRODUCED: no
OBSERVED: Live handoff opened Rotate’s 10-page output as 10 pages, Merge’s 20-page output as 20 pages, and Compress’s 10-page output as 10 pages. Each showed `Opening processed document in Studio…`.
EXPECTED: Each tool opens its just-processed output in Studio instead of restoring an earlier session document.
ROOT CAUSE: The failure did not reproduce in any of the three requested workflows; the result action is wired in `web/assets/app.js:1031–1038` and `3812` onward.
FIX PLAN: Keep the explicit processed-file handoff and add regression coverage for all three tools.

ITEM: P1-3.8 — Forms “Add Field” footer is unreachable
REPRODUCED: yes
OBSERVED: In the live Studio Forms modal, selecting Add Field left `Save & Fill Form →` visible and `Add Field to Page →` at `display:none` with a 0×0 rectangle.
EXPECTED: The Add Field tab exposes its add action; Fill is visible only on Inspect & Fill; neither action is exposed on Import / Export.
ROOT CAUSE: `web/index.html:3167–3168` hides `#btn-apply-add-field` and leaves the fill button visible. `web/assets/security_forms.js:126–133` changes panes and tab highlighting only.
FIX PLAN: Toggle the footer actions with the active tab and guard `applyFormFill` while Add Field is active.

ITEM: P1-3.9 — Studio footer not hidden until scroll
REPRODUCED: partial
OBSERVED: At 1104×542, the global footer began at y=668 and was below the initial viewport; after outer scrolling it entered the viewport at y≈451. At 1054×615, about 34 pixels of the footer were visible in the initial viewport. The result depends on viewport height.
EXPECTED: The footer remains hidden until the user scrolls down, consistently on mobile and laptop.
ROOT CAUSE: `web/assets/styles.css:9538–9546` renders the Studio footer as ordinary content after the workspace rather than gating it on a scroll state.
FIX PLAN: Match the owner’s hidden-until-scroll behavior across all viewport heights and views, then test at 1104×542 and 390×844.

ITEM: P1-3.10 — AI Docs layout identity and summary clipping
REPRODUCED: partial
OBSERVED: Before upload, the Executive Summarizer card was y=359.4–518.4. After uploading the same 2-page file, its card remained y=359.5–518.4. When generation started, `#summary-display` moved from y≈586.7 to y≈518.0 while the card stayed fixed; after the summary arrived, the 90-pixel output box began at the card’s bottom edge and was clipped by its parent. One generation was observed; three complete repetitions were not run.
EXPECTED: The AI Docs layout stays identical through empty, uploaded, processing, and completed states; summary text and actions remain visible.
ROOT CAUSE: `web/index.html:780–870` nests the summary output inside a fixed/flex card; AI state changes add progress/output content without reserving visible space. Related responsive rules are in `web/assets/styles.css:5212–5213`, `8752–8799`, and `9526` onward.
FIX PLAN: Reserve a stable summary area, keep output/actions inside the card’s scrollable region, and repeat the same before/upload/process/after geometry check three times.

ITEM: P1-3.12 — Studio page deletion is slow on large PDFs
REPRODUCED: yes
OBSERVED: On the generated 4,980,286-byte, 69-page PDF, deleting one page took approximately 28.3 seconds; after reload, deleting another took approximately 28.9 seconds. Both showed `Deleted 1 page(s).`; page counts persisted as 69→68→67 across reloads.
EXPECTED: One-page deletion does not reload and rewrite the whole large document for tens of seconds; progress and undo remain useful during the operation.
ROOT CAUSE: `web/assets/page_organizer.js:1255–1286` waits for the page-mutation result and then reloads the complete PDF into Studio; the full-file worker mutation is in the Studio page-delete API path.
FIX PLAN: Avoid full-document reload work where possible, optimize delete mutation/rendering, and align undo availability with actual mutation time.

## Phase 4 — Layout P1 items

ITEM: P1-4.1 — 820-pixel tablet receives phone layout
REPRODUCED: yes
OBSERVED: At 820×1180, the live sidebar was 290 pixels wide at x=-290, the hamburger was visible, and the mobile workspace bar appeared at the bottom. The layout therefore switches to phone navigation at tablet width.
EXPECTED: Tablet widths 768–900 retain a narrow desktop sidebar and do not show phone menu/bottom navigation.
ROOT CAUSE: `web/assets/styles.css` applies the phone layout in repeated `@media (max-width: 900px)` blocks, including lines 2388, 4057, 4467, 5250, 6714, 7522, and `left:-290px` near 4104.
FIX PLAN: Set a true phone breakpoint and add a deliberate 768–900 tablet layout; verify at 820×1180.

ITEM: P1-4.7 — Sticky pill nav overlaps Tool Desk content
REPRODUCED: yes
OBSERVED: At 1104×542, the sticky `.topbar` occupied y=0–76. After outer scrolling the Tool Desk directory, `main.main-area.scrollTop` was 1,090.4 and the first visible tool card began at y=-6.6 underneath the sticky navigation; its upper content was clipped.
EXPECTED: Headings, tool cards, and form labels clear the sticky navigation while scrolling.
ROOT CAUSE: The sticky top bar overlays the independently scrolling main content without matching scroll padding or sticky offset.
FIX PLAN: Add correct top scroll padding/spacing to every view and verify headings, cards, and input labels at all required widths.

ITEM: P1-4.11 — Shared redesign has not reached every view
REPRODUCED: partial
OBSERVED: Live Studio uses a toolbar plus an optional mobile dock, while Tool Desk and AI Docs retain different page structures and top actions. The desktop view did not expose the described shared Undo/Redo/Save/Export row, icon tool row, and Pages/Properties bottom controls across all views. The task supplies a textual concept but no reference image or precise interaction spec.
EXPECTED: The described shared action row, tool row, canvas, bottom controls, and Pages/Properties panels work across mobile, laptop, and every view.
ROOT CAUSE: `web/index.html` has separate legacy Tool Desk, Studio, AI, and waitlist views; responsive dock styling is conditional and mostly limited to Studio.
FIX PLAN: Build a shared responsive workspace shell and map each view’s controls into it; mark any interpretation that cannot be compared to a missing reference asset as partial.

## Phase 5 — Auth / UX / legal P1 items

ITEM: P1-5.1 — Resending signup OTP silently invalidates the old code
REPRODUCED: partial
OBSERVED: Code inspection shows `create_email_otp` deletes the existing OTP for the same email/purpose before inserting the new one. The verification response is the generic `Invalid or expired verification code.`; the live old-code/new-code sequence was not run because the OTP mailbox was not available.
EXPECTED: The screen explains that the latest email replaces prior codes and enforces a 60-second resend cooldown.
ROOT CAUSE: `persistence.py:491–525` replaces the prior OTP; the signup UI error path in `web/assets/app.js` does not distinguish a superseded code from other invalid/expired codes.
FIX PLAN: Show the latest-email guidance on invalid code and disable resend for 60 seconds after a send.

ITEM: P1-5.2 — OTP email deliverability and sender identity
REPRODUCED: partial
OBSERVED: Source uses environment-configured `SMTP_USER` / `SMTP_FROM_EMAIL`; the default sender is `noreply@paperplane-pdf.com` and fallback sender logic uses a shared onboarding address. No live mailbox or delivery receipt was available to verify whether the current production sender reaches inbox or junk.
EXPECTED: OTP mail comes from a verified transactional domain with aligned SPF/DKIM/DMARC; delivery failures are explicit; until then the UI tells users to check spam.
ROOT CAUSE: `email_service.py:19–31` takes sender identity from production environment configuration, and `email_service.py:88–110` provides SMTP/Resend fallback behavior. Production DNS/provider state cannot be changed from this repository.
FIX PLAN: Use a verified sending domain/provider, fail loudly if delivery did not occur, and add the spam-folder hint. Do not put mail credentials or OTP values in the audit artifacts.

ITEM: P1-5.3 — Terms promise cancellation that Billing does not expose
REPRODUCED: yes
OBSERVED: Live Settings → Plans & Billing shows the current plan summary and an Upgrade/View Pricing Tiers button; there is no cancellation control. `web/index.html:983` promises users may cancel through Settings billing controls without fees.
EXPECTED: Billing provides a real cancellation route, or Terms accurately describe the actual cancellation process.
ROOT CAUSE: The Terms promise is in `web/index.html:983`; the Billing pane in `web/index.html:1678–1698` only offers upgrade. A Terms update is an owner decision and no verified cancellation backend was found.
FIX PLAN: Do not silently change legal terms. Add a working cancellation path only if the payment provider supports it; otherwise report the mismatch and obtain the owner’s approved replacement wording before editing the promise.

