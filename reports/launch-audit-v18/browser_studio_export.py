"""Two consecutive local Studio export runs with downloaded PDF inspection."""
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
email = "export-probe-" + secrets.token_hex(6) + "@example.invalid"
password = secrets.token_urlsafe(30)
user_id = persistence.create_user(email, password)
persistence.set_user_tier(user_id, "student_pro")
tokens = {"user": persistence.create_session(email, password)["token"]}
Path(os.environ["V18_IDENTITIES"]).write_text(json.dumps(tokens))
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-studio-export-v18-") as temp:
        directory = Path(temp)
        source = directory / "studio-source.pdf"
        with fitz.open() as document:
            for number in range(1, 11):
                page = document.new_page()
                page.insert_text((72, 72), f"V18 Studio export source page {number:02d}")
            document.save(source)

        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        identities_path = directory / "identities.json"
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32),
                   V18_IDENTITIES=str(identities_path))
        app = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        result = []
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated Studio test server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated Studio test server did not start")

            token = json.loads(identities_path.read_text(encoding="utf-8"))["user"]
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                context = browser.new_context(accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10'", timeout=30000)
                page.locator("#btn-mode-organize").click()
                page.locator('.organizer-thumb-card[data-page="2"] .thumb-checkbox-label').click()
                with page.expect_response("**/api/studio/pages/reorder", timeout=30000) as reorder:
                    page.locator("#batch-move-up-btn").click()
                assert reorder.value.status == 200
                page.get_by_text("Pages reordered successfully.", exact=True).wait_for(timeout=30000)

                for run in (1, 2):
                    with page.expect_download(timeout=45000) as download:
                        page.locator("#save-studio-btn").click()
                    path = directory / f"export-{run}.pdf"
                    download.value.save_as(path)
                    with fitz.open(path) as output:
                        texts = [item.get_text() for item in output]
                        assert output.page_count == 10
                        assert "page 02" in texts[0] and "page 01" in texts[1]
                        assert all(f"page {number:02d}" in texts[number - 1] for number in range(3, 11))
                    result.append({"run": run, "download": download.value.suggested_filename,
                                   "pages": 10, "first_two_pages_reordered": True,
                                   "page_text_markers_checked": 10})
                    page.get_by_text("Edited PDF exported successfully!", exact=True).wait_for(timeout=15000)
                assert not errors, errors
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=10)
            except subprocess.TimeoutExpired:
                app.kill()
                app.wait()

        evidence = ROOT / "reports" / "launch-audit-v18" / "browser-studio-export.json"
        evidence.write_text(json.dumps({"rounds": result, "page_errors": []}, indent=2), encoding="utf-8")
        print(json.dumps({"exports": len(result), "evidence": str(evidence)}))


if __name__ == "__main__":
    main()
