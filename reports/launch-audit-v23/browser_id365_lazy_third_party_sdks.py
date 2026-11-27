from __future__ import annotations

import json, socket, sys, time

from pathlib import Path

from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]

OUT=ROOT/'reports'/'launch-audit-v23'/'browser-id365-lazy-third-party-sdks.json'
EXTERNAL_BASE=__import__('os').environ.get('PAPERPLANE_TEST_BASE','').rstrip('/')

sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))

import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-lazy-sdks-') as temporary:

    app,base,_=helper.start_server(Path(temporary)/'data')

    try:

        for _ in range(150):

            try:

                with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break

            except OSError: time.sleep(.2)

        else: raise RuntimeError('Local Paperplane failed to start')

        with sync_playwright() as p:

            browser=p.chromium.launch(channel='chrome',headless=True)

            context=browser.new_context(viewport={'width':1366,'height':900})

            requests=[]; auth_config_requests=[]; errors=[]

            page=context.new_page()

            page.on('pageerror',lambda error:errors.append(str(error)))

            def google(route):

                requests.append('google')

                route.fulfill(status=200,content_type='application/javascript',body="window.google={accounts:{id:{initialize(c){window.__gisInitialized=!!c.client_id},prompt(){window.__gisPrompted=true}}}};")

            def cashfree(route):

                requests.append('cashfree')

                route.fulfill(status=200,content_type='application/javascript',body="window.Cashfree=(options)=>{window.__cashfreeMode=options.mode;return {checkout:async checkoutOptions=>{window.__cashfreeCheckout=checkoutOptions}}};")

            context.route('https://accounts.google.com/gsi/client',google)

            context.route('https://sdk.cashfree.com/js/v3/cashfree.js',cashfree)

            context.route('**/api/auth/config',lambda route:(auth_config_requests.append('auth-config'),route.fulfill(status=200,content_type='application/json',body=json.dumps({'google_enabled':True,'google_client_id':'synthetic-client-id'}))))

            context.route('**/api/billing/checkout-session',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'payment_session_id':'synthetic-session','environment':'SANDBOX'})))

            page.goto(base+'/',wait_until='domcontentloaded')


            page.wait_for_timeout(1200)

            initial={'external_requests':list(requests),'auth_config_requests':list(auth_config_requests),'google_global_present':page.evaluate('Boolean(window.google?.accounts?.id)'),'cashfree_global_present':page.evaluate("typeof window.Cashfree==='function'")}

            assert not requests and not auth_config_requests and not initial['google_global_present'] and not initial['cashfree_global_present'],initial

            page.locator('#topbar-signin-btn').click()

            page.wait_for_function('window.__gisInitialized===true',timeout=10000)

            page.locator('#google-auth-btn').click()

            page.wait_for_function('window.__gisPrompted===true',timeout=5000)

            assert requests==['google'],requests
            page.locator('#close-auth-modal').click()

            page.evaluate("window.state.user={authenticated:true,user_id:'synthetic-user',tier:'free'}")

            page.locator('#topbar-upgrade-btn').click()

            page.locator('#student-cashfree-checkout-btn').click()

            page.wait_for_function('Boolean(window.__cashfreeCheckout)',timeout=10000)

            assert requests==['google','cashfree'],requests

            assert page.evaluate('window.__cashfreeMode')=='sandbox'

            assert page.evaluate('window.__cashfreeCheckout.paymentSessionId')=='synthetic-session'

            assert not errors,errors

            result={'initial':initial,'auth_config_requests_after_use':auth_config_requests,'sdk_requests_after_use':requests,'google_prompted':True,'cashfree_mode':'sandbox','payment_api_mocked':True,'payment_submitted':False,'page_errors':errors}

            browser.close()

        OUT.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')

        print(json.dumps(result,indent=2))

    finally:

        app.terminate()

        try: app.wait(timeout=15)

        except Exception: app.kill()

