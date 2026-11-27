# Security self-scan — 2026-11-19

## Scope

This was a passive, targeted self-scan of the current Paperplane source and the owner's deployed HTTPS site. It checked Python dependencies, high-confidence credential patterns in first-party runtime/config paths and their Git history, response headers, and nine common accidental-exposure paths. This is not a penetration test and does not establish a security certification.

## Results and changes

- `pip-audit -r requirements.txt`: no known vulnerabilities were reported for the installed dependency set.
- Targeted high-confidence credential-pattern scan: no matches in `.github`, `deploy`, `scripts`, `web`, or the named first-party runtime Python files. The same patterns produced no matches in Git history for those paths. The documentation's sample `API_KEY` assignments were placeholder examples, not usable keys. Generated temporary test certificates under ignored/nested temporary test output were excluded from the source finding count.
- Passive live check of `https://paperplane.qd.je`: HTTP redirects to HTTPS; HTTPS returned 200; certificate expiry reported Jan 29, 2027. HSTS, CSP, `nosniff`, frame options, referrer policy, and permissions policy were present. Nine common exposure paths (`.env`, `.git` metadata, backup/config files, and status/phpinfo endpoints) all returned 404. No response bodies were retained. Raw evidence: `security-passive-live-check.json`.
- The deployed CSP at scan time did not include `base-uri` or `frame-ancestors`. Added both directives to the Compose Nginx template and the standalone Nginx config. They complement same-origin framing already enforced by `X-Frame-Options: SAMEORIGIN` and prevent an injected external `<base>` from changing relative URL resolution.
- Extended the CSP regression and real-browser Nginx integration check to require both directives. Focused tests passed (2); the local production-mode Nginx/app stack passed two Chromium rounds over HTML, JavaScript asset, and API 404 responses (all 200/200/404, all eight security headers once, no page errors). Evidence: `browser-id246-nginx-headers.json`. The complete current-source suite passed twice after the CSP and responsive-layout changes (596 tests per run, four existing deprecation warnings).

## Remaining verification

The live service has not received this workspace change. After deployment, recheck the live CSP for `base-uri 'self'` and `frame-ancestors 'self'`, verify the page still loads without CSP violations, and rerun the passive header/exposure probes. This targeted scan does not replace the open v23 item checks, external provider tests, owner review, or a broader security assessment.


## Follow-up source review (2026-11-19)

A targeted review of dynamic HTML insertion found that both API-key list renderers interpolated the server-returned `key_prefix` directly into `innerHTML`. Both now escape this value before markup insertion. The browser regression supplied a synthetic `<img src=x onerror=...>` value to each renderer and confirmed it remained text, created no image elements, executed no handler, and caused no page errors. The local PWA shell/cache was bumped to v50/app.js v118; two Chromium offline rounds loaded those exact assets successfully. `pip-audit -r requirements.txt --progress-spinner off` returned “No known vulnerabilities found.” `git ls-files` shows `.env.example` as the only tracked environment file; the prior targeted credential scan and live passive checks are recorded above. The follow-up suite passed twice at 610 tests with four existing deprecation warnings per run.

This is a targeted common-issue review, not a penetration test or security guarantee. The live deployment remains on older assets until the owner deploys; rerun the CSP, asset, and UI checks against production afterward.


A second current-source review found provider-controlled invoice extraction values (`quantity` and `source_pages`) inserted without HTML escaping. Both paths now encode values before insertion. Chromium verified hostile `<img onerror>` strings stay text and create no elements in the invoice table or page citation list. The app/cache update is v119/shell-v51. The current P0 browser suite passed 60 checks with no page errors; the full suite passed twice at 611 each. Evidence: `browser-security-extraction-values-xss.json`, `browser-id357-offline-v51-smoke.json`, `browser-p0.json`, and `pytest-id-extraction-xss-run*.log`.


A third DOM-sink review found the password-recovery response HTML-joined `message` and a development reset URL. The UI now uses `textContent` and renders the development link only when it parses as a same-origin root URL containing `reset_token`. Chromium confirmed hostile markup stays inert, `javascript:` is rejected, and a valid local token link still appears. Combined latest verification: P0 browser matrix 60/60, shell v52 offline check 2/2, and full test suite 612 passed twice. Candidate app.js v120 / shell v52. Evidence: `browser-security-password-reset-response-xss.json`, `browser-id357-offline-v52-smoke.json`, `browser-p0.json`, `pytest-id-reset-xss-run*.log`.


Final current-candidate security UI follow-up: password-recovery response content is rendered as text, and the development reset URL is constrained to same-origin root URLs carrying a reset token. Browser-tested hostile HTML plus a `javascript:` URL is inert; a valid same-origin synthetic token link is preserved. App.js v120 / shell v52 passed P0 60/60, offline rounds 2/2, and two 612-test full-suite runs. This remains a targeted common-issue review, not a penetration test or security guarantee.
