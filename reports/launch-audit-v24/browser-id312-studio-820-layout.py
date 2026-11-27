"""Inspect Studio's tablet breakpoint with a real multi-page PDF in Chrome."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"reports"/"launch-audit-v24"
with TemporaryDirectory(prefix="paperplane-id312-") as tmp:
    temp=Path(tmp);source=temp/"tablet.pdf"
    with fitz.open() as doc:
        for n in range(1,6):
            page=doc.new_page(width=612,height=792);page.insert_text((72,72),f"ID312 tablet page {n} marker TBL{n:02d}")
        doc.save(source)
    with socket.socket() as sock:sock.bind(("127.0.0.1",0));port=sock.getsockname()[1]
    sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
    import browser_acceptance_v14 as helper
    app,base,_=helper.start_server(temp/"data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",port),timeout=.2):break
            except OSError:time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True);page=browser.new_page(viewport={"width":820,"height":900},is_mobile=True,has_touch=True);errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            page.goto(base+"/studio",wait_until="domcontentloaded")
            page.locator("#studio-file-input").set_input_files(str(source))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='5' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=25000)
            page.wait_for_timeout(1000)
            selectors=["#btn-more-tools-trigger","#studio-upload-btn","#save-studio-btn","#zoom-out-btn","#zoom-select","#zoom-in-btn","#page-jump-input","#studio-mobile-pages-btn"]
            controls=page.evaluate("selectors=>selectors.map(selector=>{const el=document.querySelector(selector);if(!el)return{selector,exists:false};const r=el.getBoundingClientRect(),s=getComputedStyle(el);return{selector,exists:true,visible:!!(r.width&&r.height)&&s.visibility!=='hidden'&&s.display!=='none',rect:{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom},insideViewport:r.left>=-1&&r.right<=innerWidth+1}})",selectors)
            page.locator("#studio-mobile-pages-btn").click()
            page.wait_for_function("(()=>{const r=document.querySelector('#studio-thumbnails-bar')?.getBoundingClientRect();return !!r&&r.width>0&&r.height>0})()")
            metrics=page.evaluate("""()=>{const panel=document.querySelector('#studio-thumbnails-bar'),r=panel?.getBoundingClientRect();return{viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,activeView:document.body.classList.contains('studio-active'),pages:document.querySelector('#page-total-indicator')?.textContent,canvasScrollWidth:document.querySelector('#studio-canvas-area')?.scrollWidth,canvasClientWidth:document.querySelector('#studio-canvas-area')?.clientWidth,canvasScrollHeight:document.querySelector('#studio-canvas-area')?.scrollHeight,canvasClientHeight:document.querySelector('#studio-canvas-area')?.clientHeight,activePage:document.querySelector('.studio-page-sheet[data-page="1"] .pdf-page-canvas')?.dataset.rendered,pagesPanelVisible:!!r&&r.width>0&&r.height>0}}""")
            page.screenshot(path=str(OUT/"id312-studio-820.png"),full_page=False)
            assert metrics["documentWidth"]<=820 and metrics["bodyWidth"]<=820,metrics
            assert metrics["pages"]=="5" and metrics["activePage"]=="true",metrics
            assert metrics["pagesPanelVisible"],metrics
            assert all(row["exists"] and row["visible"] for row in controls),controls
            assert not errors,errors
            evidence={"viewport":820,"metrics":metrics,"controls":controls,"page_errors":errors,"result":"passed"}
            (OUT/"browser-id312-studio-820-layout.json").write_text(json.dumps(evidence,indent=2),encoding="utf-8")
            print(json.dumps(evidence,indent=2));browser.close()
    finally:app.terminate();app.wait(timeout=5)
