"""Repeat the content-checked Watermark operation in fresh real-browser contexts."""
from __future__ import annotations

import base64
import json
from pathlib import Path
import time
import urllib.request

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = OUT / "watermark-stall-input.pdf"
BASE = "http://127.0.0.1:18501"
assert SOURCE.is_file()

source_bytes = SOURCE.read_bytes()
rounds = []
deadline = time.monotonic() + 60
while time.monotonic() < deadline:
    try:
        with urllib.request.urlopen(BASE + "/api/health", timeout=2) as health_response:
            if health_response.status == 200:
                break
    except Exception:
        time.sleep(0.5)
else:
    raise RuntimeError("current Docker image did not become healthy")

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    for round_no in range(1, 21):
        context = browser.new_context(accept_downloads=True)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        response = page.goto(BASE + "/", wait_until="domcontentloaded", timeout=30000)
        assert response and response.status == 200
        started = time.perf_counter()
        result = page.evaluate(
            """async c => {
              const raw = atob(c.data); const bytes = new Uint8Array(raw.length);
              for (let i=0;i<raw.length;i++) bytes[i]=raw.charCodeAt(i);
              const form = new FormData();
              form.append('operation','watermark');
              form.append('options',JSON.stringify({text:'AUDIT_WATERMARK'}));
              form.append('files',new File([bytes],'audit-sample.pdf',{type:'application/pdf'}));
              let response=await fetch('/api/jobs',{method:'POST',body:form});
              const submitted=await response.json();
              if(!response.ok) throw new Error(`submit ${response.status}`);
              const deadline=Date.now()+90000; let state;
              while(Date.now()<deadline){
                await new Promise(resolve=>setTimeout(resolve,250));
                response=await fetch(submitted.status_url);
                if(!response.ok) throw new Error(`status ${response.status}`);
                state=await response.json();
                if(state.status==='completed') break;
                if(state.status==='failed') throw new Error(`job failed: ${state.error||'unknown'}`);
              }
              if(state?.status!=='completed') throw new Error(`job timeout at ${state?.progress??'unknown'}%`);
              response=await fetch(submitted.download_url);
              if(!response.ok) throw new Error(`download ${response.status}`);
              const output=new Uint8Array(await response.arrayBuffer());
              let binary=''; for(let i=0;i<output.length;i+=8192) binary+=String.fromCharCode(...output.subarray(i,i+8192));
              return {bytes:btoa(binary),output_name:state.output_name};
            }""",
            {"data": base64.b64encode(source_bytes).decode("ascii")},
        )
        output = OUT / f"browser-id28-watermark-repeat-round{round_no}.pdf"
        output.write_bytes(base64.b64decode(result["bytes"]))
        with fitz.open(output) as document:
            text = [pdf_page.get_text() for pdf_page in document]
            assert len(document) == 2 and all("AUDIT_WATERMARK" in page_text for page_text in text)
        assert not errors, errors
        rounds.append({"round": round_no, "status": "completed", "http_status": response.status,
                       "elapsed_seconds": round(time.perf_counter() - started, 3),
                       "bytes": output.stat().st_size, "pages": len(text),
                       "marker_on_each_page": True, "page_errors": errors})
        print(json.dumps(rounds[-1]), flush=True)
        context.close()
    browser.close()

report = {"runtime": "current production-mode Docker image; fresh Chromium guest contexts; synthetic 2-page PDF",
          "rounds": rounds}
(OUT / "browser-id28-watermark-repeat.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"passed": len(rounds), "results": rounds}, indent=2))
