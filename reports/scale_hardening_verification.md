# Paperplane Scale-Hardening Verification

Date: 2026-10-26

## Implemented safeguards

- Upload bodies spool to isolated disk files in 64 KiB chunks with a hard size limit; partial files are removed on rejection.
- The requested `/api/jobs`, `/api/conversions`, `/api/studio/forms/analyze`, `/api/ai/chat`, and `/api/ai/summarize` paths use bounded spooling. Other server upload handlers use the same helper.
- LibreOffice conversions are guarded by a bounded process semaphore and retain isolated profiles/process-tree termination.
- Default job retention is 7,200 seconds; cleanup checks the data-volume free-space percentage and 2 GiB floor.
- Emergency cleanup purges completed/failed jobs older than 30 minutes, removes stale `paperplane-lo-*` profiles, runs `PRAGMA incremental_vacuum(500)`, and logs the reclaimed megabytes.
- SQLite connections use a 30-second busy timeout, WAL journaling, and `synchronous=NORMAL`.
- The pricing modal renders `₹250/month` and `₹750/month`, with Cashfree checkout triggers and explicit UPI, UPI QR, and card method indicators.
- Deployment dry-run tolerates an installed-but-unavailable Docker daemon and still validates configuration-only deployment actions.

## Verification results

| Check | Result |
|---|---|
| `python -m py_compile server.py converters.py config.py persistence.py tests/test_streaming_uploads.py` | PASS |
| `pytest tests/` | PASS — 178 passed, 1 dependency warning |
| Streaming spool regression tests | PASS — fixed 64 KiB reads, bounded peak heap, partial-file cleanup |
| `python scripts/preflight_test.py` | PASS — 37/37 checks |
| `python scripts/deploy_production.py --dry-run` | PASS — production deployment sign-off |
| `python scripts/browser_verification.py` | PASS — pricing modal/theme flow rendered with 0 console errors, page errors, or failed requests |
| `python scripts/cashfree_sandbox_smoke.py` | SKIPPED — `CASHFREE_APP_ID` and `CASHFREE_SECRET_KEY` are not configured here |

## Logs

- `reports/preflight_scale_hardening.log`
- `reports/deployment_dry_run.log`
- `reports/deployment_last_run.json`
- `reports/browser_verification.json`
- `reports/browser_server.log`
- `reports/cashfree_sandbox_smoke.log`
