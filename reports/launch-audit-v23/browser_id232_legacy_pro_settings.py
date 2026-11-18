from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id232-') as temp:
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);rounds=[]
            token=identity['accounts'][0][1]
            for n in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page.goto(base+'/',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=15000)
                page.evaluate("window.updateBillingUI({tier:'pro',is_pro:true,is_dev:false,usage_today:0,daily_limit:10})")
                page.wait_for_function("document.querySelector('#settings-tier-name')?.textContent==='Legacy Pro'",timeout=10000)
                page.locator('#sidebar-profile-card').click();page.locator('#settings-tab-btn-billing').click()
                pane=page.locator('#pane-billing');pane.wait_for(state='visible')
                details=page.evaluate("""()=>({tier:document.querySelector('#settings-tier-name')?.textContent,badge:document.querySelector('#settings-tier-badge')?.textContent,upgradeDisplay:getComputedStyle(document.querySelector('#settings-upgrade-plan-btn')).display,upgradeVisible:document.querySelector('#settings-upgrade-plan-btn').getClientRects().length>0})""")
                assert details['tier']=='Legacy Pro' and not details['upgradeVisible'] and not errors,(details,errors)
                page.screenshot(path=str(OUT/f'id232-legacy-pro-round{n}.png'))
                rounds.append({'round':n,'plan':details,'page_errors':errors});page.context.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id232-legacy-pro-settings.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
