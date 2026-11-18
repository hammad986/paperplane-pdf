from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id222-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True); rounds=[]
            for n in (1,2):
                context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True); page=context.new_page(); errors=[]
                page.on('pageerror',lambda err:errors.append(str(err)))
                page.goto(base+'/',wait_until='domcontentloaded'); page.wait_for_function("!document.body.classList.contains('auth-pending')")
                top=page.evaluate("""()=>({login:getComputedStyle(document.querySelector('#topbar-signin-btn')).display,register:getComputedStyle(document.querySelector('#topbar-register-btn')).display,overflow:document.documentElement.scrollWidth})""")
                page.locator('#mobile-menu-btn').click(); page.wait_for_function("document.querySelector('#sidebar')?.classList.contains('mobile-open')")
                profile=page.locator('#sidebar-profile-card'); profile.click(); page.wait_for_function("!document.querySelector('#settings-modal')?.hidden")
                sign_in=page.locator('#settings-signin-btn'); register=page.locator('#settings-register-btn')
                actions={'signin_visible':sign_in.is_visible(),'register_visible':register.is_visible(),'signin_text':sign_in.inner_text().strip(),'register_text':register.inner_text().strip()}
                sign_in.click(); page.wait_for_function("!document.querySelector('#auth-modal')?.hidden")
                auth={'visible':page.locator('#auth-modal').is_visible(),'title':page.locator('#auth-modal-title').inner_text().strip(),'viewportWidth':page.evaluate('innerWidth'),'scrollWidth':page.evaluate('document.documentElement.scrollWidth')}
                assert top['login']!='none' and actions['signin_visible'] and actions['register_visible'] and auth['visible'] and auth['scrollWidth']==390 and not errors,(top,actions,auth,errors)
                page.screenshot(path=str(OUT/f'id222-mobile-signin-round{n}.png'))
                rounds.append({'round':n,'topbar':top,'drawer_account_actions':actions,'auth_modal':auth,'page_errors':errors}); context.close()
            browser.close()
        result={'rounds':rounds}; (OUT/'browser-id222-mobile-signin.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
    finally: app.terminate(); app.wait(timeout=5)
