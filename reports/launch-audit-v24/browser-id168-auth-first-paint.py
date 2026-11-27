"""Observe the authenticated Settings first paint and hydrated state in Chrome."""
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/"reports"/"launch-audit-v14"))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix="paperplane-id168-") as tmp:
    app,base,identities=helper.start_server(Path(tmp)/"data")
    try:
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1",int(base.rsplit(":",1)[1])),timeout=.2): break
            except OSError: time.sleep(.2)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel="chrome",headless=True)
            context=browser.new_context(viewport={"width":1366,"height":900})
            context.add_cookies([{"name":"paperplane_token","value":identities["accounts"][0][1],"url":base,"httpOnly":True,"secure":False,"sameSite":"Lax"}])
            page=context.new_page();errors=[]
            page.on("pageerror",lambda e:errors.append(str(e)))
            def delay_auth(route):
                time.sleep(1.0)
                route.continue_()
            page.route("**/api/auth/me",delay_auth)
            route_results=[]
            for path in ("/", "/compress-pdf", "/settings", "/studio"):
                response=page.goto(base+path,wait_until="domcontentloaded")
                assert response and response.status==200,(path,response.status if response else None)
                first=page.evaluate("""()=>({authPending:document.body.classList.contains('auth-pending'),guestGroupHidden:getComputedStyle(document.querySelector('#topbar-auth-guest')).visibility==='hidden',userGroupHidden:document.querySelector('#topbar-auth-user').hidden,sidebarNameVisibility:getComputedStyle(document.querySelector('#user-name')).visibility,settingsGuestVisibility:getComputedStyle(document.querySelector('#settings-guest-actions')).visibility,profileSkeleton:!!getComputedStyle(document.querySelector('.profile-card-row'),'::before').content})""")
                page.wait_for_function("window.state?.user?.email && !document.body.classList.contains('auth-pending')",timeout=15000)
                final=page.evaluate("""()=>({email:state.user.email,tier:state.user.tier,bodyPending:document.body.classList.contains('auth-pending'),guestGroupHidden:document.querySelector('#topbar-auth-guest').hidden,userGroupVisible:!document.querySelector('#topbar-auth-user').hidden,settingsUserEmail:document.querySelector('#settings-user-email')?.textContent})""")
                route_results.append({"path":path,"initial_state":first,"hydrated_state":final})
            passed=all(row["initial_state"]["authPending"] and row["initial_state"]["guestGroupHidden"] and row["hydrated_state"]["userGroupVisible"] for row in route_results)
            payload={"routes":route_results,"auth_endpoint_deliberately_delayed_ms":1000,"page_errors":errors,"result":"passed" if passed and not errors else "failed"}
            (ROOT/"reports"/"launch-audit-v24"/"browser-id168-auth-first-paint.json").write_text(json.dumps(payload,indent=2),encoding="utf-8")
            print(json.dumps(payload,indent=2));assert payload["result"]=="passed",payload
            browser.close()
    finally: app.terminate();app.wait(timeout=5)
