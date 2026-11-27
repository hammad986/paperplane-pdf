"""Verify the Studio conversion dialog stays within common phone viewports."""
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
    evidence: dict = {"page_errors": [], "console_errors": [], "viewports": []}
    with TemporaryDirectory(prefix="paperplane-v24-convert-modal-") as temp_name:
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
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda message: evidence["console_errors"].append(message.text)
                        if message.type == "error" else None)
                response = page.goto(base + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("window.conversionEngine && document.readyState === 'complete'")
                for width, height in ((320, 720), (360, 800), (390, 844), (430, 932),
                                      (844, 390), (932, 430)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.evaluate("() => { void window.conversionEngine.openConvertModal(new File(['fixture'], 'source document.pdf', {type:'application/pdf'})); return true; }")
                    page.wait_for_function("!document.querySelector('#convert-modal').hidden")
                    assert page.evaluate("document.activeElement.id === 'modal-close-convert'")
                    if width == 320 and height == 720:
                        page.evaluate("""() => {
                          const modal = document.querySelector('#convert-modal');
                          const focusable = [...modal.querySelectorAll('button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [href], [tabindex]:not([tabindex="-1"])')]
                            .filter(element => element.getClientRects().length && getComputedStyle(element).visibility !== 'hidden');
                          focusable.at(-1).focus();
                        }""")
                        page.keyboard.press("Tab")
                        assert page.evaluate("document.activeElement.id === 'modal-close-convert'")
                        page.keyboard.press("Shift+Tab")
                        assert page.evaluate("document.activeElement.id !== 'modal-close-convert' && document.querySelector('#convert-modal').contains(document.activeElement)")
                    page.locator("#convert-tab-to-pdf").click()
                    page.locator("#convert-tab-from-pdf").click()
                    metrics = page.evaluate("""() => {
                      const modal = document.querySelector('#convert-modal .convert-modal-card');
                      const dialog = modal.getBoundingClientRect();
                      const close = document.querySelector('#modal-close-convert').getBoundingClientRect();
                      const tabs = document.querySelector('#convert-modal .convert-direction-tabs').getBoundingClientRect();
                      const pageWidth = document.documentElement.scrollWidth;
                      return {viewport: [innerWidth, innerHeight], dialog: [dialog.left, dialog.right, dialog.width],
                        close: [close.left, close.right], tabs: [tabs.left, tabs.right], pageWidth,
                        bodyWidth: modal.scrollWidth, bodyClientWidth: modal.clientWidth};
                    }""")
                    assert metrics["dialog"][0] >= -0.5 and metrics["dialog"][1] <= width + 0.5, metrics
                    assert metrics["close"][0] >= metrics["dialog"][0] and metrics["close"][1] <= metrics["dialog"][1], metrics
                    assert metrics["tabs"][0] >= metrics["dialog"][0] and metrics["tabs"][1] <= metrics["dialog"][1], metrics
                    assert metrics["pageWidth"] <= width + 1, metrics
                    evidence["viewports"].append(metrics)
                    page.locator("#modal-close-convert").click()
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                evidence["versions"] = {"app_js": 186, "styles_css": 69, "shell": 136}
                evidence["result"] = "passed"
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    (OUT / "browser-conversion-modal-mobile.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
