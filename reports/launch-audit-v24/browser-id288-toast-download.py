"""Recheck success-toast overlap against tool download actions in Chrome."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

def intersects(a, b):
    return a["x"] < b["x"] + b["width"] and a["x"] + a["width"] > b["x"] and a["y"] < b["y"] + b["height"] and a["y"] + a["height"] > b["y"]

def main():
    source = ROOT / "web" / "assets" / "demo.pdf"
    evidence = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id288-") as tmp:
        app, base, _ = helper.start_server(Path(tmp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local server did not start")
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                for width in (390, 1366):
                    operation = "protect" if width == 390 else "compress"
                    page = browser.new_page(viewport={"width":width,"height":844}, accept_downloads=True)
                    page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                    page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                    response = page.goto(base+("/protect-pdf" if operation == "protect" else "/compress-pdf"), wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(source))
                    page.wait_for_function("state.files?.length === 1")
                    if operation == "protect": page.locator("#password").fill("Toast-Overlap-Password!24")
                    page.locator("#run-button").click()
                    page.wait_for_function("document.querySelector('#result-download-link') && !document.querySelector('#result-download-link').hidden", timeout=60000)
                    link = page.locator("#result-download-link")
                    page.wait_for_function("(()=>{const e=document.querySelector('#result-download-link');const r=e?.getBoundingClientRect();return !!r&&r.width>0&&r.height>0})()", timeout=10000)
                    linkstate = link.evaluate("e=>({rect:(()=>{const r=e.getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height}})(),hidden:e.hidden,display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,opacity:getComputedStyle(e).opacity})")
                    page.evaluate("showToast('Download complete!', 'success', 10000)")
                    injected_toast = page.locator(".toast-notice")
                    injected_toast.wait_for(state="visible", timeout=3000)
                    before_click_toastbox = injected_toast.bounding_box()
                    pre_click_intersection = bool(linkstate["rect"]["width"] and linkstate["rect"]["height"] and before_click_toastbox and intersects(linkstate["rect"], before_click_toastbox))
                    with page.expect_download(timeout=30000) as dl:
                        link.click()
                    download = dl.value
                    output_path=Path(tmp)/download.suggested_filename
                    download.save_as(output_path)
                    with fitz.open(output_path) as output_pdf:
                        output_valid=output_pdf.page_count > 0 and output_pdf.is_pdf
                        if operation == "protect": output_valid = output_valid and output_pdf.is_encrypted and bool(output_pdf.authenticate("Toast-Overlap-Password!24"))
                    toast = page.locator(".toast-notice").filter(has_text="Download complete!")
                    toast.wait_for(state="visible", timeout=5000)
                    toastbox = toast.bounding_box()
                    evidence["rounds"].append({"operation":operation,"viewport_width":width,"route_status":response.status if response else None,
                        "download_name":download.suggested_filename,"download_pdf_valid":output_valid,"button_state":linkstate,"toast_box":toastbox,
                        "preexisting_success_toast_box":before_click_toastbox,"toast_intersects_download_button":pre_click_intersection,
                        "toast_pointer_events":toast.evaluate("e=>getComputedStyle(e).pointerEvents"),
                        "toast_z_index":toast.evaluate("e=>getComputedStyle(e).zIndex")})
                    page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=5)
    evidence["result"] = not evidence["page_errors"] and not evidence["console_errors"] and len(evidence["rounds"]) == 2 and all(r["route_status"] == 200 and r["download_pdf_valid"] and not r["toast_intersects_download_button"] for r in evidence["rounds"])
    out=ROOT/"reports"/"launch-audit-v24"/"browser-id288-toast-download.json"
    out.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    if not evidence["result"]: raise SystemExit(1)
if __name__ == "__main__": main()
