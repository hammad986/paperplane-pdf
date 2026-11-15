"""Focused Chromium regression checks for new v20 server-side fixes."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import zipfile

import fitz
import openpyxl
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
BOOTSTRAP = r'''import os, uvicorn, json, secrets
from pathlib import Path
import persistence, server
email = "v20-browser-" + secrets.token_hex(5) + "@example.invalid"
password = secrets.token_urlsafe(24)
user_id = persistence.create_user(email, password)
persistence.set_user_tier(user_id, "student_pro")
token = persistence.create_session(email, password)["token"]
Path(os.environ["V20_BROWSER_TOKEN_PATH"]).write_text(token)
uvicorn.run(server.app, host="127.0.0.1", port=int(os.environ["PAPERPLANE_PORT"]), log_level="error")
'''


def make_pdf(path: Path, labels: list[str]) -> None:
    doc = fitz.open()
    for label in labels:
        page = doc.new_page()
        page.insert_text((72, 72), label)
    doc.save(path)
    doc.close()


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="paperplane-v20-browser-") as temp:
        directory = Path(temp)
        port_socket = socket.socket()
        port_socket.bind(("127.0.0.1", 0))
        port = port_socket.getsockname()[1]
        port_socket.close()
        env = {key: value for key, value in os.environ.items()
               if not key.upper().startswith(("PAPERPLANE_", "CASHFREE_", "OPENAI_", "GEMINI_", "BLUESMINDS_", "ADMIN_"))}
        env.update(PAPERPLANE_SKIP_DOTENV="1", PAPERPLANE_ENV="development",
                   PAPERPLANE_DATA_DIR=str(directory / "data"), PAPERPLANE_PORT=str(port),
                   PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(48), PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(32),
                   V20_BROWSER_TOKEN_PATH=str(directory / "token.txt"))
        proc = subprocess.Popen([sys.executable, "-c", BOOTSTRAP], cwd=ROOT, env=env,
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        base = f"http://127.0.0.1:{port}"
        try:
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    if proc.poll() is not None:
                        raise RuntimeError("Local v20 browser server exited during startup")
                    time.sleep(.2)
            split_source = directory / "split.pdf"
            make_pdf(split_source, [f"Source page {i}" for i in range(1, 5)])
            annotated_source = directory / "annotated.pdf"
            make_pdf(annotated_source, ["Comment target and visible annotation text"])
            doc = fitz.open(annotated_source)
            source_page = doc[0]
            annot = source_page.add_highlight_annot(fitz.Rect(72, 57, 230, 77))
            annot.set_info(content="Original note")
            doc.saveIncr()
            doc.close()
            columns_source = directory / "columns.pdf"
            doc = fitz.open()
            page = doc.new_page()
            for x, y, text in [(72, 72, "Item"), (240, 72, "Amount"), (72, 100, "Printer"), (240, 100, "$42.00")]:
                page.insert_text((x, y), text)
            doc.save(columns_source)
            doc.close()
            sparse_source = directory / "sparse.pdf"
            make_pdf(sparse_source, [f"Topic {i}" for i in range(1, 25)])
            large_source = directory / "five-megabyte.pdf"
            large_doc = fitz.open()
            for _ in range(4):
                pixels = os.urandom(1400 * 1400 * 3)
                image = Image.frombytes("RGB", (1400, 1400), pixels)
                jpeg = directory / f"page-{_}.jpg"
                image.save(jpeg, format="JPEG", quality=86)
                page = large_doc.new_page(width=612, height=792)
                page.insert_image(page.rect, filename=str(jpeg))
            large_doc.save(large_source, garbage=4, deflate=False)
            large_doc.close()
            large_bytes = large_source.stat().st_size

            def b64(path: Path) -> str:
                return base64.b64encode(path.read_bytes()).decode("ascii")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                page = browser.new_page()
                for _ in range(100):
                    if (directory / "token.txt").exists():
                        break
                    time.sleep(.05)
                page.context.add_cookies([{"name": "paperplane_token", "value": (directory / "token.txt").read_text(), "url": base}])
                page.goto(base, wait_until="domcontentloaded")
                page.wait_for_load_state("networkidle")
                delayed_context = browser.new_context()
                delayed_context.add_cookies([{"name": "paperplane_token", "value": (directory / "token.txt").read_text(), "url": base}])
                delayed_page = delayed_context.new_page()
                delayed_page.add_init_script("""(() => {
                  const original = window.fetch.bind(window);
                  window.fetch = (input, init) => String(input).includes('/api/auth/me')
                    ? new Promise(resolve => setTimeout(() => resolve(original(input, init)), 1200))
                    : original(input, init);
                })();""")
                delayed_page.goto(base + "/settings", wait_until="domcontentloaded")
                delayed_page.wait_for_function("document.body.classList.contains('auth-pending')")
                pending_text = delayed_page.locator("body").inner_text()
                assert "Guest Explorer" not in pending_text
                assert "Sign In" not in pending_text and "Create Account" not in pending_text
                delayed_page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                assert "v20-browser-" in delayed_page.locator("body").inner_text()
                delayed_context.close()
                result = page.evaluate("""async ({cases}) => {
                  async function job(c) {
                    const form = new FormData(); form.append('operation', c.op); form.append('options', JSON.stringify(c.options || {}));
                    const bytes = Uint8Array.from(atob(c.pdf), x => x.charCodeAt(0));
                    form.append('files', new File([bytes], c.filename, {type:'application/pdf'}));
                    const create = await fetch('/api/jobs', {method:'POST', body:form});
                    if (!create.ok) throw new Error(c.op + ' create ' + create.status + ': ' + await create.text());
                    const info = await create.json();
                    let state;
                    for (let i=0; i<300; i++) {
                      await new Promise(r=>setTimeout(r,200));
                      state = await (await fetch(info.status_url)).json();
                      if (state.status === 'completed') break;
                      if (state.status === 'failed') throw new Error(c.op + ' failed: ' + state.error);
                    }
                    if (state?.status !== 'completed') throw new Error(c.op + ' timed out');
                    const response = await fetch(info.download_url);
                    if (!response.ok) throw new Error(c.op + ' download ' + response.status);
                    const arr = new Uint8Array(await response.arrayBuffer());
                    let binary=''; for (const byte of arr) binary += String.fromCharCode(byte);
                    return {name:state.output_name, bytes:btoa(binary)};
                  }
                  const status = await (await fetch('/api/billing/status')).json();
                  const outputs = {};
                  for (const c of cases) outputs[c.key] = await job(c);
                  const chatForm = new FormData(); chatForm.append('question','What is this document about?');
                  const sparse = Uint8Array.from(atob(cases.find(c=>c.key==='sparse').pdf), x=>x.charCodeAt(0));
                  chatForm.append('file', new File([sparse], 'sparse.pdf', {type:'application/pdf'}));
                  const chat = await (await fetch('/api/ai/chat', {method:'POST', body:chatForm})).json();
                  return {status, outputs, chat};
                }""", {"cases":[
                    {"key":"split","op":"split","filename":"split.pdf","pdf":b64(split_source),"options":{"pages":"1-2"}},
                    {"key":"split_one","op":"split","filename":"split.pdf","pdf":b64(split_source),"options":{"pages":"1"}},
                    {"key":"flatten","op":"flatten","filename":"annotated.pdf","pdf":b64(annotated_source)},
                    {"key":"word","op":"pdf_to_word","filename":"columns.pdf","pdf":b64(columns_source)},
                    {"key":"annotate","op":"annotate","filename":"columns.pdf","pdf":b64(columns_source),"options":{"annot_type":"highlight","page":1,"text":"Printer","content":"Browser review note"}},
                    {"key":"excel","op":"pdf_to_excel","filename":"columns.pdf","pdf":b64(columns_source)},
                    {"key":"sparse","op":"merge","filename":"sparse.pdf","pdf":b64(sparse_source)},
                    {"key":"compress1","op":"compress","filename":"five-megabyte.pdf","pdf":b64(large_source),"options":{"preset":"balanced"}},
                    {"key":"compress2","op":"compress","filename":"five-megabyte.pdf","pdf":b64(large_source),"options":{"preset":"balanced"}},
                    {"key":"watermark1","op":"watermark","filename":"five-megabyte.pdf","pdf":b64(large_source),"options":{"text":"V20 WATERMARK CHECK"}},
                    {"key":"watermark2","op":"watermark","filename":"five-megabyte.pdf","pdf":b64(large_source),"options":{"text":"V20 WATERMARK CHECK"}},
                    {"key":"numbers1","op":"page_numbers","filename":"five-megabyte.pdf","pdf":b64(large_source),"options":{"format":"page_of_total","start_number":1}},
                    {"key":"numbers2","op":"page_numbers","filename":"five-megabyte.pdf","pdf":b64(large_source),"options":{"format":"page_of_total","start_number":1}}
                ]})
                browser.close()

            assert "cashfree_environment" not in result["status"] and "cashfree_configured" not in result["status"]
            split_output = directory / "split-result.pdf"
            split_output.write_bytes(base64.b64decode(result["outputs"]["split"]["bytes"]))
            with fitz.open(split_output) as split_doc:
                assert split_doc.page_count == 2 and "Source page 1" in split_doc[0].get_text() and "Source page 2" in split_doc[1].get_text()
            split_one = directory / "split-one.pdf"
            split_one.write_bytes(base64.b64decode(result["outputs"]["split_one"]["bytes"]))
            with fitz.open(split_one) as one_doc:
                assert one_doc.page_count == 1 and "Source page 1" in one_doc[0].get_text()
            flattened = directory / "flattened.pdf"
            flattened.write_bytes(base64.b64decode(result["outputs"]["flatten"]["bytes"]))
            with fitz.open(flattened) as flat_doc:
                assert list(flat_doc[0].annots() or []) == []
            annotated = directory / "comment.pdf"
            annotated.write_bytes(base64.b64decode(result["outputs"]["annotate"]["bytes"]))
            with fitz.open(annotated) as annotate_doc:
                assert next(annotate_doc[0].annots()).info["content"] == "Browser review note"
            workbook = directory / "columns.xlsx"
            workbook.write_bytes(base64.b64decode(result["outputs"]["excel"]["bytes"]))
            sheet = openpyxl.load_workbook(workbook, data_only=True).active
            assert [sheet.cell(1, i).value for i in (1, 2)] == ["Item", "Amount"]
            assert [sheet.cell(2, i).value for i in (1, 2)] == ["Printer", "$42.00"]
            docx = directory / "editable.docx"
            docx.write_bytes(base64.b64decode(result["outputs"]["word"]["bytes"]))
            with zipfile.ZipFile(docx) as archive:
                xml = archive.read("word/document.xml").decode("utf-8")
                assert "Item" in xml and "Amount" in xml and "Printer" in xml
                assert "word/media/" not in " ".join(archive.namelist())
            assert "No relevant information found" not in result["chat"]["answer"]
            assert large_bytes >= 5_000_000, f"generated fixture is only {large_bytes} bytes"
            for key in ("compress1", "compress2"):
                compressed = directory / f"{key}.pdf"
                compressed.write_bytes(base64.b64decode(result["outputs"][key]["bytes"]))
                with fitz.open(compressed) as compressed_doc:
                    assert compressed_doc.page_count == 4
                    assert compressed_doc[0].get_images()
            for key in ("watermark1", "watermark2"):
                marked = directory / f"{key}.pdf"
                marked.write_bytes(base64.b64decode(result["outputs"][key]["bytes"]))
                with fitz.open(marked) as marked_doc:
                    assert marked_doc.page_count == 4
                    assert "V20 WATERMARK CHECK" in marked_doc[0].get_text()
            for key in ("numbers1", "numbers2"):
                numbered = directory / f"{key}.pdf"
                numbered.write_bytes(base64.b64decode(result["outputs"][key]["bytes"]))
                with fitz.open(numbered) as numbered_doc:
                    assert numbered_doc.page_count == 4
                    assert "Page 1 of 4" in numbered_doc[0].get_text()
            print("ID 292: browser split download has only requested pages 1-2")
            print("ID 293: browser flatten download has no active annotation records")
            print("ID 295: browser PDF-to-Word download contains editable text without raster page images")
            print("ID 298: browser annotation download preserves the comment in annotation Contents")
            print("ID 299: browser billing response omits provider environment/configuration details")
            print("ID 301: sparse 24-page browser chat returns a useful subject/sample response")
            print("ID 302: browser PDF-to-Excel download separates positional columns into cells")
            print(f"ID 294: two 5+ MB image-heavy runs each passed for compress, watermark and page numbers (input {large_bytes} bytes)")
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()


if __name__ == "__main__":
    main()
