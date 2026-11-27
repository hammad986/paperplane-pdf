"""Reproduce result-action overlap after a successful PDF download."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

def box(locator):
    return locator.evaluate("e=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}}")

def intersects(a, b):
    return a["x"] < b["x"] + b["width"] and a["x"] + a["width"] > b["x"] and a["y"] < b["y"] + b["height"] and a["y"] + a["height"] > b["y"]

def main():
    evidence = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id224-") as temp:
        temp = Path(temp)
        sources=[]
        for n in (1,2):
            path=temp/f"source-{n}.pdf"
            with fitz.open() as pdf:
                page=pdf.new_page(); page.insert_text((72,90),f"ID224 SOURCE PAGE {n}"); pdf.save(path)
            sources.append(path)
        app,base,_=helper.start_server(temp/"data")
        try:
            port=int(base.rsplit(":",1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local server did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                for width,height in ((320,568),(390,844),(1366,900)):
                    page=browser.new_page(viewport={"width":width,"height":height},accept_downloads=True)
                    page.on("pageerror",lambda err:evidence["page_errors"].append(str(err)))
                    page.on("console",lambda msg:evidence["console_errors"].append(msg.text) if msg.type=="error" else None)
                    response=page.goto(base+"/merge-pdf",wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files([str(x) for x in sources])
                    page.wait_for_function("state.files?.length === 2")
                    page.locator("#run-button").click()
                    page.locator("#result-download-link:not([hidden])").wait_for(timeout=60000)
                    actions=page.locator("#result .result-actions")
                    # Check the app's actual completion toast while positioning
                    # the result actions near the bottom of the viewport.
                    actions.scroll_into_view_if_needed()
                    page.evaluate("""() => {const e=document.querySelector('#result .result-actions');const r=e.getBoundingClientRect();window.scrollBy(0,Math.max(0,r.bottom-(innerHeight-95)));}""")
                    page.wait_for_timeout(180)
                    completion_toast=page.locator(".toast-notice")
                    completion_toast.wait_for(state="visible",timeout=3000)
                    completion_toast_box=box(completion_toast)
                    completion_actions_box=box(actions)
                    completion_no_overlap=not intersects(completion_toast_box,completion_actions_box)
                    completion_screenshot=Path(__file__).parent/f"browser-id224-completion-{width}.png"
                    page.screenshot(path=str(completion_screenshot),full_page=False)
                    with page.expect_download(timeout=30000) as pending:
                        page.locator("#result-download-link").click()
                    download=pending.value; output=temp/download.suggested_filename; download.save_as(output)
                    with fitz.open(output) as pdf:
                        content_ok=pdf.is_pdf and pdf.page_count==2 and all(f"ID224 SOURCE PAGE {n}" in pdf[i].get_text() for i,n in enumerate((1,2)))
                    # Force the exact success message after the local server's
                    # blob URL path. Some browsers bypass the fetch-to-blob path,
                    # so this exercises the same actual toast component on the
                    # result-card state without stubbing layout or hit-testing.
                    # Scroll the actions low into view as a user would before
                    # selecting Process Another File / All Tools.
                    actions.scroll_into_view_if_needed()
                    page.evaluate("""() => {const e=document.querySelector('#result .result-actions');const r=e.getBoundingClientRect();window.scrollBy(0,Math.max(0,r.bottom-(innerHeight-95)));}""")
                    page.wait_for_timeout(150)
                    actions_box=box(actions)
                    action_boxes=[box(action) for action in actions.locator("a,button").all()]
                    screenshot=Path(__file__).parent/f"browser-id224-actions-{width}.png"
                    page.screenshot(path=str(screenshot),full_page=False)
                    page.evaluate("showToast('Download complete!', 'success', 10000)")
                    toast=page.locator(".toast-notice").filter(has_text="Download complete!")
                    toast.wait_for(state="visible",timeout=5000)
                    toast_box=box(toast)
                    evidence["rounds"].append({"viewport":[width,height],"route_status":response.status if response else None,
                        "scroll_y":page.evaluate("scrollY"),"download":download.suggested_filename,"content_checked":content_ok,
                        "action_row":actions_box,"action_buttons":action_boxes,"toast":toast_box,
                        "completion_toast":completion_toast_box,"completion_action_row":completion_actions_box,
                        "completion_toast_no_overlap":completion_no_overlap,"completion_screenshot":completion_screenshot.name,
                        "toast_intersects_action_row":intersects(toast_box,actions_box),
                        "toast_intersects_action_buttons":[intersects(toast_box,x) for x in action_boxes],
                        "toast_pointer_events":toast.evaluate("e=>getComputedStyle(e).pointerEvents"),"screenshot":screenshot.name})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=5)
    evidence["result"]=not evidence["page_errors"] and not evidence["console_errors"] and len(evidence["rounds"])==3 and all(
        x["route_status"]==200 and x["content_checked"] and x["completion_toast_no_overlap"] and not x["toast_intersects_action_row"] for x in evidence["rounds"])
    output=Path(__file__).parent/"browser-id224-result-action-toast.json"
    output.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    if not evidence["result"]: raise SystemExit(1)

if __name__=="__main__": main()
