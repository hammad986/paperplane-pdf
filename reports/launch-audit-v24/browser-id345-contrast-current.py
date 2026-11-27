from __future__ import annotations

import base64
import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def fixture(path: Path) -> None:
    with fitz.open() as doc:
        page = doc.new_page()
        page.draw_rect(page.rect, color=(0.08, 0.08, 0.08), fill=(0.08, 0.08, 0.08))
        page.insert_text((72, 90), "DARK PAGE SOURCE MARKER", color=(1, 1, 1))
        doc.save(path)


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id345-") as temp:
        root = Path(temp)
        source = root / "dark-page.pdf"
        fixture(source)
        app, base, _ = helper.start_server(root / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                payload = base64.b64encode(source.read_bytes()).decode("ascii")
                for round_no in (1, 2):
                    for slug, operation, marker in (("watermark-pdf", "watermark", "DARK REPORT"),
                                                     ("add-page-numbers-to-pdf", "page_numbers", "Page 1 of 1"),
                                                     ("sign-pdf", "sign", "Audit Signer")):
                        response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded")
                        assert response and response.status == 200
                        page.locator("#file-input").set_input_files(str(source))
                        color_selector = "#signature_color" if operation == "sign" else "#mark_color"
                        page.locator(color_selector).fill("#ff0000")
                        page.locator("#mark_background").select_option("dark")
                        preview = page.locator("#mark_preview")
                        assert preview.is_visible() and "mostly dark background" in preview.inner_text()
                        assert preview.evaluate("e => getComputedStyle(e).getPropertyValue('--mark-color').trim()") == "#ff0000"
                        mark_preview = page.locator("#mark_preview .mark-preview-mark")
                        expected_class = {"watermark": "is-watermark", "page_numbers": "footer-center", "sign": "is-signature"}[operation]
                        assert expected_class in mark_preview.get_attribute("class")
                        assert mark_preview.is_visible()
                        opts = {"text": marker, "signature": marker, "signer_name": marker,
                                "format": "Page {n} of {total}", "mark_color": "#ff0000",
                                "signature_color": "#ff0000", "mark_background": "dark"}
                        result = page.evaluate("""async c => {
                          const raw=atob(c.data), bytes=Uint8Array.from(raw, x=>x.charCodeAt(0));
                          const form=new FormData(); form.append('operation',c.operation);
                          form.append('options',JSON.stringify(c.options));
                          form.append('files',new File([bytes],c.name,{type:'application/pdf'}));
                          let r=await fetch('/api/jobs',{method:'POST',body:form}), job=await r.json();
                          if(!r.ok) throw Error(JSON.stringify(job));
                          let state;
                          for(let i=0;i<240;i++){await new Promise(ok=>setTimeout(ok,250));r=await fetch(job.status_url);state=await r.json();if(state.status==='completed'||state.status==='failed')break;}
                          if(state.status!=='completed') throw Error(JSON.stringify(state));
                          r=await fetch(job.download_url); if(!r.ok) throw Error('download '+r.status);
                          const b=new Uint8Array(await r.arrayBuffer());let s='';for(let i=0;i<b.length;i+=8192)s+=String.fromCharCode(...b.subarray(i,i+8192));return btoa(s);
                        }""", {"operation": operation, "options": opts, "name": source.name, "data": payload})
                        pdf_bytes = base64.b64decode(result)
                        with fitz.open(stream=pdf_bytes, filetype="pdf") as output:
                            text = output[0].get_text()
                            assert marker in text or (operation == "page_numbers" and "Page 1 of 1" in text), text
                            span = next(s for s in output[0].get_texttrace() if marker in "".join(chr(c[0]) for c in s["chars"]))
                            assert span["color"] == (1.0, 0.0, 0.0)
                            content_streams = [output.xref_stream(xref) or b""
                                               for xref in range(1, output.xref_length())]
                            content = b"\n".join(content_streams).replace(b"\r", b"")
                            assert b"2 Tr" in content, content[-3000:]  # PDF fill-plus-stroke text rendering mode
                        evidence["rounds"].append({"round": round_no, "operation": operation, "bytes": len(pdf_bytes),
                                                   "marker": marker, "red_fill": True, "fill_and_outline": True,
                                                   "preview": preview.inner_text()})
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = (len(evidence["rounds"]) == 6 and not evidence["page_errors"] and not evidence["console_errors"])
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id345-contrast-current.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
