"""Read-only smoke check for an already-running local Paperplane server.

Run manually with ``python tests/live_verification.py``. This intentionally
does not create users, issue API keys, submit jobs, or contact external services.
"""
from __future__ import annotations

import json
import os
from urllib.parse import urlparse
from urllib.request import urlopen


BASE_URL = os.environ.get("PAPERPLANE_SMOKE_URL", "http://127.0.0.1:8501").rstrip("/")


def _get_json(path: str) -> dict:
    with urlopen(f"{BASE_URL}{path}", timeout=10) as response:
        if response.status != 200:
            raise AssertionError(f"{path} returned HTTP {response.status}")
        payload = json.loads(response.read())
    if not isinstance(payload, dict):
        raise AssertionError(f"{path} returned a non-object JSON response")
    return payload


def test_live_server() -> None:
    parsed = urlparse(BASE_URL)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise ValueError("This smoke check is restricted to an HTTP loopback server.")

    health = _get_json("/api/health")
    assert health.get("status") == "ok", "local server health is not ok"
    print(f"[OK] Health: status={health['status']}, workers={health.get('workers')}")

    integrations = _get_json("/api/integrations")
    assert integrations.get("queue") is True, "job queue integration is unavailable"
    print("[OK] Integrations endpoint is healthy")

    operations = _get_json("/api/operations")
    assert operations, "operation catalog is empty"
    print(f"[OK] Operation catalog: {len(operations)} entries")
    print("LOCAL READ-ONLY SMOKE CHECKS PASSED")


if __name__ == "__main__":
    test_live_server()
