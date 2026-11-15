"""Chromium regression for deleting one Studio page from the main toolbar."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = r'''
import json, os, secrets
from pathlib import Path
import persistence, server, uvicorn
persistence.init_db()
email = "toolbar-delete-" + secrets.token_hex(6) + "@example.invalid"
password = secrets.token_urlsafe(30)
persistence.create_user(email, password)
tokens = {"user": persistence.create_session(email, password)["token"]}
Path(os.environ["V18_IDENTITIES"]).write_text(json.dumps(tokens))
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-toolbar-delete-v18-") as temp:
        directory = Path(temp)
        source = directory / "ten-pages.pdf"
        with fitz.open() as document:
            for i in range(10):
                page = document.new_page()
                page.insert_text((72, 72), f"Toolbar delete page {i + 1}")
            document.save(source)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        identities = directory / "identities.json"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32),
                   V18_IDENTITIES=str(identities))
        app = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated Studio toolbar server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated Studio toolbar server did not start")
            token = json.loads(identities.read_text(encoding="utf-8"))["user"]
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context()
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base}])
                page = context.new_page()
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10'", timeout=30000)
                with page.expect_response("**/api/studio/page/delete", timeout=30000) as response:
                    page.locator("#editor-delete-page-btn").click()
                    page.locator("dialog.app-confirm-dialog .app-confirm-accept").click()
                assert response.value.status == 200
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '9'", timeout=30000)
                body_text = await_body_text(page)
                assert "Cannot delete all pages" not in body_text
                evidence = {"before": 10, "after": 9, "delete_status": response.value.status,
                            "bogus_last_page_error": False}
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
        out = Path(__file__).with_name("browser-studio-toolbar-delete.json")
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))


def await_body_text(page) -> str:
    return page.locator("body").inner_text()


if __name__ == "__main__":
    main()
