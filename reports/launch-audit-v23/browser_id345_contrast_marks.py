"""Chromium verifies custom colour/background preview and real watermark/page-number downloads."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import base64
from playwright.sync_api import sync_playwright

OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8765"
results = []
with TemporaryDirectory(prefix="paperplane-id345-") as temp:
    source = Path(temp) / "dark-page.pdf"
    with fitz.open() as document:
        page = document.new_page()
        page.draw_rect(page.rect, color=(0.08, 0.08, 0.08), fill=(0.08, 0.08, 0.08))
        page.insert_text((72, 90), "DARK PAGE SOURCE MARKER", color=(1, 1, 1))
        document.save(source)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
            page = context.new_page()
            errors = []
            page.on("pageerror", lambda error: errors.append(str(error)))
            for slug, operation, marker in (("watermark-pdf", "watermark", "DARK REPORT"), ("add-page-numbers-to-pdf", "page_numbers", "Page 1 of 1"), ("sign-pdf", "sign", "Audit Signer")):
                response = page.goto(f"{BASE}/{slug}", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#file-input").set_input_files(str(source))
                color_selector = "#signature_color" if operation == "sign" else "#mark_color"
                page.locator(color_selector).fill("#ff0000")
                page.locator("#mark_background").select_option("dark")
                preview = page.locator("#mark_preview")
                assert preview.is_visible() and "Mostly dark" not in preview.inner_text()
                assert "dark page background" in preview.inner_text()
                assert "#ff0000" in preview.evaluate("e => getComputedStyle(e).getPropertyValue('--mark-color').trim()")
                request_options = {"text": marker, "signature": marker, "signer_name": marker, "format": "Page {n} of {total}", "mark_color": "#ff0000", "signature_color": "#ff0000", "mark_background": "dark"}
                response_payload = page.evaluate("""async c => {
                  const raw = atob(c.data), bytes = new Uint8Array(raw.length);
                  for (let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
                  const form = new FormData(); form.append('operation', c.operation);
                  form.append('options', JSON.stringify(c.options));
                  form.append('files', new File([bytes], c.name, {type:'application/pdf'}));
                  let response = await fetch('/api/jobs', {method:'POST', body:form});
                  let job = await response.json();
                  if (!response.ok) throw new Error(JSON.stringify(job));
                  let state;
                  for (let i=0;i<120;i++) {
                    await new Promise(resolve=>setTimeout(resolve,250));
                    response = await fetch(job.status_url); state = await response.json();
                    if (state.status==='completed') break;
                    if (state.status==='failed') throw new Error(state.error);
                  }
                  if (state?.status!=='completed') throw new Error('job timed out');
                  response = await fetch(job.download_url); if (!response.ok) throw new Error(`download ${response.status}`);
                  const data = new Uint8Array(await response.arrayBuffer()); let binary='';
                  for(let i=0;i<data.length;i+=8192) binary += String.fromCharCode(...data.subarray(i,i+8192));
                  return {name:state.output_name,data:btoa(binary)};
                }""", {"operation": operation, "options": request_options, "name": source.name, "data": base64.b64encode(source.read_bytes()).decode("ascii")})
                output = OUT / f"id345-{operation}-round{round_number}.pdf"
                output.write_bytes(base64.b64decode(response_payload["data"]))
                with fitz.open(output) as result:
                    extracted = result[0].get_text()
                    expected = marker if operation in {"watermark", "sign"} else "Page 1 of 1"
                    assert expected in extracted, extracted
                    spans = [span for span in result[0].get_texttrace() if expected in "".join(chr(char[0]) for char in span["chars"])]
                    assert spans and spans[0]["color"] == (1.0, 0.0, 0.0), spans
                results.append({"round": round_number, "operation": operation, "http": response.status, "download": output.name, "pdf_text": extracted.strip(), "red_mark": True})
            assert not errors, errors
            context.close()
        browser.close()
(OUT / "browser-id345-contrast-marks.json").write_text(json.dumps({"base": BASE, "rounds": results}, indent=2), encoding="utf-8")
print(json.dumps({"rounds": len(results), "results": results}, ensure_ascii=False))
