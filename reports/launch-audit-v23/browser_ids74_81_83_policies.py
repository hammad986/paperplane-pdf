from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-ids74-81-83-') as temp:
  app,base,_=helper.start_server(Path(temp)/'data')
  try:
    port=int(base.rsplit(':',1)[1])
    for _ in range(100):
        try:
            with socket.create_connection(('127.0.0.1',port),timeout=.2):break
        except OSError:time.sleep(.15)
    runs=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for number in (1,2):
            context=browser.new_context(viewport={'width':1366,'height':900})
            page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
            terms=page.goto(base+'/terms',wait_until='domcontentloaded');assert terms.status==200
            terms_text=page.locator('#pane-terms').inner_text() if page.locator('#pane-terms').count() else page.locator('body').inner_text()
            assert 'does not provide automatic renewals or an in-app subscription cancellation control' in terms_text
            assert 'cancellation conditions have not been approved' in terms_text
            page.goto(base+'/',wait_until='domcontentloaded')
            page.locator('#sidebar-settings-gear-btn').click()
            page.locator('#settings-tab-btn-billing').click()
            billing=page.locator('#pane-billing').inner_text()
            assert 'Upgrade' in billing and 'Cancel' not in billing
            resp_headers=[];page.on('response',lambda response: resp_headers.extend(response.headers_array()) if response.url==base+'/' else None)
            main=page.goto(base+'/',wait_until='domcontentloaded');assert main.status==200
            if not resp_headers:resp_headers=main.headers_array()
            names=[h['name'].lower() for h in resp_headers]
            security={header:names.count(header) for header in ('x-frame-options','x-content-type-options','referrer-policy')}
            assert all(count<=1 for count in security.values()),security
            page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
            debug=page.locator('#ai-test-connection-btn')
            visibility={'hidden_property':debug.evaluate('(e)=>e.hidden'),'visible':debug.is_visible()}
            assert visibility['hidden_property'] and not visibility['visible'],visibility
            assert not errors,errors
            page.screenshot(path=str(OUT/f'ids74-81-83-round{number}.png'),full_page=True)
            runs.append({'round':number,'terms_cancellation_disclosure':True,'billing_has_upgrade_no_cancel':'Upgrade' in billing and 'Cancel' not in billing,'security_header_counts':security,'ai_connection_debug_link':visibility,'page_errors':errors})
            context.close()
        browser.close()
    data={'rounds':runs};(OUT/'browser-ids74-81-83-policies.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
  finally:
    app.terminate();app.wait(timeout=5)
