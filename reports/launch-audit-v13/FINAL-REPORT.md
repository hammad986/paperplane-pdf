# Paperplane v13 launch audit

## Verdict

**HOLD.** Local fixes and regression coverage address the P0 items, but the required evidence is incomplete for provider-backed AI, the exact Drive file, production redeploy persistence, owner credential rotation, and Cashfree sandbox checkout. Every audit item has one of the requested statuses in the register below.

## Scope and verification

- Branch launch-audit-v13, audited HEAD c11042eb6ae8d10b0b7a641248a181a688b4133b. All changes are uncommitted.
- No commit, push, deployment, real payment, production account access, or real credential values were used.
- Phase -1 reproduction was recorded before product edits in REPRODUCTION-LOG.md.
- Baseline suite was 388 passed, 1 warning. Final suite ran twice consecutively.
- Final run 1: 428 passed, 1 warning in 121.85s (0:02:01). See test-suite-run-1.log.
- Final run 2: 428 passed, 1 warning in 134.56s (0:02:14). See test-suite-run-2.log.
- Each final run reports one Starlette/httpx deprecation warning. The prompt's expected count of two was not reproduced.
- Compose configuration validation passed. Docker engine access failed because Docker Desktop's Linux engine pipe was unavailable.
- git -c core.whitespace=cr-at-eol diff --check passed.

## Tool output checks

- The 44-operation catalog ran twice on synthetic/repository fixtures. Each run completed 40 operations. Three provider-dependent operations were unavailable. HTML-to-PDF correctly blocked the intentionally private test URL.
- Outputs were reopened and checked for formats, page counts, text/order, rotations, sizes, form values, encryption, dimensions, and image geometry where supported.
- Tesseract and a live AI provider were unavailable. See tool-content-audit.json.

## Browser checks

- Two isolated Chromium rounds passed before expanded checks were added. They recorded local and server Merge, ZIP Split, photo tools, 69-page reorder/export/delete persistence, sign-out, feedback refresh, responsive widths, and no page errors. See browser-acceptance.json.
- An additional expanded Chromium attempt stopped at the A4-to-Letter Studio resize check: the synthetic browser session had already reached the Free Tier limit (10/10 operations), and the endpoint returned HTTP 402 `TIER_LIMIT_REACHED`. No result is claimed for the remaining expanded cases. See `expanded-browser-attempt.md`.

## Changes made

- Fail-closed admin startup, secret scanning workflow, two owner identities, hashed single-use challenges and sessions, admin session revocation, per-user plan/usage actions, audit logging, and feedback refresh.
- Payment readiness and environment reporting, signed webhook validation, order amount/currency/owner matching, replay protection, and revenue separation by environment.
- Trusted proxy handling and atomic quota reservation/refunds. A concurrent quota overrun was reproduced and fixed.
- Drive resource-key/confirmation handling, bounded AI translation/summary changes, Smart Metadata invalid-upload rejection, and image Aadhaar masking.
- Local PDF/photo processing, server-mode selection, route/settings states, account-switch cleanup, and responsive refinements.
- Named-volume preflight and deployment guidance. Live Docker volume identity was not tested.

## Item register

| ID | Source title | Status | Evidence or remaining work |
| ---: | --- | --- | --- |
| 1 | AI Translate fails with HTTP 500 | **PARTIAL** | Slow stubbed provider reproduced the prior timeout. Batch timeout/retry and Hindi overlay now pass stub tests. Live provider result unavailable. |
| 2 | Executive Brief / AI Summarize fail on the 69-page document | **PARTIAL** | Added bounded chunk and shared-deadline handling. Synthetic 69-page path is tested. Live provider unavailable. |
| 3 | Studio page deletions do not survive reload (Studio) | **PARTIAL** | Two prior Chromium rounds verified 69-page delete to 68, reload, and export. |
| 4 | Cloud Import from the owner's Drive link is unreliable | **PARTIAL** | Resource key and bounded trusted Drive confirmation handling pass unit tests. Exact supplied file remains partial per owner direction. |
| 5 | Summary citations are nondeterministic | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 6 | False author claim is never corrected | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 7 | Workflow/FAQ copy shows the previous tool's text on first SPA landing (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 8 | Remove Pages times out on first | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 9 | Smart Metadata: 502 on first attempt, | **PARTIAL** | Malformed PDF returned HTTP 200 before changes. Now returns validation error and does not charge usage. First-run provider timeout not tested. |
| 10 | Studio Extract produces no automatic | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 11 | Canvas is blank at 0s on a page jump | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 12 | Chat answers render raw markdown | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 13 | Studio page delete is slow (~15-20s) | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 14 | Annotate and Redact contradict each | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 15 | Sticky top-nav pill overlaps tool-page | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 16 | /developers still has no | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 17 | Tool Desk is a real view (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 18 | /fill-form and /ai-translate route aliases work (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 19 | Studio sidebar toggle no longer covers the toolbar (Studio) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 20 | Run-button labels no longer wrap mid-word (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 21 | Studio page-1 canvas renders within ~5s (Studio) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 22 | "Upload PDF to chat" wording is in the AI empty state (AI) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 23 | Free-tier quota bypass closed (code-confirmed) (Code) | **FIXED** | Reproduced concurrent requests exceeding guest quota. Atomic reservations and stream-failure refunds now pass targeted tests. |
| 24 | AI status endpoints no longer lie (code-confirmed) (Code) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 25 | Tool catalog: 38 of 41 tools verified end-to-end (8 Nov) (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 26 | Mask Aadhaar: masking inside the output never checked (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 27 | Mobile layout on real phone widths (Mobile, P1) - The v5 retest ran at desktop widths. Codex claims | **NOT TESTED** | Targeted final verification was not completed. |
| 28 | Contents inside downloaded outputs (Tools, P2) - Not opened in any round: merged page count, split | **NOT TESTED** | Targeted final verification was not completed. |
| 29 | Guest mode, correct-password Unlock, payments (Site, P2) - All live rounds ran signed-in on Pro. | **NOT TESTED** | The prompt records this item as untested, and no additional proof was obtained. |
| 30 | Mobile Studio is unusable (owner | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 31 | "Bluesminds" provider name leaks on /developers (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 32 | Cloud Import modal pops up | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 33 | iLovePDF named in shipped HTML/JS comments (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 34 | AI Docs page layout shifts after | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 35 | General greetings fail when a document is loaded (AI) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 36 | Copy errors: "Characters glyphs", "Uncap", template text on every tool page (Site, P2) - Only 2 | **NOT TESTED** | Targeted final verification was not completed. |
| 37 | "Browser zero-upload processing: Supported" on all 41 tool pages (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 38 | Combobox truncation, progress-bar lag, | **NOT TESTED** | No discriminating final evidence was recorded. |
| 39 | DECISION: remove one of the duplicated AI tools / Tool Desk tabs (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 40 | Plan names, price formats and tool names | **NOT TESTED** | No discriminating final evidence was recorded. |
| 41 | PDF to Markdown flaky timeout (PARTIAL) | **NOT TESTED** | No discriminating final evidence was recorded. |
| 42 | DECISION: redesign all views after the | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 43 | Studio delete undo window is effectively | **NOT TESTED** | No discriminating final evidence was recorded. |
| 44 | AI Intelligence: remove 'Your AI PDF and full chat history save in this browser...' banner (AI) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 45 | Studio layout: remove save banner, | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 46 | Sidebar quota text is contradictory: 'Unlimited · 500 MB · 100 files' (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 47 | REGRESSION v7: Studio reorder no | **PARTIAL** | Prior browser rounds verified drag reorder and Earlier. Later and final expanded Studio checks remain unverified. |
| 48 | REGRESSION v7: Studio duplicate fails with 'Network error: Failed to fetch' (Studio) | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 49 | REGRESSION v7: Studio Export fails with 'Export error: Failed to fetch' | **PARTIAL** | Two prior browser rounds verified 69-page export and output order. Final expanded quota-dialog run not completed. |
| 50 | /developers copy defects: 'Copy Copy | **NOT TESTED** | No discriminating final evidence was recorded. |
| 51 | Settings: 'Local or temporary processing' | **NOT TESTED** | No discriminating final evidence was recorded. |
| 52 | AI Docs empty state: 'page citations.' | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 53 | Studio header breaks on scroll: | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 54 | /tools/*, /pricing and /plans return styled | **NOT TESTED** | No discriminating final evidence was recorded. |
| 55 | Sidebar 'Operations Today' box cramped at | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 56 | Per-platform 'Join Waitlist' buttons only | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 57 | More Tools dropdown left half hidden in owner's screenshot state (not reproduced at rest) (Studio) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 58 | DECISION: PAGES panel needs a collapse/expand toggle (laptop + mobile) (Studio) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 59 | Tablet (820px) gets the phone layout - sidebar hidden, drawer only (Mobile) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 60 | Signup: new code silently cancels the | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 61 | OTP emails land in junk, sent from a | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 62 | Studio Export + zoom controls vanish | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 63 | CRITICAL: Register without OTP - email+password only creates an account + instant session (Code) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 64 | Forms 'Add Field' is unreachable - its | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 65 | CRITICAL: No OTP rate limiting - 6-digit OTP brute-forceable (6-7 wrong codes, no 429) (Code) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 66 | /developers tables run past the right edge on phones and tablets (Mobile) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 67 | CRITICAL: IDOR - any logged-in user can download any other user's processed files (Code) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 68 | Draw Signature pad dead (touch ignored); drawn /sign-pdf output has no signature - Type works | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 69 | CONTESTED: 'Clear Studio PDF' | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 70 | Page Organizer: tool page offers NO | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 71 | Annotate tool is a silent no-op - reports success, output has no annotation (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 72 | Mobile: 'View in Studio' from a scrolled | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 73 | Export stalls after resize (pages 4-5 hang | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 74 | Terms §4 promises cancellation via Settings billing, but Billing has Upgrade only - no cancel (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 75 | Compare: .txt extension fixed, but temp | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 76 | Empty fields show 'Operation Failed' instead of a plain hint (Remove/Watermark/Redact/Mask) (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 77 | Studio GEOMETRY/ORDER & OCR | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 78 | CONTESTED: 'Open in Studio' handoff - final sweep says it ignores the new file; Muse's check says it | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 79 | DECISION: No History/Dashboard page - past jobs are not listed anywhere (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 80 | Mobile Settings panes overflow slightly; tab | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 81 | Duplicate security headers (X-Frame-Options, X-Content-Type-Options, Referrer-Policy sent twice) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 82 | Tool 'details' sections lazy-load after first | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 83 | 'Test AI Connection' debug link is visible to all users on the AI Docs page (AI) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 84 | Escape closes ALL stacked modals at | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 85 | Result-card buttons clipped on mobile; | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 86 | AI Docs polish: raw '[Page N]' markers, '1-' | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 87 | Phone bottom bar labels are 9px - hard to | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 88 | Merge output named after first file; Compare card does not say the result is a .txt diff (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 89 | API inconsistency: register is form-encoded, OTP endpoints take JSON; guest_token in URLs (Code) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 90 | UNRETESTED: login code in a response header; server 502s under 2-4 concurrent jobs (Code, P1) - | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 91 | Deep-linking to /settings returns the 404 page (Settings is an overlay with no route) (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 92 | Studio 'New Page' discards without | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 93 | Redeploy wipes accounts/data - production DB not persistent across deploys | **PARTIAL** | Two-process persistence test passes and Compose retains named volume. Container recreation was unavailable without Docker. |
| 94 | Developer API rejects its own freshly | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 95 | Smart Metadata export not confirmed - no export button found (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 96 | Fill PDF Form on a real fillable form not confirmed (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 97 | Password-reset emails never arrive | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 98 | Pro checkout is Cashfree sandbox in production - anyone can get Pro free | **PARTIAL** | Production with TEST gateway now fails closed. Mock signed sandbox tiers, mismatched orders, and webhook replay are tested. No sandbox account used. |
| 99 | AI PDF Chat ignores the attached document unless the question says 'according to this document' (AI) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 100 | Mobile drawer uses 100vh not 100dvh - profile card + settings gear unreachable (Mobile) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 101 | Admin secret code is the hardcoded public repo default (server.py:184) - fail closed | **PARTIAL** | Unset admin key/code fail closed; Gitleaks workflow added. Owner rotation and remote history cleanup are not done. |
| 102 | Feedback widget submission accepted but never reaches the admin list - write/read | **PARTIAL** | Database persistence test and previous browser refresh test pass. No live service feedback write/read. |
| 103 | Admin session ends after ~75 min | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 104 | Cloud Import dialog sometimes auto- | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 105 | Smart Metadata document_date is '3.3.1' | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 106 | Intermittent first-attempt 502s and 75% | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 107 | Revenue dashboard labels sandbox test | **PARTIAL** | Revenue groups production, test, simulation, and unknown sources and excludes nonproduction from production totals. Mock data only. |
| 108 | /api-docs publicly accessible in production (Code) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 109 | 24-hour deletion claim does not cover | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 110 | SEO heading off-by-one on 27 tool | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 111 | Word to PDF fails when files from a | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 112 | HTML-to-PDF SSRF protection - verify | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 113 | Repair PDF rejects genuinely damaged files (Tools) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 114 | Studio restores a previous account's | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 115 | Feedback pill overlaps mobile content and | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 116 | Sanitize Document Now gives no feedback (Studio) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 117 | Digital Signatures Verify shows false | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 118 | Admin lockout bypassable via spoofed | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 119 | Studio Organize button does nothing on | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 120 | /admin HEAD returns 405 (GET works) | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 121 | Sign PDF tool page has no draw pad - | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 122 | Browser tabs freeze on heavy pages | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 123 | Local tool downloads are toast-only - no | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 124 | Copy/UX nits grouped (v10) | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 125 | Advanced Studio toolbar/tools need to be | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 126 | Security Audit/Sanitize modal not reachable | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 127 | Tool cards are JS buttons, not links; wrong- | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 128 | Feedback button: dismissible; shown to | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 129 | Sanitize dialog shows two identical | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 130 | /settings renders the Tool Desk directory, | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 131 | 1104px clipping: /download heading and | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 132 | /dashboard, /history, /faq, /feedback return 404 | **PARTIAL** | Route aliases and intended page responses pass tests and prior Chromium route checks. |
| 133 | /settings URL shows Tool Desk content after the modal closes | **PARTIAL** | Settings page shell and in-place settings content pass tests and prior Chromium navigation. |
| 134 | Waitlist form on /download - contested, now confirmed present (Site) | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 135 | Wrong per-tool limits text names | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 136 | Free-operations contradiction - 250 vs | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 137 | Theme inconsistency - dark/light flip, | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 138 | AI Intelligence has no route (Site) | **PARTIAL** | Listed as previously verified-fixed. Two item-specific regression rounds were required and not completed. |
| 139 | Sidebar AVAILABLE TOOLS empty on | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 140 | Sidebar profile card missing on several | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 141 | Pricing modal layout - two-column feature | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 142 | Grammar - '1 tools' | **FIXED** | Prior two browser rounds typed a one-result search and observed singular grammar. |
| 143 | Developers banner missing a space | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 144 | 404 page is bare - no sidebar or top | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 145 | Large empty white bar under the dropzone | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 146 | Translate CTA pale peach, low contrast | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 147 | Floating Feedback button mounts | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 148 | 'Server Mode' toggle state varies by | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 149 | Photo Merge cannot merge (single-file | **PARTIAL** | Prior browser rounds verified multi-photo merge and grid dimensions. |
| 150 | Server engine falsely rejects a common | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 151 | Ads shown to a paid Pro account + | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 152 | Photo tools are server-only by design | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 153 | Tool-count labels are wrong (41 vs 44 vs | **FIXED** | Prior browser rounds observed a 44-tool catalog and matching badge. |
| 154 | Stale prices leak in the live UI (₹750, | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 155 | Local-processing controls contradict each | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 156 | Split mode label lies (says ZIP, outputs | **FIXED** | ZIP opened with three individual one-page PDFs in each previous browser round. |
| 157 | AI Chat welcome message renders twice | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 158 | 'Download Another File' is circular | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 159 | Home shows 'Loading tools…' for several | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 160 | Settings modal content differs by entry | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 161 | Compress PDF 502 on 5.2 MB / 69-page | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 162 | Photo Resize rejects 50% scale | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 163 | Merge claims 'never upload' but lists a | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 164 | Studio 'Unsaved' signature annotation is | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 165 | Photo Resize preset/dimensions | **PARTIAL** | Prior browser rounds verified output at 350 by 450 pixels. |
| 166 | Page Organizer is server-only despite | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 167 | Display-font word-spacing: headings | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 168 | First-paint / load-state root cause: | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 170 | 'Free Guest Tool' badge on every tool page | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 171 | No footer on any page except Home | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 172 | Step cards headings-only, no body text | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 173 | Steps promise controls that do not exist | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 174 | Studio: phantom 'Page 1 is loading…' with | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 175 | Photo tools have no lower sections; Mask | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 176 | Stale toast persists across navigation; | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 177 | Pricing modal taller than viewport; Pay | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 178 | Photo & Exam suite click lands main pane | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 180 | /developers: heading twice; version | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 181 | Dead slugs with correct slugs existing | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 182 | Pale-peach 'Select files to continue →' | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 183 | Home footer has no copyright/year and no | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 184 | All guests share one 10-ops/day quota | **FIXED** | Separate synthetic addresses receive separate buckets; forwarded-address spoofing is ignored in regression tests. |
| 185 | Tab freezes after local ops when | **PARTIAL** | Prior Chromium rounds navigated away after local merge in under one second. |
| 186 | Server Mode toggle can never be | **PARTIAL** | Prior Chromium rounds changed to server mode; merge produced one job and consumed one quota slot. |
| 187 | Exam Photo & Signature Resizer burns | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 188 | Mask Aadhaar rejects images while | **FIXED** | Two image-mask regression cases passed. Prefix pixels are covered and final four digits remain visible for spaced and joined numbers. |
| 189 | Tablet 768-1024px shows both headers | **PARTIAL** | Prior browser rounds measured mutually exclusive header/layout states at 360, 390, 768, 820, 834, 1024, 1104, and 1366 pixels. |
| 190 | Feedback pill covers the primary CTA on | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 191 | merge-photos 'grid' layout renders identical | **PARTIAL** | Local fix or recorded prior-browser evidence exists. Required live or expanded final verification remains. |
| 192 | Sidebar and topbar sell 'Pro Power User Rs | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 193 | Studio Export shows 'Error: [object Object]' | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 194 | Photo compress misses its 'exact target | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 195 | Photo resize runs with no dimensions | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 196 | Copy/polish bugs from Master Audit #17 | **NOT TESTED** | No discriminating final end-to-end evidence was recorded. |
| 197 | Signed-out users still look signed in - | **PARTIAL** | Prior browser round signed out, checked guest state in another tab, then reloaded. |
| 198 | Sign-in button missing after sign-out | **PARTIAL** | Sign-in control returned after sign-out in both prior browser rounds. |
| 199 | Studio Export page size A4->Letter swap unverifiable (quota-gated) (Studio, P2) - Master Audit | **NOT TESTED** | Expanded Chromium attempt received HTTP 402 `TIER_LIMIT_REACHED` (10/10 operations) before the resize could be checked. |
| 200 | Admin 'Last Active' always '-' | **PARTIAL** | Admin list derives last activity from user activity and audit records. Regression suite passed. |
| 201 | Admin shows no location on login (exact | **PARTIAL** | Offline GeoIP lookup accepts public addresses and declines private addresses. Real database absent. |
| 202 | Admin has no list of who is logged in as | **PARTIAL** | Admin sessions list and targeted revocation have local tests. No live administrator sessions inspected. |
| 203 | Super admin role: only 1 account, | **PARTIAL** | Two owner emails are accepted by separate synthetic session tests. Owner login itself was not exercised. |
| 204 | Admin has no set-plan / reset-usage | **PARTIAL** | Targeted set-plan/reset-usage actions and audit entries pass local tests. |
| 205 | Top pill nav reported broken/mixed by owner - browser found it clean at 1920px (Site, P2) - | **PARTIAL** | Viewport checks from prior browser rounds show no horizontal clipping. Expanded scrolled state did not rerun. |

## Regression gate

All 47 items previously marked verified-fixed are listed individually above. Some have test or prior browser evidence. Two item-specific regression rounds across all 47 were not completed, so the remaining entries retain PARTIAL status.

## Remaining verification

- Run the 47-item regression set twice with its requested browser and output-content checks.
- Verify provider-backed Hindi translation and the 69-page brief in an authorized non-production environment.
- Recheck the exact Drive file once an accessible test source is available.
- Verify the existing Docker volume and account login across container recreation when Docker is available.
- Owner rotates production admin credentials. No credential values appear in this report.
- Rerun expanded browser cases for extraction, duplicate, A4-to-Letter, quota dialog, Studio clear, and scrolled 1104px pages with a fresh paid-tier test account or a controlled isolated quota fixture.
- Run dependency vulnerability scanning with package-index access. Local pip-audit setup failed because network access was unavailable.
