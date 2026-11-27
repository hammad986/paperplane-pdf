"""Verify mobile result controls, status toast, fixed Run and navigation bounds."""
from __future__ import annotations
import base64, json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

def rect(element):
    if not element or element.get_attribute("hidden") is not None: return None
    return element.evaluate("e=>{const r=e.getBoundingClientRect();return r.width&&r.height?{left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}:null}")

def overlap(a,b):
    return bool(a and b and a["left"]<b["right"] and a["right"]>b["left"] and a["top"]<b["bottom"] and a["bottom"]>b["top"])

def main():
    with TemporaryDirectory(prefix="paperplane-v24-id85-") as tmp:
        tmp=Path(tmp)
        source=tmp/"id85-source.pdf"
        with fitz.open() as pdf:
            for n in range(1,4):
                page=pdf.new_page(); page.insert_text((72,90),f"ID85 CONTENT PAGE {n}")
            pdf.save(source)
        encoded=base64.b64encode(source.read_bytes()).decode()
        app,base,_=helper.start_server(tmp/"data")
        evidence={"checks":[],"page_errors":[],"console_errors":[]}
        try:
            port=int(base.rsplit(":",1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                for width,height in ((320,568),(320,740),(390,844)):
                    page=browser.new_page(viewport={"width":width,"height":height},accept_downloads=True)
                    page.on("pageerror",lambda error:evidence["page_errors"].append(str(error)))
                    page.on("console",lambda msg:evidence["console_errors"].append(msg.text) if msg.type=="error" else None)
                    response=page.goto(base+"/merge-pdf",wait_until="domcontentloaded")
                    page.evaluate("window.selectOperation('merge')")
                    page.evaluate("""b64=>{const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));const blob=new Blob([bytes],{type:'application/pdf'});window.showDownloadResult({output_name:'id85-result.pdf',output_size:blob.size,page_count:3},URL.createObjectURL(blob),{blob});}""",encoded)
                    page.locator("#result:not([hidden])").wait_for()
                    page.wait_for_timeout(100)
                    row=page.locator("#result .result-actions")
                    download=page.locator("#result-download-link")
                    primary=rect(download)
                    action_rects=[]
                    for item in row.locator("a,button").all(): action_rects.append(rect(item))
                    toast=page.locator(".toast-notice")
                    toast_rect=rect(toast)
                    run_rect=rect(page.locator("#run-button"))
                    nav_rect=rect(page.locator(".mobile-workspace-bar"))
                    no_overflow=page.evaluate("document.documentElement.scrollWidth<=innerWidth")
                    no_toast_overlap=all(not overlap(toast_rect,item) for item in action_rects+[run_rect,nav_rect])
                    no_button_clipping=all(item and item["left"]>=0 and item["right"]<=width and item["top"]>=0 and item["bottom"]<=height for item in action_rects)
                    screenshot=Path(__file__).parent/f"browser-id85-result-{width}x{height}.png"
                    page.screenshot(path=str(screenshot),full_page=True)
                    with page.expect_download(timeout=15000) as pending: download.click()
                    result=pending.value; output=tmp/result.suggested_filename; result.save_as(output)
                    with fitz.open(output) as parsed:
                        content_checked=parsed.is_pdf and parsed.page_count==3 and all(f"ID85 CONTENT PAGE {n}" in parsed[i].get_text() for i,n in enumerate((1,2,3)))
                    evidence["checks"].append({"viewport":[width,height],"route_status":response.status if response else None,
                        "result_card":rect(page.locator("#result")),"primary_download":primary,"action_buttons":action_rects,
                        "toast":toast_rect,"run_button":run_rect,"bottom_navigation":nav_rect,
                        "no_horizontal_overflow":no_overflow,"no_toast_overlap":no_toast_overlap,
                        "no_button_clipping":no_button_clipping,"download":result.suggested_filename,"content_checked":content_checked,
                        "carousel_nodes":page.locator("[class*=carousel], [id*=carousel]").count(),"screenshot":screenshot.name})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=5)
    evidence["result"]=len(evidence["checks"])==3 and not evidence["page_errors"] and not evidence["console_errors"] and all(
        c["route_status"]==200 and c["content_checked"] and c["no_horizontal_overflow"] and c["no_toast_overlap"] and c["no_button_clipping"] for c in evidence["checks"])
    out=Path(__file__).parent/"browser-id85-result-toast-current.json"
    out.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    if not evidence["result"]: raise SystemExit(1)

if __name__=="__main__": main()
