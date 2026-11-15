"""Browser API smoke: metadata questions work in streamed and non-streamed chat."""
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
BOOTSTRAP = r'''
import persistence, server, uvicorn
persistence.init_db()
uvicorn.run(server.app, host="127.0.0.1", port=int(__import__("os").environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-chat-metadata-v18-") as temp:
        directory = Path(temp)
        pdf_path = directory / "four-page-metadata.pdf"
        with fitz.open() as document:
            for i in range(4):
                page = document.new_page()
                page.insert_text((72, 72), f"Unrelated body passage {i + 1}")
            document.set_metadata({"title": "Quarterly Results"})
            document.save(pdf_path)
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
                        raise RuntimeError("Isolated metadata chat server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated metadata chat server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(base, wait_until="domcontentloaded")
                evidence = page.evaluate("""async ({pdfBytes}) => {
                  const bytes = Uint8Array.from(atob(pdfBytes), c => c.charCodeAt(0));
                  async function ask(path) {
                    const body = new FormData();
                    body.append('question', 'How many pages does this document have?');
                    body.append('file', new Blob([bytes], {type:'application/pdf'}), 'four-page-metadata.pdf');
                    const response = await fetch(path, {method:'POST', body, credentials:'same-origin'});
                    return {status: response.status, body: await response.text()};
                  }
                  return {standard: await ask('/api/ai/chat'), stream: await ask('/api/ai/chat/stream')};
                }""", {"pdfBytes": base64.b64encode(pdf_path.read_bytes()).decode("ascii")})
                assert evidence["standard"]["status"] == 200
                assert "4 pages" in evidence["standard"]["body"]
                assert evidence["stream"]["status"] == 200
                assert "4 pages" in evidence["stream"]["body"]
                browser.close()
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
        out = Path(__file__).with_name("browser-document-metadata-chat.json")
        out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
