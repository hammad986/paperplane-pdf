"""Browser regression: HTML-to-PDF explains that it accepts URLs, not HTML uploads."""
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

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = r'''
import persistence, server, uvicorn
persistence.init_db()
uvicorn.run(server.app, host="127.0.0.1", port=int(__import__("os").environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-html-upload-v18-") as temp:
        directory = Path(temp)
        source = directory / "not-a-url.html"
        source.write_text("<html><body>upload must be rejected</body></html>", encoding="utf-8")
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32))
        app = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        evidence = {"url": base + "/html-to-pdf", "upload": source.name}
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated HTML tool server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated HTML tool server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(base + "/html-to-pdf", wait_until="domcontentloaded")
                page.wait_for_function("window.location.pathname.includes('html-to-pdf') && document.querySelector('#file-input')")
                page.locator("#file-input").set_input_files(str(source))
                page.get_by_text("HTML to PDF uses a public URL", exact=False).wait_for(timeout=5000)
                assert page.locator("#file-list").inner_text().strip() == ""
                assert page.locator("#run-button").is_disabled()
                evidence["result"] = "upload rejected with URL-required explanation; no file staged and convert stays disabled"
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
        out = Path(__file__).with_name("browser-html-upload-rejection.json")
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
