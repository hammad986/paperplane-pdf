"""Verify mobile upload controls have distinct hit targets and only Import opens its modal."""
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
    with TemporaryDirectory(prefix="paperplane-v24-dropzone-") as temp_name:
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
                response = page.goto(base + "/resize-image-dimensions", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("state.activeView === 'desk' && state.operation === 'photo_resize'")
                assert page.locator("#cloud-drop-btn").inner_text().strip() == "Import from a cloud link"
                for width in (320, 390, 1366):
                    page.set_viewport_size({"width": width, "height": 844})
                    target_map = page.evaluate("""() => Object.fromEntries(['browse','cloud-drop-btn'].map(id => {
                      const element = document.getElementById(id);
                      const rect = element.getBoundingClientRect();
                      const top = document.elementFromPoint(rect.left + rect.width/2, rect.top + rect.height/2);
                      return [id, {rect:[rect.left, rect.right, rect.top, rect.bottom], hit:top?.closest('button')?.id || top?.id}];
                    }))""")
                    assert target_map["browse"]["hit"] == "browse", target_map
                    assert target_map["cloud-drop-btn"]["hit"] == "cloud-drop-btn", target_map
                    with page.expect_file_chooser(timeout=5000):
                        page.locator("#browse").click()
                    assert page.locator("#cloud-modal").is_hidden()
                    page.locator("#cloud-drop-btn").click()
                    assert page.locator("#cloud-modal").is_visible()
                    evidence["viewports"].append({"width": width, "targets": target_map,
                                                   "browse_opens_picker_only": True,
                                                   "import_button_opens_modal": True})
                    page.locator("#close-cloud-modal").click()
                assert not evidence["page_errors"], evidence
                assert not evidence["console_errors"], evidence
                evidence["versions"] = {"app_js": 181, "styles_css": 65, "shell": 127}
                evidence["result"] = "passed"
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait(timeout=5)
    (OUT / "browser-dropzone-import-target.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
