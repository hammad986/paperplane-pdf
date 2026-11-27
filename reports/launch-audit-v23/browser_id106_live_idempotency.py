"""Verify one guest job is replayed on live with a repeated idempotency key."""
from __future__ import annotations

import asyncio
import fitz
import json
from pathlib import Path
import secrets
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
OUT = ROOT / "reports" / "launch-audit-v23" / "browser-id106-live-idempotency-2026-11-19.json"
MARKER = "LIVE-IDEMPOTENCY-SINGLE-JOB-CHECK"


async def main() -> dict:
    with fitz.open() as document:
        page = document.new_page(width=612, height=792)
        page.insert_text((72, 90), MARKER)
        source_bytes = list(document.tobytes())
    key = "live-v23-" + secrets.token_urlsafe(24)
    page_errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        context = await browser.new_context(viewport={"width": 1366, "height": 900})
        page = await context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        home = await page.goto(BASE + "/merge-pdf", wait_until="domcontentloaded", timeout=45000)
        result = await page.evaluate("""async ({bytes, marker, key}) => {
          const submit=async name=>{
            const form=new FormData();
            form.append('operation','merge');
            form.append('options','{}');
            form.append('files',new Blob([new Uint8Array(bytes)],{type:'application/pdf'}),name);
            const r=await fetch('/api/jobs',{method:'POST',body:form,credentials:'same-origin',headers:{'Idempotency-Key':key}});
            let body={}; try {body=await r.json()} catch {}
            return {status:r.status,body};
          };
          const first=await submit('id106-live-source.pdf');
          if(first.status!==202) return {first_status:first.status,first_error:first.body.detail||null};
          const second=await submit('id106-live-source.pdf');
          const same_job=Boolean(first.body.job_id&&first.body.job_id===second.body.job_id);
          const status_url=first.body.status_url||`/api/jobs/${first.body.job_id}`;
          const download_url=first.body.download_url||`/api/jobs/${first.body.job_id}/download`;
          const end=Date.now()+90000; let job=null;
          while(Date.now()<end){
            const r=await fetch(status_url,{credentials:'same-origin'});
            if(!r.ok) return {first_status:first.status,second_status:second.status,same_job,
              idempotent:Boolean(second.body.idempotent),status_http:r.status,completed:false};
            job=await r.json(); if(job.status==='completed'||job.status==='failed') break;
            await new Promise(resolve=>setTimeout(resolve,500));
          }
          if(!job||job.status!=='completed') return {first_status:first.status,second_status:second.status,
            same_job,idempotent:Boolean(second.body.idempotent),completed:false,job_status:job?.status||null};
          const download=await fetch(download_url,{credentials:'same-origin'});
          const output=download.ok?Array.from(new Uint8Array(await download.arrayBuffer())):[];
          return {first_status:first.status,second_status:second.status,same_job,
            idempotent:Boolean(second.body.idempotent),completed:true,download_status:download.status,
            output_bytes:output};
        }""", {"bytes": source_bytes, "marker": MARKER, "key": key})
        await context.close()
        await browser.close()
    output_bytes = bytes(result.pop("output_bytes", []))
    result["download_bytes"] = len(output_bytes)
    result["pdf_signature"] = output_bytes.startswith(b"%PDF-")
    result["pages"] = None
    result["content_checked"] = False
    if result.get("download_status") == 200 and result["pdf_signature"]:
        with fitz.open(stream=output_bytes, filetype="pdf") as output:
            result["pages"] = output.page_count
            result["content_checked"] = output.page_count == 1 and MARKER in output[0].get_text()
    evidence = {"site": BASE, "source": "generated one-page guest PDF; idempotency key and job id redacted",
                "route_status": home.status if home else None, "result": result,
                "page_errors": page_errors}
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not (result.get("first_status") == 202 and result.get("second_status") == 200
            and result.get("same_job") and result.get("idempotent") and result.get("completed")
            and result.get("download_status") == 200 and result.get("content_checked")
            and not page_errors):
        raise SystemExit(1)
    return evidence


if __name__ == "__main__":
    asyncio.run(main())
