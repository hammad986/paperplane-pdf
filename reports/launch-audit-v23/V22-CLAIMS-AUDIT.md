# V22 claims audit for v23

Baseline: `main` at `03436d90d9fc233eedf3a614eaa5de4f520137ca`. The worktree was clean before v23 evidence files were created. No code changes were present at the start of this audit.

| V22 claim | Current evidence | V23 disposition |
|---|---|---|
| ID 241 replacement of `{n}` and `{total}` | `server.py` replacement covers both tokens; tests in `tests/test_text_layer_v18.py` and `tests/test_launch_audit_v22.py`. | Code present; preserve regression coverage. |
| ID 309 scan-to-PDF size | Pixel-size handling exists in `converters.py`, `server.py`, and `web/assets/app.js`; V22 regression tests remain. | Code present; fresh route/catalog retest is in progress. |
| ID 283 compression rendered-content guard | Compression skips unsafe alpha/palette/CMYK replacement and validates output; V21/V22 tests remain. | Code present; needs content audit evidence in the v23 catalog. |
| ID 299 billing response omits Cashfree order ID | Public status response omits the internal order ID while persistence uses it. | Code present; live response was not rechecked in this local-only round. |
| ID 1 provider errors and fallback | Retry/fallback helper and safe 429 mapping are present. Provider availability is still an external requirement; a new translated-fraction gate now rejects results below 50%. | Code changes made; controlled test and local browser evidence recorded. Real provider is rate-limited and remains unverified. |
| ID 246 CSP and nginx version hiding | Both nginx templates set `server_tokens off` and CSP. | Template code present; deployed headers were not checked in this local-only round. |
| ID 220 PDF/A profile support | Docker image installs ICC profiles; converter locates the profile and checks PDF/A metadata/OutputIntent. | Code present; production-image veraPDF validation remains unverified. |
| Full test suite passed 488 twice | Baseline before v23 code edits: 488 passed twice, logs `pytest-baseline-run1.log` and `pytest-baseline-run2.log`. | Confirmed baseline. A post-change full-suite pair remains required. |
| 176 responsive route checks | The earlier v22 route matrix was absent from this checkout. | Not inherited as current proof. P0 layout/browser checks were rerun locally for v23. |
| 44-operation catalog: 39 passed and P0 status | Earlier v22 report folders/artifacts are absent in this checkout. | Not inherited as current proof. V23 local 44-operation catalog is being rerun; see reproduction log. |

This audit does not convert prior live claims into current v23 verification. Only evidence generated in the v23 folder closes the associated v23 check.
