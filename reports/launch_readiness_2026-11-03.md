# Launch readiness verification — 2026-11-03 to 2026-11-04

## Decision

**Local source: verification passed for the checks listed below. Live production: NOT READY for sign-off.** The deployed site responds, but its HTML references older frontend bundles than this workspace and serves a weaker/different CSP. The current fixes have not been deployed. No deployment was performed.

This report records concrete coverage and known limits; it does not claim a universal 100% guarantee.

## Changes completed

- Responsive mobile navigation and tool surfaces, including the studio/editor and AI view, were adjusted based on the supplied references.
- Free upload limits are aligned to 50 MiB; production's 500 MiB upload limit now has multipart headroom (`client_max_body_size 512m`).
- Quota/action validation and AI workflow regressions received coverage.
- Deployment dry-run output now says `preflight_passed`; only an actual deployment plus smoke verification can claim deployment verification.
- Deployment sign-off documentation now marks the live deployment unverified.

## Verification evidence

| Check | Result |
| --- | --- |
| Full Python suite (`pytest -q`) | **229 passed, 1 warning** (532.67 seconds) |
| Targeted deployment/API/live-E2E checks | **23 passed, 1 warning** |
| Python compilation, JavaScript syntax, Compose config, `git diff --check` | **Passed** |
| Local browser matrix | **413 route/viewport cases**: Chromium across 41 tool routes at 9 widths (320–1920 px), plus Firefox and WebKit across 11 core routes at phone and laptop widths; no outer horizontal overflow, title mismatches, or JavaScript runtime errors |
| Live browser matrix (read-only) | **167 cases**: Chromium across 41 tool routes at phone/laptop/desktop sizes, plus Firefox and WebKit on core routes at phone/laptop sizes; no overflow, title mismatch, page exception, or HTTP error response |
| Current-source container through local Nginx | Nginx config test passed; HTTP redirected to HTTPS; HTTPS health returned 200 with current CSP/security headers; browser checks passed at 390, 1366, and 1920 px |
| Current-source container workflows | 41 operations reported available; DOCX→PDF completed and extracted text matched; OCR completed and recognized the synthetic phrase; secure signup cookie verified (`HttpOnly`, `Secure`, `SameSite=Lax`) without a token in the response body |
| Fresh `docker compose build --pull` | **Passed**; image built successfully after slow upstream package downloads |
| Fresh built-image smoke | **Passed**; container health 200, 41/41 operations implemented and available, grayscale job completed, PDF download returned 200 with `%PDF-` header |

### Known warning / live-site differences

- The live site emitted Google Identity stylesheet CSP violations because its deployed policy omits the required Google stylesheet origin. Its live HTML still references `styles.css?v=3.5.10` and `app.js?v=3.5.9`; workspace source references `styles.css?v=3.5.21` and `app.js?v=3.5.14`.
- The live policy also permits `unsafe-inline` scripts while the current source does not. Therefore live browser results describe the existing deployment, not the changes in this workspace.
- The 39 cancelled live `api/seo/...` requests occurred as the route-matrix harness navigated away. They were not server error responses. The CSP console violations are a real live issue.
- One pytest warning is a Starlette/httpx deprecation warning.

## Coverage boundaries and release blockers

- Physical-device testing on actual phones, tablets, laptops, and assistive technologies was not available here.
- The production domain was only checked with read-only health/browser requests. There was no write, deploy, migration, or production file operation.
- To claim deployment readiness, deploy the reviewed current source through the normal release process, then rerun smoke checks against the resulting live version and confirm deployed asset hashes/CSP match the source. Recheck Google Identity styling and the key upload, editor, conversion, and AI flows on the live deployment.

## Artifacts

- Browser test details: `reports/browser_verification.md` and `reports/browser_verification.json`.
- Machine-readable dry-run status: `reports/deployment_last_run.json` (`preflight_passed`, not deployment sign-off).
- Superseding deployment status: `reports/deployment_signoff.md`.
