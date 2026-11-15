"""Two local Chromium content-checked passes per public Drive/direct PDF input."""
from __future__ import annotations

import base64
import fitz
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
INPUTS = {
    "drive_owner_exact": "https://drive.google.com/file/d/1dAovOT7FCFaur33cX5_M6SsL6EvZT9rS/view",
    "drive": "https://drive.google.com/file/d/1d1JfUBhXbuGnQEEjnzPClMkvfdb8DVXS/view?usp=sharing",
    "direct": "https://www.w3.org/WAI/ER/tests/xhtml/testsuite/resources/pdf/dummy.pdf",
    "direct_corrected": "https://www.w3.org/WAI/ER/tests/xhtml/testfiles/resources/pdf/dummy.pdf",
}
BOOTSTRAP = r'''
import persistence, server, uvicorn
persistence.init_db()
uvicorn.run(server.app, host="127.0.0.1", port=int(__import__("os").environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-cloud-import-v18-") as temp:
        directory = Path(temp)
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
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Isolated Cloud Import server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated Cloud Import server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(base, wait_until="domcontentloaded")
                results = page.evaluate("""async ({inputs}) => {
                  const output = [];
                  for (const [name, url] of Object.entries(inputs)) {
                    for (let pass = 1; pass <= 2; pass++) {
                      const body = new FormData(); body.append('file_url', url);
                      const response = await fetch('/api/cloud/sync', {method:'POST', body});
                      const data = await response.json();
                      output.push({name, pass, status:response.status, data});
                    }
                  }
                  return output;
                }""", {"inputs": INPUTS})
                browser.close()
            evidence = []
            for item in results:
                result = {"name": item["name"], "pass": item["pass"], "status": item["status"]}
                if item["status"] == 200:
                    imported = item["data"]
                    raw = base64.b64decode(imported["data_url"].split(",", 1)[1])
                    pdf = directory / f"{item['name']}-{item['pass']}.pdf"
                    pdf.write_bytes(raw)
                    with fitz.open(pdf) as document:
                        assert len(document) == imported["page_count"] >= 1
                        result.update(filename=imported["filename"], bytes=len(raw), pages=len(document),
                                      first_page_text=document[0].get_text()[:100])
                else:
                    result["error"] = item["data"].get("detail")
                evidence.append(result)
            report = Path(__file__).with_name("browser-cloud-import-retries.json")
            report.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
            print(json.dumps(evidence, indent=2, ensure_ascii=True))
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()


if __name__ == "__main__":
    main()
