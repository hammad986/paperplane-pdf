"""Measure AI Intelligence layout before and after an offline Executive Brief in Chrome."""
from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent/"browser-id34-ai-layout-after-summary.json"

with TemporaryDirectory(prefix="paperplane-v24-id34-") as temp:
    tmp=Path(temp); data=tmp/"data"; data.mkdir(); pdf=tmp/"six-page-note.pdf"
    with fitz.open() as doc:
        for n in range(1,7):
            page=doc.new_page(); page.insert_text((72,72),f"Summary layout marker page {n}. Reliable systems require explicit recovery and review.",fontsize=12)
        doc.set_metadata({"title":"Summary Layout Note"}); doc.save(pdf)
    with socket.socket() as sock: sock.bind(("127.0.0.1",0)); port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(("PAPERPLANE_","CASHFREE_","SMTP_","RESEND_","OPENAI_","OPENROUTER_","BLUESMINDS_","ANTHROPIC_","GEMINI_","DEEPSEEK_","GOOGLE_API_","AI_","ADMIN_")) and k not in {"TESTING","SESSION_SECRET_KEY"}}
    env.update({"PAPERPLANE_SKIP_DOTENV":"1","PAPERPLANE_ENV":"development","PAPERPLANE_DATA_DIR":str(data),"PAPERPLANE_PORT":str(port),"PAPERPLANE_ADMIN_KEY":secrets.token_urlsafe(48),"PAPERPLANE_ADMIN_CODE":secrets.token_urlsafe(32),"PAPERPLANE_SESSION_SECRET":secrets.token_urlsafe(48),"PAPERPLANE_SECURE_COOKIES":"false","PYTHONPATH":str(ROOT)})
    app=subprocess.Popen([sys.executable,"app.py"],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    evidence={"widths":[],"page_errors":[],"console_errors":[]}
    try:
        for _ in range(120):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError("Local server did not start")
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            page=browser.new_page(viewport={"width":1366,"height":900})
            page.on("pageerror",lambda e:evidence["page_errors"].append(str(e)))
            page.on("console",lambda m:evidence["console_errors"].append(m.text) if m.type=="error" else None)
            # Exercise the real UI transition with a deterministic provider response.
            # This local workspace has no AI provider credentials, so the capability
            # and summarize endpoints are controlled at the browser boundary.
            page.route("**/api/ai/capabilities", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"executive_brief_available": True, "reason": None})))
            page.route("**/api/ai/summarize", lambda route: route.fulfill(status=200, content_type="application/json", body=json.dumps({"summary": "# Executive Summary\n\nA six-page note describes reliable recovery.\n\n## Findings\n\n- Page processing should preserve source context.\n- Review should confirm each exported result.", "summary_mode": "offline_extractive", "citations": [1, 2, 3, 4, 5, 6]})))
            page.goto(f"http://127.0.0.1:{port}/ai-intelligence",wait_until="domcontentloaded")
            page.locator("#ai-file-input").set_input_files(str(pdf))
            page.wait_for_function("!document.querySelector('#ai-active-doc-bar')?.hidden && document.querySelector('#summary-mode-badge')?.textContent?.trim()",timeout=30000)
            evidence["before_summary"]=page.evaluate("""() => ({title:document.querySelector('#ai-active-doc-name')?.textContent,summary:document.querySelector('#summary-display')?.innerText,mode:document.querySelector('#summary-mode-badge')?.textContent})""")
            page.locator("#trigger-summary-btn").click()
            page.wait_for_function("document.querySelector('#summary-display')?.innerText?.length > 120 && document.querySelector('#summary-actions-bar')?.hidden === false",timeout=30000)
            evidence["summary_mode"]=page.locator("#summary-mode-badge").inner_text()
            for width,height in ((390,844),(820,900),(1366,900)):
                page.set_viewport_size({"width":width,"height":height}); page.wait_for_timeout(250)
                metrics=page.evaluate("""() => {
                  const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,display:getComputedStyle(e).display};};
                  const cards=[...document.querySelectorAll('.ai-studio-container > .ai-chat-card, .ai-studio-container > div:last-child > .ai-chat-card')].map(rect);
                  const summary=document.querySelector('#summary-display');
                  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,cards,summary:rect(summary),summaryCharacters:summary?.innerText?.length||0,summaryMode:document.querySelector('#summary-mode-badge')?.innerText};
                }""")
                assert metrics["documentWidth"]<=width+2 and metrics["summaryCharacters"]>120,metrics
                if width==1366:
                    assert len(metrics["cards"])>=3 and all(card and card["right"]<=width+1 and card["width"]>0 for card in metrics["cards"]),metrics
                page.screenshot(path=str(OUT.parent/f"id34-ai-layout-{width}.png"))
                evidence["widths"].append(metrics)
            assert not evidence["page_errors"] and not evidence["console_errors"],evidence
            browser.close()
        evidence["result"]="passed"
    finally:
        app.terminate()
        try: app.wait(timeout=5)
        except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
OUT.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
print(json.dumps(evidence,indent=2))
