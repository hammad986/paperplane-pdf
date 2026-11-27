"""Inspect Studio controls and canvas at phone and desktop widths in real Chrome."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper


def main() -> None:
    with TemporaryDirectory(prefix="paperplane-v24-id30-") as tmp:
        root = Path(tmp)
        fixture = root / "studio-six-pages.pdf"
        with fitz.open() as doc:
            for page_no in range(1, 7):
                page = doc.new_page()
                page.insert_text((72, 72), f"Mobile Studio layout marker {page_no}", fontsize=18)
            doc.save(fixture)
        app, base, _identity = helper.start_server(root / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.15)
            results = {"rounds": [], "page_errors": [], "console_errors": []}
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.on("pageerror", lambda err: results["page_errors"].append(str(err)))
                page.on("console", lambda msg: results["console_errors"].append(msg.text) if msg.type == "error" else None)
                page.goto(base + "/studio", wait_until="domcontentloaded")
                page.locator("#studio-file-input").set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '6' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=30000)
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=30000)
                for width, height in ((390, 844), (820, 900), (1366, 900)):
                    page.set_viewport_size({"width": width, "height": height})
                    page.wait_for_timeout(3000)
                    metrics = page.evaluate("""() => {
                      const rect = selector => { const el=document.querySelector(selector); if(!el) return null; const r=el.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height,display:getComputedStyle(el).display}; };
                      const toolbar=document.querySelector('#studio-toolbar');
                      const exportButton=document.querySelector('#save-studio-btn');
                      const clearLabel=document.querySelector('#studio-clear-pdf-btn .tool-btn-text');
                      const canvas=document.querySelector('#pdf-canvas');
                      const footer=document.querySelector('.app-global-footer');
                      const undoBanner=document.querySelector('#studio-undo-banner');
                      const br=exportButton?.getBoundingClientRect(), nav=document.querySelector('.mobile-bottom-nav')?.getBoundingClientRect();
                      let darkPixels=null; if(canvas?.width&&canvas?.height){const ctx=canvas.getContext('2d');if(ctx){darkPixels=0;const data=ctx.getImageData(0,0,canvas.width,canvas.height).data;for(let i=0;i<data.length;i+=4)if(data[i]<80&&data[i+1]<80&&data[i+2]<80&&data[i+3]>0)darkPixels++;}}
                      const fr=footer?.getBoundingClientRect();
                      const main=document.querySelector('.main-area');
                      const footerVisibility=footer?getComputedStyle(footer).visibility:'missing';
                      return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,documentScrollHeight:document.documentElement.scrollHeight,documentClientHeight:document.documentElement.clientHeight,bodyScrollHeight:document.body.scrollHeight,mainScrollHeight:main?.scrollHeight,mainClientHeight:main?.clientHeight,footerRevealed:document.documentElement.classList.contains('footer-revealed'),toolbar:rect('#studio-toolbar'),primaryRibbon:rect('.studio-primary-ribbon'),subRibbon:rect('.studio-sub-ribbon'),undoBanner:{hidden:undoBanner?.hidden,text:undoBanner?.innerText||''},footer:{display:footer?getComputedStyle(footer).display:'missing',visibility:footerVisibility,visible:!!footer&&footerVisibility==='visible'&&getComputedStyle(footer).display!=='none',top:fr?.top??null,bottom:fr?.bottom??null,initiallyInViewport:!!fr&&fr.top<innerHeight&&fr.bottom>0},clearPdfLabel:{text:clearLabel?.innerText,rect:clearLabel?(()=>{const r=clearLabel.getBoundingClientRect();return {width:r.width,height:r.height,scrollHeight:r.scrollHeight,clientHeight:r.clientHeight}})():null},export:rect('#save-studio-btn'),pageCount:document.querySelector('#page-total-indicator')?.textContent,canvas:{width:canvas?.width||0,height:canvas?.height||0,clientWidth:canvas?.clientWidth||0,clientHeight:canvas?.clientHeight||0,datasetRendered:canvas?.dataset.rendered,darkPixels},exportWithinViewport:!!br&&br.left>=0&&br.right<=innerWidth,exportAboveMobileNavigation:!nav||nav.height===0||!!br&&br.bottom<=nav.top+1};
                    }""")
                    if width == 390:
                        page.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
                        page.locator(".main-area").evaluate("el => el.scrollTo({top: el.scrollHeight, behavior: 'instant'})")
                        page.wait_for_timeout(250)
                        metrics["footerAfterScroll"] = page.locator(".app-global-footer").evaluate("el => { const r=el.getBoundingClientRect(), s=getComputedStyle(el); return {display:s.display, visibility:s.visibility, visible:s.visibility==='visible'&&s.display!=='none', top:r.top, bottom:r.bottom, inViewport:r.top<innerHeight&&r.bottom>0, revealed:document.documentElement.classList.contains('footer-revealed'), scrollY:window.scrollY}; }")
                    results["rounds"].append(metrics)
                    page.screenshot(path=str(OUT / f"id30-studio-layout-{width}.png"), full_page=False)
                    assert metrics["pageCount"] == "6" and metrics["canvas"]["clientWidth"] > 0, metrics
                    assert metrics["documentWidth"] <= width + 2, metrics
                    assert metrics["clearPdfLabel"]["text"] == "Clear PDF", metrics
                    if width == 390:
                        assert metrics["exportWithinViewport"] and metrics["exportAboveMobileNavigation"], metrics
                        assert metrics["undoBanner"]["hidden"] is True, metrics
                        assert not metrics["footer"]["visible"] and not metrics["footerRevealed"], metrics
                        assert metrics["footerAfterScroll"]["inViewport"] and metrics["footerAfterScroll"]["visible"] and metrics["footerAfterScroll"]["revealed"], metrics
                assert not results["page_errors"], results
                browser.close()
            results["result"] = "passed"
            (OUT / "browser-id30-mobile-studio-layout.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
            print(json.dumps(results, indent=2))
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
