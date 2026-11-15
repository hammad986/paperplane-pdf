"""Exercise the served citation dedupe helper in Chromium against a local app."""
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
    with tempfile.TemporaryDirectory(prefix="paperplane-citations-v18-") as temp:
        directory = Path(temp)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),
                   PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32))
        app = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated citation test server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated citation test server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"http://127.0.0.1:{port}", wait_until="networkidle")
                result = page.evaluate("""() => {
                  const pages = uniqueAiCitationPages([3, 3, 4, 3, 0, 'bad', '4']);
                  const citations = pages.map(page => aiPageCitationTag(page));
                  setClientSideMode(false);
                  updateButton();
                  const serverLabel = document.querySelector('#privacy-mode-label').textContent;
                  setClientSideMode(true);
                  updateButton();
                  const localLabel = document.querySelector('#privacy-mode-label').textContent;
                  openCloudModal();
                  const cloudModalCount = document.querySelectorAll('#cloud-modal').length;
                  const cloudModalTitle = document.querySelector('#cloud-modal h3').textContent;
                  const cloudSubmitText = document.querySelector('#cloud-submit-btn').textContent.trim();
                  const cloudEntrypointsShareHandler =
                    document.querySelector('#cloud-drop-btn').onclick === openCloudModal &&
                    document.querySelector('#topbar-cloud-btn').onclick === openCloudModal;
                  document.querySelector('#cloud-modal').hidden = true;
                  return {citations, serverLabel, localLabel, cloudModalCount, cloudModalTitle, cloudSubmitText,
                          cloudEntrypointsShareHandler};
                }""")
                browser.close()
            assert len(result["citations"]) == 2, result
            assert 'Page 3' in result["citations"][0] and 'Page 4' in result["citations"][1], result
            assert result["serverLabel"] == "Server Processing", result
            assert result["localLabel"] == "Local Processing", result
            assert result["cloudModalCount"] == 1, result
            assert result["cloudModalTitle"] == "Cloud Document Import", result
            assert "Fetch & Import Document" in result["cloudSubmitText"], result
            assert result["cloudEntrypointsShareHandler"], result
            evidence = {"served": True, "input": [3, 3, 4, 3, 0, "bad", "4"],
                        "rendered_unique_citations": ["Page 3", "Page 4"],
                        "processing_mode_labels": [result["localLabel"], result["serverLabel"]],
                        "cloud_import_dialog_count": result["cloudModalCount"],
                        "cloud_import_entrypoints_share_handler": result["cloudEntrypointsShareHandler"]}
            Path(__file__).with_name("browser-citation-dedupe.json").write_text(
                json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()


if __name__ == "__main__":
    main()
