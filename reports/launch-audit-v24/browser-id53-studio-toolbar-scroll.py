"""Check Studio toolbar, Export, breadcrumb and page rail after long-page scrolling."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-v24-id53-") as temp:
    root=Path(temp); fixture=root/"studio-69-pages.pdf"
    with fitz.open() as doc:
        for number in range(1,70):
            page=doc.new_page(); page.insert_text((72,72),f"Studio scroll marker {number:02d}",fontsize=12)
        doc.save(fixture)
    app,base,_identity=helper.start_server(root/"data")
    try:
        port=int(base.rsplit(":",1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2): break
            except OSError: time.sleep(.15)
        evidence={"rounds":[],"page_errors":[],"console_errors":[]}
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            for round_number in (1,2):
                page=browser.new_page(viewport={"width":1366,"height":900})
                page.on("pageerror",lambda err:evidence["page_errors"].append(str(err)))
                page.on("console",lambda msg:evidence["console_errors"].append(msg.text) if msg.type=="error" else None)
                page.goto(base+"/studio",wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='69'",timeout=30000)
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=30000)
                page.evaluate("""() => {
                  const canvas=document.querySelector('#studio-canvas-area');
                  const pages=document.querySelector('#studio-thumbnails-scroll')||document.querySelector('#studio-thumbnails-bar');
                  if(canvas) canvas.scrollTop=canvas.scrollHeight;
                  if(pages) pages.scrollTop=pages.scrollHeight;
                }""")
                page.wait_for_timeout(300)
                metrics=page.evaluate("""() => {
                  const r=s=>{const e=document.querySelector(s);if(!e)return null;const x=e.getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom,width:x.width,height:x.height,display:getComputedStyle(e).display};};
                  const top=r('.topbar'), crumb=r('.breadcrumb-trail'), toolbar=r('#studio-toolbar'), exp=r('#save-studio-btn'), pages=r('#studio-thumbnails-bar');
                  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,pageCount:document.querySelector('#page-total-indicator')?.textContent,topbar:top,breadcrumb:crumb,toolbar,export:exp,pages,canvasScrollTop:document.querySelector('#studio-canvas-area')?.scrollTop,exportVisible:!!exp&&exp.width>0&&exp.left>=0&&exp.right<=innerWidth,toolbarBelowHeader:!!top&&!!toolbar&&toolbar.top>=top.bottom-1,pagesVisible:!!pages&&pages.width>0};
                }""")
                assert metrics["pageCount"]=="69" and metrics["exportVisible"] and metrics["toolbarBelowHeader"] and metrics["pagesVisible"] and metrics["documentWidth"]<=1368,metrics
                evidence["rounds"].append(metrics)
                page.screenshot(path=str(OUT/f"id53-studio-scroll-round{round_number}.png"))
                page.close()
            browser.close()
        assert not evidence["page_errors"] and not evidence["console_errors"], evidence
        evidence["result"]="passed"
        (OUT/"browser-id53-studio-toolbar-scroll.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
        print(json.dumps(evidence,indent=2))
    finally:
        app.terminate(); app.wait(timeout=5)
