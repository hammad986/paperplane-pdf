"""Create one owner-assigned GitHub issue after a scheduled Cashfree probe failure."""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request


TITLE = "Cashfree sandbox checkout probe failed"
API = "https://api.github.com"


def ensure_failure_issue(
    repository: str,
    token: str,
    run_id: str,
    *,
    opener=urllib.request.urlopen,
) -> tuple[bool, int | None]:
    match = re.fullmatch(r"([A-Za-z0-9_.-]{1,100})/([A-Za-z0-9_.-]{1,100})", repository)
    if not match:
        raise ValueError("GITHUB_REPOSITORY must be owner/name")
    if not re.fullmatch(r"[0-9]{1,20}", run_id):
        raise ValueError("GITHUB_RUN_ID must be numeric")
    if not token:
        raise ValueError("GITHUB_TOKEN is required to create the owner alert")

    owner, repo = match.groups()
    base = f"{API}/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo)}"
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "User-Agent": "Paperplane-Cashfree-Probe-Alert",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    issues_request = urllib.request.Request(
        f"{base}/issues?state=open&per_page=100",
        headers=headers,
    )
    with opener(issues_request, timeout=20) as response:
        issues = json.loads(response.read().decode("utf-8"))
    existing = next(
        (issue for issue in issues
         if not issue.get("pull_request") and issue.get("title") == TITLE),
        None,
    )
    if existing:
        return False, existing.get("number")

    run_url = f"https://github.com/{owner}/{repo}/actions/runs/{run_id}"
    body = (
        f"@{owner} The scheduled Cashfree TEST sandbox checkout probe failed.\n\n"
        "The probe only creates and verifies an unpaid INR 1.00 sandbox order; it does not submit a payment.\n\n"
        f"Review the [failed workflow run]({run_url}) and close this issue after the probe passes."
    )
    payload = json.dumps({
        "title": TITLE,
        "body": body,
        "assignees": [owner],
    }).encode("utf-8")
    create_request = urllib.request.Request(
        f"{base}/issues",
        data=payload,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with opener(create_request, timeout=20) as response:
        issue = json.loads(response.read().decode("utf-8"))
    return True, issue.get("number")


def main() -> int:
    try:
        created, issue_number = ensure_failure_issue(
            os.environ.get("GITHUB_REPOSITORY", ""),
            os.environ.get("GITHUB_TOKEN", ""),
            os.environ.get("GITHUB_RUN_ID", ""),
        )
    except (OSError, urllib.error.URLError, ValueError, json.JSONDecodeError) as error:
        # Keep access tokens and response bodies out of Action logs.
        print(f"::error::Could not ensure the Cashfree probe owner alert ({type(error).__name__}).")
        return 1
    if created:
        print(f"Created owner-assigned Cashfree probe alert issue #{issue_number}.")
    else:
        print(f"Cashfree probe alert issue #{issue_number} is already open; no duplicate was created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
