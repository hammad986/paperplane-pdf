"""Focused diagnostic for authenticated mobile feedback prompt visibility."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix="paperplane-id221-") as tmp:
    app,base,identities=helper.start_server(Path(tmp)/"data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",int(base.rsplit(":",1)[1])),timeout=.2): break
            except OSError: time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            context=browser.new_context(viewport={"width":390,"height":844})
            context.add_cookies([{"name":"paperplane_token","value":identities["accounts"][0][1],"url":base,"httpOnly":True,"secure":False,"sameSite":"Lax"}])
            page=context.new_page();page.goto(base+"/",wait_until="networkidle")
            page.wait_for_function("Boolean(window.state?.user?.user_id)",timeout=10000)
            page.wait_for_timeout(800)
            diagnostic=page.evaluate("""()=>{
              const userId=window.state?.user?.user_id||null;
              const container=document.querySelector('#pp-feedback-container');
              const launcher=document.querySelector('#pp-feedback-launcher');
              const dismiss=document.querySelector('#pp-feedback-dismiss');
              const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect(),s=getComputedStyle(e);return{x:r.x,y:r.y,width:r.width,height:r.height,display:s.display,visibility:s.visibility,hidden:e.hidden}};
              const flag=kind=>userId?localStorage.getItem(`paperplane-feedback-${kind}:v1:account-${userId}`):null;
              return {userId,container:rect(container),launcher:rect(launcher),dismiss:rect(dismiss),dismissed:flag('dismissed'),submitted:flag('submitted'),seen:flag('seen'),viewport:{w:innerWidth,h:innerHeight},page:{scrollY,scrollHeight:document.documentElement.scrollHeight}};
            }""")
            page.screenshot(path=str(ROOT/"reports"/"launch-audit-v24"/"feedback-mobile-diagnostic.png"),full_page=False)
            page.locator("#topbar-user-profile-btn").click()
            page.locator("#settings-tab-btn-privacy").click()
            page.locator("#settings-feedback-open").wait_for(state="visible",timeout=5000)
            page.locator("#settings-feedback-open").click()
            page.wait_for_function("getComputedStyle(document.querySelector('#pp-feedback-popover')).display === 'flex'")
            diagnostic["accessible_from_mobile_settings"] = True
            diagnostic["popover_opened_from_settings"] = page.locator("#pp-feedback-popover").evaluate("el=>getComputedStyle(el).display==='flex'")
            page.screenshot(path=str(ROOT/"reports"/"launch-audit-v24"/"feedback-mobile-settings-open.png"),full_page=False)
            (ROOT/"reports"/"launch-audit-v24"/"browser-id221-feedback-widget-diagnostic.json").write_text(json.dumps(diagnostic,indent=2),encoding="utf-8")
            print(json.dumps(diagnostic,indent=2));browser.close()
    finally: app.terminate();app.wait(timeout=5)
