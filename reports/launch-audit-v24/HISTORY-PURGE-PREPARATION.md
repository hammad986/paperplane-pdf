# Admin fallback history purge preparation

## Finding

The redacted full-history Gitleaks 8.24.2 scan on 2026-11-25 scanned all 49 commits (~159 MB) and found two historical `paperplane-admin-fallback` matches in `server.py`: commits `8dd50e6921643b659028f586abcd93dbbee7d57f` and `1596e5d135637cf36183255970e3a9a11a8614d3`. Secret values are intentionally not recorded here. Treat both historical admin credentials as compromised until rotated.

The current source reads `PAPERPLANE_ADMIN_KEY` and `PAPERPLANE_ADMIN_CODE` as required environment settings. Docker Compose no longer supplies fallback values, `.env` is ignored and not tracked, and the existing Gitleaks workflow scans incoming commits with redaction. No credential value or private-key material was printed or copied into this report. A separate redacted current-tree Gitleaks scan found expected credential-shaped matches in the ignored local `.env` and ignored local certificate/test fixtures; the exact v234 Docker image contains none of these paths. The owner should review the local `.env` privately and rotate any production value that may have been shared.

## Purge preparation

1. Owner rotates both admin values in the deployment environment and verifies the new OTP/admin access before using the application.
2. Keep this working tree and all uncommitted implementation changes backed up. Do not rewrite this active checkout: it is on `main` and has extensive uncommitted changes.
3. After the code changes are committed in the owner's normal review process, make a separate full mirror clone and preserve a second offline backup.
4. In the mirror only, use `git-filter-repo` with a reviewed blob callback that rewrites the two historical `PAPERPLANE_ADMIN_KEY` / `PAPERPLANE_ADMIN_CODE` fallback expressions to environment-only lookups. Do not place either old value in a command line, script, report, or shell history.
5. Run the configured full-history Gitleaks scan with `--redact=100`; require zero findings, verify current source contains no credential fallback, then check every branch and tag ref.
6. Owner reviews and authorizes any force-push of rewritten refs. Coordinate a fresh clone for collaborators; do not merge old refs back. No history rewrite or push was performed in this audit.

## Evidence

- Redacted full-history match metadata: `gitleaks-full-history-current-redacted-2026-11-25.json`.
- Redacted current-tree scan: `gitleaks-current-tree-redacted-2026-11-25.json`.
- Current source requires environment configuration in `server.py`; Compose requires the admin code setting and does not define a fallback.
- CI rule: `.github/workflows/secrets.yml`; detector: `.gitleaks.toml`.
- This document contains commit identifiers and remediation steps only, never the matched credential values.
