from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id97-') as temp:
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/',wait_until='domcontentloaded')
                page.locator('#topbar-signin-btn').click();page.locator('#auth-modal:not([hidden])').wait_for(state='visible')
                page.locator('#link-forgot-password').click();page.locator('#auth-forgot-pane:not([hidden])').wait_for(state='visible')
                page.locator('#forgot-email').fill(identity['accounts'][0][0])
                with page.expect_response('**/api/auth/forgot-password') as event:page.locator('#forgot-submit-btn').click()
                response=event.value;assert response.status==200
                body=response.json();assert body['status']=='success' and 'If an account exists' in body['message']
                assert 'has been dispatched' not in body['message']
                reset_link=page.locator('#forgot-message a[href*="reset_token="]')
                reset_link.wait_for(state='visible',timeout=10000)
                url=reset_link.get_attribute('href');assert url and 'reset_token=' in url
                page.screenshot(path=str(OUT/f'id97-password-reset-request-round{number}.png'),full_page=True)
                page.goto(url,wait_until='domcontentloaded')
                page.locator('#reset-password-modal:not([hidden])').wait_for(state='visible',timeout=10000)
                page.locator('#reset-new-password').fill('Recovered!Password-2026')
                page.locator('#reset-confirm-password').fill('Recovered!Password-2026')
                with page.expect_response('**/api/auth/reset-password') as reset_event:page.locator('#reset-submit-btn').click()
                reset_response=reset_event.value;assert reset_response.status==200,reset_response.status
                reset_body=reset_response.json();assert reset_body.get('status')=='success',reset_body
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id97-password-reset-complete-round{number}.png'),full_page=True)
                rounds.append({'round':number,'forgot_status':response.status,'generic_message':True,'development_reset_link':True,'reset_status':reset_response.status,'reset_complete':True,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'email_delivery':'no provider configured; local code path must return failure rather than simulated success; reset link exercised using local development response'}
        (OUT/'browser-id97-password-reset.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
