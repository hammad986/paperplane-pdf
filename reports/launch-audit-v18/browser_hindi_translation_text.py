"""Controlled local Chromium translation run verifies Hindi visual and text output."""
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
import ai_engine, persistence, server, uvicorn
persistence.init_db()
ai_engine.AI_KILL_SWITCH = False
ai_engine._current_bluesminds_api_key = lambda: "controlled-test-key"
ai_engine._translate_text_batch = lambda batch, language, **kwargs: {
    i: ("Prueba traducida" if str(language).lower().startswith("es") else "प्लेन टेस्ट")
    for i, _ in batch
}
uvicorn.run(server.app, host="127.0.0.1", port=int(__import__("os").environ["PAPERPLANE_PORT"]), log_level="error")
'''


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-hindi-translation-v18-") as temp:
        directory = Path(temp)
        source = directory / "english-source.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 100), "Sample English text for translation")
            document.save(source)
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
                        raise RuntimeError("Isolated Hindi translation server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated Hindi translation server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(base, wait_until="domcontentloaded")
                encoded = base64.b64encode(source.read_bytes()).decode("ascii")
                responses = page.evaluate("""async ({pdfBytes}) => {
                  const bytes = Uint8Array.from(atob(pdfBytes), c => c.charCodeAt(0));
                  const body = new FormData();
                  const toBase64 = bytes => { let value = ''; for (let i=0; i<bytes.length; i+=0x8000) value += String.fromCharCode(...bytes.subarray(i,i+0x8000)); return btoa(value); };
                  const results = [];
                  for (const language of ['es', 'hi', 'es', 'hi']) {
                    const body = new FormData();
                    body.append('target_language', language);
                    body.append('file', new Blob([bytes], {type:'application/pdf'}), 'english-source.pdf');
                    const result = await fetch('/api/ai/translate', {method:'POST', body});
                    results.push({language, status:result.status, mode:result.headers.get('X-Paperplane-Translation-Mode'), pdf:toBase64(new Uint8Array(await result.arrayBuffer()))});
                  }
                  return results;
                }""", {"pdfBytes": encoded})
                browser.close()
            evidence = []
            for index, response in enumerate(responses, 1):
                assert response["status"] == 200, response
                output = directory / f"translated-{index}.pdf"
                output.write_bytes(base64.b64decode(response["pdf"]))
                with fitz.open(output) as translated:
                    text = translated[0].get_text()
                    expected = ("Prueba traducida" if response["language"] == "es" else "प्लेन टेस्ट")
                    assert expected in text, repr(text)
                    pix = translated[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
                    assert any(pix.samples)
                evidence.append({"language": response["language"], "http_status": response["status"],
                                 "translation_mode": response["mode"], "extracted_text": text,
                                 "rendered_page_has_content": True})
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()
        report = Path(__file__).with_name("browser-hindi-translation-text.json")
        report.write_text(json.dumps(evidence, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(evidence, indent=2, ensure_ascii=True))


if __name__ == "__main__":
    main()
