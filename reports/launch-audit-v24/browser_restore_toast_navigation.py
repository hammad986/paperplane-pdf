"""Check that failed-restore notices only follow an actual restore attempt."""
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


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-restore-toast-") as temp_name:
        data_dir = Path(temp_name) / "data"
        data_dir.mkdir()
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        env = {key: value for key, value in os.environ.items() if not key.upper().startswith((
            "PAPERPLANE_", "CASHFREE_", "SMTP_", "RESEND_", "OPENAI_", "OPENROUTER_",
            "BLUESMINDS_", "ANTHROPIC_", "GEMINI_", "DEEPSEEK_", "GOOGLE_API_", "AI_", "ADMIN_",
        )) and key not in {"TESTING", "SESSION_SECRET_KEY"}}
        env.update({"PAPERPLANE_SKIP_DOTENV": "1", "PAPERPLANE_ENV": "development",
                    "PAPERPLANE_DATA_DIR": str(data_dir), "PAPERPLANE_PORT": str(port),
                    "PAPERPLANE_ADMIN_KEY": secrets.token_urlsafe(48),
                    "PAPERPLANE_ADMIN_CODE": secrets.token_urlsafe(32),
                    "PAPERPLANE_SESSION_SECRET": secrets.token_urlsafe(48),
                    "PAPERPLANE_SECURE_COOKIES": "false", "PYTHONPATH": str(ROOT)})
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
                for route, expected_attempt in (("/merge-pdf", False), ("/studio", True)):
                    context = browser.new_context(viewport={"width": 1280, "height": 850})
                    context.add_init_script("sessionStorage.setItem('paperplane-last-local-document:guest', 'Unsaved Fixture.pdf')")
                    page = context.new_page()
                    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                    page.on("console", lambda message: evidence["console_errors"].append(message.text)
                            if message.type == "error" else None)
                    response = page.goto(base + route, wait_until="domcontentloaded")
                    assert response and response.status == 200
                    if expected_attempt:
                        page.wait_for_function("document.querySelector('.toast-notice')?.textContent.includes('was temporary and could not be restored')", timeout=10000)
                    else:
                        page.wait_for_timeout(1200)
                    result = page.evaluate("""() => ({
                      activeView: state.activeView,
                      notice: document.querySelector('.toast-notice')?.textContent || null,
                      marker: sessionStorage.getItem('paperplane-last-local-document:guest')
                    })""")
                    assert (result["notice"] is not None) is expected_attempt, result
                    assert (result["marker"] is None) is expected_attempt, result
                    evidence["routes"] = evidence.get("routes", []) + [{"route": route, **result}]
                    context.close()
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                evidence["asset_version"] = "app.js v166 / shell v107"
                evidence["result"] = "passed"
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    (OUT / "browser-restore-toast-navigation.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
