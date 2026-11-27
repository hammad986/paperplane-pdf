"""Browser-check that a login OTP challenge never leaks its code in HTTP headers.

The local mail dispatcher is replaced with a success stub before Uvicorn starts;
no SMTP/API request and no real email is sent. The response is produced by the
real server route and inspected from Chromium.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

with TemporaryDirectory(prefix="paperplane-id90-otp-header-") as temp_dir:
    data_dir = Path(temp_dir) / "data"
    os.environ.update(
        PAPERPLANE_SKIP_DOTENV="1",
        PAPERPLANE_ENV="development",
        PAPERPLANE_DATA_DIR=str(data_dir),
        PAPERPLANE_SECURE_COOKIES="false",
        PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),
        PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(30),
    )
    import persistence
    persistence.init_db()
    email = f"id90-{secrets.token_hex(5)}@example.invalid"
    password = f"Audit-{secrets.token_urlsafe(20)}!"
    persistence.create_user(email, password)

    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        port = candidate.getsockname()[1]

    # Import server only after the temporary database is selected, then stub
    # only the SMTP/API boundary. The challenge route and response are real.
    import server
    captured_codes: list[str] = []
    def capture_without_delivery(_recipient: str, code: str, _purpose: str = "login") -> bool:
        captured_codes.append(str(code))
        return True
    server.send_otp_email = capture_without_delivery
    import uvicorn
    config = uvicorn.Config(server.app, host="127.0.0.1", port=port, log_level="error", workers=1)
    uvicorn_server = uvicorn.Server(config)
    import threading
    thread = threading.Thread(target=uvicorn_server.run, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    try:
        for _ in range(200):
            if not thread.is_alive():
                raise RuntimeError("Isolated OTP test server exited before startup")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.1)
        else:
            raise RuntimeError("Isolated OTP test server did not start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            context = browser.new_context(viewport={"width": 390, "height": 844})
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            response = page.goto(base + "/login", wait_until="domcontentloaded")
            if response and response.status == 404:
                response = page.goto(base + "/", wait_until="domcontentloaded")
            assert response and response.status == 200, response.status if response else None
            result = page.evaluate("""async ({email, password}) => {
              const response = await fetch('/api/auth/login', {
                method: 'POST', credentials: 'include',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({email, password, require_otp: true})
              });
              const headers = [...response.headers.entries()];
              return {status: response.status, body: await response.json(), headers};
            }""", {"email": email, "password": password})
            cookies = context.cookies(base)
            forbidden_headers = [
                (name, value) for name, value in result["headers"]
                if "otp" in name.lower() or "one-time" in value.lower()
                or any(code and code in value for code in captured_codes)
            ]
            leaked_dev_code = "dev_otp" in result["body"]
            leaked_code_in_body = any(code and code in json.dumps(result["body"]) for code in captured_codes)
            authenticated_cookie = any(cookie["name"] == "paperplane_token" for cookie in cookies)
            assert result["status"] == 200, result
            assert result["body"].get("status") == "otp_required", result
            assert len(captured_codes) == 1 and len(captured_codes[0]) == 6 and captured_codes[0].isdigit()
            assert not leaked_dev_code, result
            assert not leaked_code_in_body, result
            assert not forbidden_headers, forbidden_headers
            assert not authenticated_cookie, cookies
            assert not page_errors, page_errors
            report = {
                "scenario": "real local login challenge route with controlled no-network mail success stub",
                "mail_network_calls": 0,
                "captured_code_digits": len(captured_codes[0]),
                "status": result["status"],
                "challenge_status": result["body"].get("status"),
                "dev_otp_body_key_present": leaked_dev_code,
                "captured_code_present_in_body": leaked_code_in_body,
                "otp_related_response_headers": forbidden_headers,
                "authenticated_session_cookie_issued": authenticated_cookie,
                "guest_quota_cookie_only": any(cookie["name"] == "paperplane_guest_quota" for cookie in cookies),
                "page_errors": page_errors,
            }
            browser.close()
    finally:
        uvicorn_server.should_exit = True
        thread.join(timeout=10)
        if thread.is_alive():
            uvicorn_server.force_exit = True
            thread.join(timeout=5)

report_path = ROOT / "reports" / "launch-audit-v23" / "browser-id90-otp-header-local.json"
report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps(report, indent=2))
