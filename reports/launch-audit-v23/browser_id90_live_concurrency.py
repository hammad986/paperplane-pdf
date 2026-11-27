"""Small read-only-output live check of four concurrent guest Merge jobs.

Uploads only a generated one-page PDF fixture. No account login or payment is used.
Job IDs, guest cookies, download URLs and PDF contents are not written to evidence.
"""
from __future__ import annotations

import asyncio
import fitz
import json
import os
from pathlib import Path
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "https://paperplane.qd.je"
COUNT = int(os.environ.get("PAPERPLANE_ID90_COUNT", "4"))
if not 1 <= COUNT <= 8:
    raise ValueError("PAPERPLANE_ID90_COUNT must be between 1 and 8")
OUT = ROOT / "reports" / "launch-audit-v23" / f"browser-id90-live-concurrency-{COUNT}-2026-11-20.json"


async def main() -> dict:
    source_bytes = []
    markers = []
    for index in range(COUNT):
        marker = f"LIVE-GUEST-MERGE-CONTENT-{index + 1:02d}"
        markers.append(marker)
        with fitz.open() as document:
            page = document.new_page(width=612, height=792)
            page.insert_text((72, 90), marker)
            source_bytes.append(list(document.tobytes()))

    page_errors: list[str] = []
    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="chrome", headless=True)
        contexts = [await browser.new_context(viewport={"width": 1366, "height": 900}) for _ in range(COUNT)]

        async def run_one(index: int, context) -> dict:
            page = await context.new_page()
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            home = await page.goto(BASE + "/merge-pdf", wait_until="domcontentloaded", timeout=45000)
            submitted = await page.evaluate("""async ({bytes, marker, index}) => {
              const form=new FormData();
              form.append('operation','merge');
              form.append('options','{}');
              form.append('files',new Blob([new Uint8Array(bytes)],{type:'application/pdf'}),`live-concurrency-${index+1}.pdf`);
              const response=await fetch('/api/jobs',{method:'POST',body:form,credentials:'same-origin'});
              let body={};
              try { body=await response.json(); } catch {}
              return {status:response.status,body};
            }""", {"bytes": source_bytes[index], "marker": markers[index], "index": index})
            if submitted["status"] != 202:
                return {"route_status": home.status if home else None,
                        "submit_status": submitted["status"], "accepted": False,
                        "error": str(submitted["body"].get("detail", ""))[:300]}

            body = submitted["body"]
            status_url = body.get("status_url") or f"/api/jobs/{body.get('job_id')}"
            deadline = asyncio.get_running_loop().time() + 120
            job = None
            while asyncio.get_running_loop().time() < deadline:
                job_response = await page.evaluate("""async url => {
                  const r=await fetch(url,{credentials:'same-origin'});
                  return {status:r.status,body:await r.json()};
                }""", status_url)
                if job_response["status"] != 200:
                    return {"route_status": home.status if home else None, "submit_status": 202,
                            "accepted": True, "status_http": job_response["status"], "completed": False}
                job = job_response["body"]
                if job.get("status") in {"completed", "failed"}:
                    break
                await page.wait_for_timeout(500)
            if not job or job.get("status") != "completed":
                return {"route_status": home.status if home else None, "submit_status": 202,
                        "accepted": True, "completed": False, "job_status": job.get("status") if job else None}

            download_url = body.get("download_url")
            if not download_url:
                download_url = f"/api/jobs/{body.get('job_id')}/download"
            downloaded = await page.evaluate("""async url => {
              const r=await fetch(url,{credentials:'same-origin'});
              if(!r.ok) return {status:r.status,bytes:[]};
              return {status:r.status,bytes:Array.from(new Uint8Array(await r.arrayBuffer()))};
            }""", download_url)
            output_bytes = bytes(downloaded.get("bytes", []))
            valid_pdf = output_bytes.startswith(b"%PDF-")
            content_checked = False
            pages = None
            if downloaded["status"] == 200 and valid_pdf:
                with fitz.open(stream=output_bytes, filetype="pdf") as output:
                    pages = output.page_count
                    text = "\n".join(item.get_text() for item in output)
                    content_checked = pages == 1 and markers[index] in text
            return {"route_status": home.status if home else None, "submit_status": 202,
                    "accepted": True, "completed": True, "download_status": downloaded["status"],
                    "pdf_signature": valid_pdf, "pages": pages, "content_checked": content_checked,
                    "download_bytes": len(output_bytes)}

        try:
            results = await asyncio.gather(*(run_one(index, ctx) for index, ctx in enumerate(contexts)))
        finally:
            for context in contexts:
                await context.close()
            await browser.close()

    return {"site": BASE, "test": f"{COUNT} concurrent guest Merge jobs using generated one-page PDFs",
            "guest_contexts": COUNT, "results": results, "page_errors": page_errors,
            "all_content_checked": len(results) == COUNT and all(item.get("content_checked") for item in results)}


if __name__ == "__main__":
    result = asyncio.run(main())
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
