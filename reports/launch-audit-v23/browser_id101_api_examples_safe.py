"""Verify the API reference displays environment-based auth examples in Chrome."""
from __future__ import annotations

import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

rounds = []
with TemporaryDirectory(prefix="paperplane-id101-api-examples-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        else:
            raise RuntimeError("Local Paperplane app failed to start")

        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/developers", wait_until="domcontentloaded")
                assert response and response.status == 200
                code = page.locator("#full-api-code-curl").inner_text()
                assert "${PAPERPLANE_API_KEY}" in code, code
                assert "${IDEMPOTENCY_KEY}" in code, code
                assert "your_api_key" not in code.lower(), code
                assert "sk_test_" not in code.lower(), code
                assert not errors, errors
                rounds.append({"round": round_no, "http_status": response.status,
                               "uses_env_api_key": True, "uses_idempotency_variable": True,
                               "credential_literals_absent": True, "page_errors": errors})
                page.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=8)

report = {"base": base, "route": "/developers", "rounds": rounds, "verdict": "PASS"}
(OUT / "browser-id101-api-examples-safe.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
