"""Verify AI Docs citations, source name, active chat, and mobile step-chip reachability."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
import json
import socket
import subprocess
import sys
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix="paperplane-id86-ai-polish-") as temp:
    root = Path(temp)
    fixture = root / "annual-report.pdf"
    with fitz.open() as document:
        for number in range(1, 4):
            page = document.new_page()
            page.insert_text((72, 72), f"ID86 report page {number}; amount 42000")
        document.save(fixture)

    app, base, _ = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            if app.poll() is not None:
                raise RuntimeError(f"app exited with {app.returncode}")
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.15)

        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
                context.add_init_script("""(() => {
                  const original=window.fetch.bind(window);
                  window.fetch=(input,init={})=>{
                    let path='';try{path=new URL(typeof input==='string'?input:input.url,location.href).pathname}catch{}
                    if(path!=='/api/ai/chat/stream')return original(input,init);
                    const frames=[
                      ['stage',{stage:'Thinking…'}],['stage',{stage:'Extracting…'}],['stage',{stage:'Analysing…'}],
                      ['stage',{stage:'Searching…'}],['stage',{stage:'Generating…'}],
                      ['token',{text:'The total is 42000 [[Page 2]].'}],
                      ['done',{citations:[2],mode:'local_extraction'}]
                    ];
                    const encoder=new TextEncoder();
                    const body=new ReadableStream({async start(controller){for(const [event,data] of frames){controller.enqueue(encoder.encode(`event: ${event}\\ndata: ${JSON.stringify(data)}\\n\\n`));await new Promise(resolve=>setTimeout(resolve,160));}controller.close();}});
                    return Promise.resolve(new Response(body,{status:200,headers:{'Content-Type':'text/event-stream'}}));
                  };
                })();""")
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                response = page.goto(base + "/ai-intelligence", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#ai-empty-state").wait_for(state="visible", timeout=10000)
                empty_state = {"visible": page.locator("#ai-empty-state").is_visible(), "message": page.locator("#ai-empty-state .ai-empty-copy").inner_text()}
                assert empty_state["visible"] and "What can I help with?" in empty_state["message"], empty_state

                page.locator("#ai-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#ai-doc-name')?.textContent==='annual-report.pdf' && document.querySelector('#ai-active-doc-bar')?.hidden===false", timeout=10000)
                filename = page.locator("#ai-doc-name").inner_text()
                assert filename == "annual-report.pdf" and not filename.startswith("1-"), filename
                assert page.locator("#ai-empty-state").is_hidden()
                assert page.locator("#chat-messages").evaluate("element=>element.clientHeight>0"), "chat area is empty or collapsed"

                page.locator("#chat-input").fill("What is the total?")
                page.locator("#chat-send-btn").click()
                page.locator(".ai-stage-timeline").wait_for(state="visible", timeout=10000)
                page.wait_for_function("document.querySelector('.ai-stage-line span:last-child')?.textContent==='Generating…'", timeout=10000)
                chips = page.locator(".ai-stage-timeline")
                chips_metrics = chips.evaluate("element=>{const rail=element.getBoundingClientRect();const items=[...element.children].map(node=>{const r=node.getBoundingClientRect();return {label:node.textContent.trim(),left:r.left,right:r.right,top:r.top,bottom:r.bottom,inside:r.left>=rail.left-1&&r.right<=rail.right+1&&r.top>=rail.top-1&&r.bottom<=rail.bottom+1}});return {clientWidth:element.clientWidth,scrollWidth:element.scrollWidth,clientHeight:element.clientHeight,scrollHeight:element.scrollHeight,flexWrap:getComputedStyle(element).flexWrap,count:items.length,items}}")
                assert chips_metrics["count"] == 5 and chips_metrics["flexWrap"] == "wrap" and chips_metrics["clientHeight"] >= chips_metrics["scrollHeight"] - 2 and all(item["inside"] for item in chips_metrics["items"]), chips_metrics

                page.locator(".ai-stream-text").get_by_text("The total is 42000").wait_for(state="visible", timeout=10000)
                page.wait_for_function("document.querySelector('.ai-stage-line span:last-child')?.textContent==='Complete'", timeout=10000)
                output = page.locator(".ai-stream-bubble")
                rendered = output.evaluate("element=>({text:element.querySelector('.chat-markdown')?.innerText,rawMarkers:/\\[\\[?Page\\s+\\d+\\]?\\]?/i.test(element.querySelector('.chat-markdown')?.innerText||''),inlineCitations:[...element.querySelectorAll('.chat-markdown [data-ai-page]')].map(node=>({text:node.textContent.trim(),page:node.getAttribute('data-ai-page')})),verifiedCitations:[...element.querySelectorAll('.chat-citation-tags [data-ai-page]')].map(node=>({text:node.textContent.trim(),page:node.getAttribute('data-ai-page')})),stageCount:element.querySelectorAll('.ai-stage-timeline li').length})")
                assert not rendered["rawMarkers"] and rendered["inlineCitations"] == [{"text": "Page 2", "page": "2"}] and rendered["verifiedCitations"] == [{"text": "Page 2", "page": "2"}], rendered
                assert rendered["stageCount"] == 5 and not errors, {"rendered": rendered, "errors": errors}
                page.screenshot(path=str(OUT / f"id86-ai-chat-mobile-round{number}.png"), full_page=True)
                rounds.append({"round": number, "route_status": response.status, "empty_state": empty_state, "source_filename": filename, "chat_area_height": page.locator("#chat-messages").evaluate("element=>element.clientHeight"), "in_flight_stage_chips": chips_metrics, "final_answer": rendered, "page_errors": errors})
                context.close()
            browser.close()
        result = {"stream": "controlled SSE through the real UI event handler; no external provider request", "rounds": rounds}
        (OUT / "browser-id86-ai-chat-rendering-polish.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(json.dumps({"rounds": rounds}, indent=2))
    finally:
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/PID", str(app.pid), "/T", "/F"], capture_output=True, text=True)
        if app.poll() is None:
            app.terminate()
        app.wait(timeout=5)
