# Paperplane Railway Deployment Runbook (Prepared, Not Executed)

This runbook matches the current repository and Railway's current deployment model. No deployment, Git action, or live billing request was performed.

## Current candidate facts

- Root `Dockerfile` is the production image definition; it installs the PDF/OCR/conversion tools and starts `scripts/container_entrypoint.py` as the container entrypoint.
- The app now prefers Railway's injected `PORT` over the Docker default `PAPERPLANE_PORT=8501`. Local regression tests cover the precedence and defaults.
- When the Railway runtime marker `RAILWAY_SERVICE_ID` is present, the app's trusted-host list includes `healthcheck.railway.app`, the host Railway uses for deploy health checks.
- A disposable v154 production image ran health checks and the 44-operation browser catalog: 41 content-checked downloads in each of two rounds, SSRF test blocked, two provider-only AI operations unavailable without credentials, zero browser errors. It also ran with Railway-style `PORT=18529` alongside conflicting `PAPERPLANE_PORT=8501`; the app and Docker health check both reported healthy.
- The live domain was previously observed serving stale app.js v91 versus this workspace's app.js v145, and some requests timed out. Recheck availability and exact asset versions before replacing it.

## Railway service settings

1. Configure the Paperplane service to build from the repository root `Dockerfile`.
2. Set health check path to `/api/health`; allow Railway enough startup time for the image's OCR/PDF dependencies and database initialization. A healthy check must return HTTP 2xx.
3. Attach a persistent Railway volume at `/data`. Keep the app to one replica while SQLite is the application database. Confirm the mounted volume before the first rollout; do not initialize an empty replacement over existing account/job data.
4. Set the service public domain and TLS, then set `PAPERPLANE_PUBLIC_URL` and `PAPERPLANE_ALLOWED_ORIGINS` to that exact HTTPS origin.
5. Configure `PAPERPLANE_TRUSTED_HOSTS` with the public domain. Railway health-check host support is automatic when `RAILWAY_SERVICE_ID` is present.
6. Use Railway's injected `PORT`; do not pin a conflicting `PORT`. The app now honors it even though the image supplies a local `PAPERPLANE_PORT` default.

## Required production variables

Set these through Railway's sealed service variables, never source files:

- `PAPERPLANE_ENV=production`
- `PAPERPLANE_HOST=0.0.0.0`
- `PAPERPLANE_DATA_DIR=/data`
- `PAPERPLANE_PUBLIC_URL=https://<your-domain>`
- `PAPERPLANE_ALLOWED_ORIGINS=https://<your-domain>`
- `PAPERPLANE_TRUSTED_HOSTS=<your-domain>,healthcheck.railway.app`
- `PAPERPLANE_SESSION_SECRET=<fresh random 32-byte-or-longer value>`
- `PAPERPLANE_ADMIN_KEY=<fresh owner-rotated value>`
- `PAPERPLANE_ADMIN_CODE=<fresh owner-rotated value>`
- `PAPERPLANE_SECURE_COOKIES=true`
- `PAPERPLANE_ALLOW_BILLING_SIMULATION=false`
- `PAPERPLANE_ALLOW_TEST_PAYMENTS=false`
- `CASHFREE_ENV=PROD`, plus owner-configured production merchant credentials and webhook secret
- A verified transactional sender and real email delivery credentials before enabling account OTP, password reset, or admin OTP flows
- AI provider secrets only for providers you intend to enable; validate quotas and data-processing disclosure before enabling

Keep `PAPERPLANE_JOB_TTL_SECONDS` aligned with the privacy/support policy and available storage. Do not enable multiple app replicas against one SQLite volume.

## Staged rollout and acceptance

1. Make an encrypted, restorable backup of the existing `/data` volume/database. Verify its size and timestamp, and retain the prior Railway deployment for rollback.
2. Deploy to a staging Railway environment with separate volume, secrets, domain/origins, and billing sandbox credentials. Never copy production secrets into staging.
3. Verify health, worker count, actual served `app.js` / PDF runtime / service-worker versions, and that the browser can reach the app without mixed content or console errors.
4. Upload a synthetic, marker-bearing PDF and verify its downloaded output contents for Merge, Split, Compress, OCR, conversion, and Studio workflows. Exercise guest and authenticated access, rate limits, cancellation, restart persistence, and offline local Merge. Do not use customer documents for acceptance tests.
5. Run a sandbox checkout only after owner approval and only in staging. A production payment must be a separately authorized owner action.
6. For production, verify health and asset versions first, then a minimal synthetic PDF round trip and email/OTP behavior. Monitor queue health, errors, storage, and provider latency during rollout. Keep the old deployment and backup available until checks complete.
7. Roll back to the previous known-good Railway deployment if health, asset integrity, PDF content, email, or storage persistence fails. Do not point the new release at a different/empty volume as a rollback substitute.

## Current release gate

This repository still has a HOLD verdict: 324/353 checklist entries are fixed locally, 28 remain partial, and one owner-only payment item remains blocked. Outstanding evidence includes the current deployed app being stale/unavailable at times, real provider stability, physical Android/iOS capture/install, Studio's <250 ms long-task target on low-end hardware, owner credential rotation/history purge, owner legal/merchant decisions, and the real production payment check. Complete the applicable owner actions and retest after deployment before calling the release ready.

## Official Railway references

- [Dockerfiles](https://docs.railway.com/builds/dockerfiles)
- [Health checks](https://docs.railway.com/deployments/healthchecks)
- [Volumes](https://docs.railway.com/volumes)
- [Variables reference](https://docs.railway.com/variables/reference)
