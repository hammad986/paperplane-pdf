"""Local Chromium check for selectable text in Edit PDF and Page Numbers outputs."""
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
    with tempfile.TemporaryDirectory(prefix="paperplane-unicode-layer-v18-") as temp:
        directory = Path(temp)
        source_path = directory / "one-page.pdf"
        with fitz.open() as document:
            page = document.new_page()
            page.insert_text((72, 72), "Source body")
            document.save(source_path)
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
                        raise RuntimeError("Isolated Unicode text server exited")
                    time.sleep(.1)
            else:
                raise RuntimeError("Isolated Unicode text server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(base, wait_until="domcontentloaded")
                outputs = page.evaluate("""async ({pdfBytes}) => {
                  const source = Uint8Array.from(atob(pdfBytes), c => c.charCodeAt(0));
                  const editedForm = new FormData();
                  editedForm.append('file', new Blob([source], {type:'application/pdf'}), 'one-page.pdf');
                  editedForm.append('edits', JSON.stringify([{type:'text', page:1, docX:72, docY:120, docW:250, docH:35, text:'Searchable Studio Text', fontSize:18, bold:true}]));
                  const editedResponse = await fetch('/api/studio/apply-edits', {method:'POST', body:editedForm});
                  const edited = new Uint8Array(await editedResponse.arrayBuffer());
                  const jobForm = new FormData();
                  jobForm.append('operation', 'page_numbers');
                  jobForm.append('options', JSON.stringify({format:'page_of_total'}));
                  jobForm.append('files', new Blob([source], {type:'application/pdf'}), 'one-page.pdf');
                  const created = await fetch('/api/jobs', {method:'POST', body:jobForm});
                  const job = await created.json();
                  let status;
                  for (let i=0; i<100; i++) {
                    status = await (await fetch(job.status_url)).json();
                    if (status.status === 'completed' || status.status === 'failed') break;
                    await new Promise(resolve => setTimeout(resolve, 100));
                  }
                  let numbered = new Uint8Array();
                  if (status.status === 'completed') numbered = new Uint8Array(await (await fetch(job.download_url)).arrayBuffer());
                  const toBase64 = bytes => { let value = ''; for (let i = 0; i < bytes.length; i += 0x8000) value += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return btoa(value); };
                  return {editStatus:editedResponse.status, edit:toBase64(edited), jobStatus:created.status,
                    pageNumberStatus:status.status, numbered:toBase64(numbered)};
                }""", {"pdfBytes": base64.b64encode(source_path.read_bytes()).decode("ascii")})
                browser.close()
            assert outputs["editStatus"] == 200
            assert outputs["jobStatus"] == 202 and outputs["pageNumberStatus"] == "completed"
            edit_path = directory / "edited.pdf"
            page_path = directory / "numbered.pdf"
            edit_path.write_bytes(base64.b64decode(outputs["edit"]))
            page_path.write_bytes(base64.b64decode(outputs["numbered"]))
            for path, expected in ((edit_path, "Searchable Studio Text"), (page_path, "Page 1 of 1")):
                with fitz.open(path) as output:
                    extracted = output[0].get_text().replace("\u00a0", " ")
                    assert expected in extracted
                    assert any(output.xref_get_key(font[0], "ToUnicode")[0] != "null"
                               for font in output.get_page_fonts(0, full=True))
            evidence = {"studio_edit": "downloaded PDF contains selectable searchable text with ToUnicode map",
                        "page_numbers": "downloaded PDF contains selectable page label with ToUnicode map"}
            report = Path(__file__).with_name("browser-unicode-text-layer.json")
            report.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
            print(json.dumps(evidence, indent=2))
        finally:
            app.terminate()
            try:
                app.wait(timeout=5)
            except subprocess.TimeoutExpired:
                app.kill()


if __name__ == "__main__":
    main()
