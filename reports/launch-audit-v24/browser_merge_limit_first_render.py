"""Verify authenticated Merge limits are correct on the first HTML render."""
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
OUT = Path(__file__).resolve().parent


def isolated_env(data_dir: Path, port: int) -> dict[str, str]:
    env = {
        key: value for key, value in os.environ.items()
        if not key.upper().startswith((
            "PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
            "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_",
        ))
        and key not in {"TESTING", "SESSION_SECRET_KEY"}
    }
    env.update({
        "PAPERPLANE_SKIP_DOTENV": "1",
        "PAPERPLANE_ENV": "development",
        "PAPERPLANE_DATA_DIR": str(data_dir),
        "PAPERPLANE_PORT": str(port),
        "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
        "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
        "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
        "PAPERPLANE_SECURE_COOKIES": "false",
        "PYTHONPATH": str(ROOT),
    })
    return env


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-merge-limit-") as temp_name:
        temp = Path(temp_name)
        data_dir = temp / "data"
        data_dir.mkdir()
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        env = isolated_env(data_dir, port)
        seed = """
import json
from persistence import init_db, create_user, create_session, set_user_tier
init_db()
email = 'merge-first-render@example.invalid'
password = 'Synthetic-Only-Merge-Test-318!'
user_id = create_user(email, password)
set_user_tier(user_id, 'developer')
print(json.dumps({'email': email, 'token': create_session(email, password)['token']}))
"""
        seeded = subprocess.run([sys.executable, "-c", seed], cwd=ROOT, env=env,
                                capture_output=True, text=True, check=True, timeout=30)
        identity = json.loads(seeded.stdout)
        app = subprocess.Popen([sys.executable, "app.py"], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            base = f"http://127.0.0.1:{port}"
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                authenticated = browser.new_context(viewport={"width": 1280, "height": 850})
                authenticated.add_cookies([{
                    "name": "paperplane_token", "value": identity["token"],
                    "url": base, "httpOnly": True, "secure": False, "sameSite": "Lax",
                }])
                page = authenticated.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                        if message.type == "error" else None)
                response = page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("state.activeView === 'desk' && state.operation === 'merge'")
                initial = page.evaluate("""() => ({
                  authenticatedLimit: JSON.parse(document.querySelector('#paperplane-bootstrap').textContent).planLimits.max_batch_files,
                  displayedHint: document.querySelector('#file-hint').textContent,
                  authEmail: state.user?.email || null
                })""")
                headers = response.all_headers()
                page.wait_for_function("state.user && state.user.email === 'merge-first-render@example.invalid'")
                settled = page.evaluate("""() => ({
                  authenticatedLimit: JSON.parse(document.querySelector('#paperplane-bootstrap').textContent).planLimits.max_batch_files,
                  displayedHint: document.querySelector('#file-hint').textContent,
                  authEmail: state.user?.email || null
                })""")
                assert initial["authenticatedLimit"] == 100
                assert "100 PDF files per run" in initial["displayedHint"], initial
                assert headers.get("cache-control") == "private, no-store", headers
                assert "cookie" in headers.get("vary", "").lower(), headers
                assert settled["authenticatedLimit"] == 100 and "100 PDF files per run" in settled["displayedHint"]
                evidence["authenticated"] = {"initial": initial, "settled": settled,
                                               "cache_control": headers.get("cache-control"),
                                               "vary": headers.get("vary")}

                guest = browser.new_context(viewport={"width": 1280, "height": 850})
                guest_page = guest.new_page()
                guest_page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                guest_response = guest_page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                assert guest_response and guest_response.status == 200
                guest_initial = guest_page.evaluate("""() => ({
                  authenticatedLimit: JSON.parse(document.querySelector('#paperplane-bootstrap').textContent).planLimits.max_batch_files,
                  displayedHint: document.querySelector('#file-hint').textContent
                })""")
                assert guest_initial["authenticatedLimit"] == 10
                assert "10 PDF files per run" in guest_initial["displayedHint"], guest_initial
                evidence["guest"] = guest_initial
                browser.close()

        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except subprocess.TimeoutExpired:
                app.kill()

    evidence["result"] = not evidence["page_errors"] and not evidence["console_errors"]
    (OUT / "browser-merge-limit-first-render.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["result"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
