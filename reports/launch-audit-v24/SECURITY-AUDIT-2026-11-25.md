# Paperplane local security audit — 25 Nov 2026

## Summary

Read-only review of the current local repository and production workflow. This pass checked deployment gates, SSH configuration, application security patterns, and Python dependency advisories. It did not scan the live site or run a penetration test.

The review found an important release-control gap and fixed it in the local candidate: the production deploy workflow could deploy on `main` without waiting for the full test suite, used a mutable third-party SSH action tag, and did not verify the server host key. The workflow now waits for tests, pins the SSH action to its verified v1.2.5 release commit, uses read-only `contents` permission, does not persist checkout credentials, and fails closed unless the owner configures `ORACLE_HOST_FINGERPRINT`.

## Findings

| Severity | Finding | Status and action |
|---|---|---|
| High, fixed locally | Production deployment did not depend on the test suite. A push to `main` could run the SSH deployment even if tests failed in another workflow. | Added a `verify` job to `.github/workflows/deploy.yml`, running `python -m pytest -q`; deployment now has `needs: verify`. A deployment-contract regression test checks this gate. |
| High, fixed locally; owner setup required | The deploy workflow used `appleboy/ssh-action@v1.0.3` by mutable version tag and did not pin the destination server's SSH host key. | Pinned to verified release commit `0ff4204d59e8e51228ff73bce53f80d53301dee2` (v1.2.5), passed the `fingerprint` input, and made the `ORACLE_HOST_FINGERPRINT` repository secret mandatory before SSH. Owner must obtain the host fingerprint through a trusted channel and add the GitHub secret before deployment. |
| Informational | Current requirements audit found no known published vulnerabilities. | `pip-audit -r requirements.txt --progress-spinner off`: “No known vulnerabilities found.” |
| Informational | Bandit high-severity scan found no findings in the application modules checked. | `bandit -q -r server.py persistence.py config.py ai_engine.py email_service.py converters.py security_forms_engine.py scripts/container_entrypoint.py -lll`: exit 0, no findings. |
| Remaining owner action | A previously exposed admin credential still requires rotation and a coordinated history purge/review. The existing prepared mirror predates current uncommitted changes and is not publish-ready. | Follow the existing OWNER STEPS in `FINAL-REPORT.md`. Do not publish the old mirror. |

The deployment-workflow YAML parsed locally; `tests/test_deployment_contracts.py` passed 10 tests after adding the gate regression. The exact final full suite passed twice: **748 passed, 4 warnings, 4 subtests** in 460.86s and 397.93s (`pytest-v234-deploy-gate-summary.json`). One earlier full-suite attempt had a transient 60-second Chrome timeout; the isolated HTML-to-PDF test then passed in 12.43s, and both fresh complete suite runs passed (`pytest-v234-deploy-gate-round1.log`, `pytest-v234-deploy-gate-round2.log`).

## Scope and limits

- Reviewed local Compose, Docker, Nginx, application configuration, authentication-cookie settings, and GitHub workflows.
- Confirmed the application uses required environment secrets, production session-secret checks, trusted-host/CORS configuration, and secure-cookie settings in production by source inspection.
- `pip check` reported conflicts among unrelated packages installed in this shared Python environment (including browser-use, Semgrep, OpenHands, and OpenTelemetry tools). These are not dependencies declared by Paperplane's `requirements.txt`; they do not establish a Paperplane runtime dependency conflict. The project's full test suite is the runtime compatibility evidence.
- No live URL, production SSH host, TLS certificate, or deployment was contacted. No credentials were read or printed, no real payment was made, and no repository history was rewritten in this pass.
- This is a high-impact configuration review, not a full penetration test or a guarantee of security.
