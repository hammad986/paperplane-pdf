"""Exercise processing-mode persistence and the browser/server privacy controls."""
from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

def main():
    evidence={"mode_rounds":[],"route_matrix":[],"scope_copy":{},"page_errors":[],"console_errors":[]}
    with TemporaryDirectory(prefix="paperplane-v24-id148-155-") as tmp:
        app,base,_=helper.start_server(Path(tmp)/"data")
        try:
            port=int(base.rsplit(":",1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1",port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError("local app did not start")
            with sync_playwright() as p:
                browser=p.chromium.launch(channel="chrome",headless=True)
                page=browser.new_page(viewport={"width":1366,"height":900})
                page.add_init_script("if(!sessionStorage.getItem('id148-seeded')){localStorage.setItem('paperplane-pdf-processing-mode','server');sessionStorage.setItem('id148-seeded','1')}")
                page.on("pageerror",lambda error:evidence["page_errors"].append(str(error)))
                page.on("console",lambda msg:evidence["console_errors"].append(msg.text) if msg.type=="error" else None)
                for route in ("/merge-pdf","/rotate-pdf","/remove-pages"):
                    response=page.goto(base+route,wait_until="domcontentloaded")
                    page.locator("#client-privacy-toggle").wait_for(state="attached")
                    evidence["mode_rounds"].append({"route":route,"status":response.status if response else None,
                        "sidebar_checked":page.locator("#client-privacy-toggle").is_checked(),
                        "settings_preference":page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")})
                page.locator("#sidebar-settings-gear-btn").click()
                page.locator("#settings-tab-btn-privacy").click()
                setting=page.locator("#settings-client-privacy-toggle")
                setting.wait_for(state="attached")
                initial_setting=setting.is_checked()
                page.screenshot(path=str(Path(__file__).parent/"browser-id148-settings-privacy.png"),full_page=True)
                content=page.locator("#settings-modal .settings-content")
                content.evaluate("e=>e.scrollTop=e.scrollHeight")
                label=page.locator("label.toggle-switch-sm:has(#settings-client-privacy-toggle)")
                evidence["privacy_control_debug"]={"content_scroll_top":content.evaluate("e=>e.scrollTop"),"content_scroll_height":content.evaluate("e=>e.scrollHeight"),
                    "content_client_height":content.evaluate("e=>e.clientHeight"),"label_box":label.bounding_box(),"input_box":setting.bounding_box(),
                    "input_visible":setting.is_visible(),"input_disabled":setting.is_disabled()}
                page.screenshot(path=str(Path(__file__).parent/"browser-id148-settings-privacy-scrolled.png"),full_page=True)
                label.click()
                page.wait_for_function("document.querySelector('#settings-client-privacy-toggle').checked")
                settings_copy=page.locator("#settings-client-privacy-support").inner_text()
                page.locator("#close-settings-modal").click()
                for route in ("/merge-pdf","/rotate-pdf","/remove-pages"):
                    response=page.goto(base+route,wait_until="domcontentloaded")
                    page.locator("#client-privacy-toggle").wait_for(state="attached")
                    evidence["mode_rounds"].append({"route":route,"status":response.status if response else None,
                        "sidebar_checked":page.locator("#client-privacy-toggle").is_checked(),
                        "settings_preference":page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")})
                page.reload(wait_until="domcontentloaded")
                page.locator("#client-privacy-toggle").wait_for(state="attached")
                reload_checked=page.locator("#client-privacy-toggle").is_checked()
                evidence["settings"]= {"initial_server_preference":initial_setting,"after_toggle_local":setting.is_checked(),
                    "reload_sidebar_checked":reload_checked,"saved_preference":page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")}
                page.goto(base+"/merge-pdf",wait_until="domcontentloaded")
                sidebar_copy=page.locator("#privacy-mode-support").inner_text()
                evidence["scope_copy"]={"settings":settings_copy,"merge_sidebar":sidebar_copy,
                    "settings_names_page_organizer":"page organizer" in settings_copy.lower(),
                    "settings_names_photo_tools":"photo tools" in settings_copy.lower(),
                    "sidebar_describes_selected_tool":"merge pdf runs in your browser" in sidebar_copy.lower()}
                routes=page.evaluate("""() => Object.entries(TOOL_SLUGS).map(([op,slug])=>({op,slug,local:CLIENT_SIDE_SUPPORTED_OPERATIONS.has(op),image:CLIENT_SIDE_IMAGE_OPERATIONS.has(op)}))""")
                preference=page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")
                for item in routes:
                    route="/"+item["slug"]
                    response=page.goto(base+route,wait_until="domcontentloaded")
                    page.locator("#client-privacy-toggle").wait_for(state="attached")
                    checked=page.locator("#client-privacy-toggle").is_checked()
                    disabled=page.locator("#client-privacy-toggle").is_disabled()
                    expected=bool(item["image"] or (item["local"] and preference!="server"))
                    evidence["route_matrix"].append({"operation":item["op"],"route":route,"status":response.status if response else None,
                        "checked":checked,"disabled":disabled,"expected_checked":expected,"match":checked==expected})
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=5)
    evidence["result"]=(not evidence["page_errors"] and not evidence["console_errors"]
        and all(x["status"]==200 for x in evidence["mode_rounds"])
        and [x["sidebar_checked"] for x in evidence["mode_rounds"]]==[False,False,False,True,True,True]
        and evidence["settings"]["reload_sidebar_checked"] and evidence["settings"]["saved_preference"]=="local"
        and evidence["scope_copy"]["settings_names_page_organizer"] and evidence["scope_copy"]["settings_names_photo_tools"]
        and evidence["scope_copy"]["sidebar_describes_selected_tool"]
        and len(evidence["route_matrix"])>=40 and all(x["status"]==200 and x["match"] for x in evidence["route_matrix"]))
    out=Path(__file__).parent/"browser-id148-id155-processing-mode.json"
    out.write_text(json.dumps(evidence,indent=2),encoding="utf-8")
    print(json.dumps(evidence,indent=2))
    if not evidence["result"]: raise SystemExit(1)

if __name__=="__main__": main()
