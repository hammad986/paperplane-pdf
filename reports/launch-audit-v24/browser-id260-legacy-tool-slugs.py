"""Check legacy tool URLs redirect to live canonical pages in local Chrome."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
import browser_acceptance_v14 as helper
CASES={"resize-photo":"resize-image-dimensions","photo-resize":"resize-image-dimensions","compress-photo":"compress-image-online","add-page-numbers":"add-page-numbers-to-pdf"}
with TemporaryDirectory(prefix="paperplane-id260-") as tmp:
    app,base,_=helper.start_server(Path(tmp)/"data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",int(base.rsplit(":",1)[1])),timeout=.2): break
            except OSError: time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True); page=browser.new_page(viewport={"width":390,"height":844}); errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            results=[]
            for old,canonical in CASES.items():
                response=page.goto(base+"/"+old,wait_until="domcontentloaded")
                assert response and response.status==200
                assert page.url.endswith("/"+canonical),page.url
                title=page.title(); assert "Paperplane" in title,title
                results.append({"legacy_path":"/"+old,"final_path":"/"+canonical,"final_status":response.status,"title":title})
            assert not errors,errors
            payload={"results":results,"page_errors":errors,"result":"passed"}
            (ROOT/"reports"/"launch-audit-v24"/"browser-id260-legacy-tool-slugs.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
            print(json.dumps(payload,indent=2));browser.close()
    finally: app.terminate();app.wait(timeout=5)
