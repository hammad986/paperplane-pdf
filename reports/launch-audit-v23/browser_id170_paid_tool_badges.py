from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sqlite3, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
ROUTES=[item['route'] for item in json.loads((OUT/'route-layout-matrix.json').read_text(encoding='utf-8'))['copy_routes'] if item['route'] not in ('/','/pricing')]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id170-') as temp:
    app,base,identities=helper.start_server(Path(temp)/'data')
    try:
        email,token=identities['accounts'][0]
        # Convert only this disposable test identity to the legacy Pro tier.
        with sqlite3.connect(Path(temp)/'data'/'paperplane.sqlite3') as connection:
            connection.execute("UPDATE users SET tier='pro', subscription_status='active' WHERE email=?",(email,))
            connection.commit()
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                checks=[]
                for route in ROUTES:
                    response=page.goto(base+route,wait_until='domcontentloaded',timeout=20000)
                    assert response and response.status==200,(route,response.status if response else None)
                    badge=page.locator('#tool-tier-badge')
                    page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=10000)
                    if page.url.endswith('/ai-intelligence'):
                        visible_badge=badge.evaluate("e=>e.getClientRects().length>0") if badge.count() else False
                        assert not visible_badge and 'Free Guest Tool' not in page.locator('body').inner_text(),(route,page.url)
                        checks.append({'route':route,'status':response.status,'workspace':'AI Intelligence','guestBadgeVisible':False})
                        print(f"checked {n}:{route} -> AI Intelligence",flush=True)
                        continue
                    try:
                        page.wait_for_function("() => {const e=document.querySelector('#tool-tier-badge');return e&&(/Legacy Pro|no daily operation cap/i.test(e.textContent))}",timeout=5000)
                    except Exception as error:
                        raise AssertionError({'route':route,'url':page.url,'badge':badge.inner_text() if badge.count() else None,'bodyClasses':page.locator('body').get_attribute('class')}) from error
                    label=badge.inner_text().strip()
                    assert 'Free Guest Tool' not in label and 'Free Account Required' not in label,(route,label)
                    assert 'Student & Educator' in label or 'no daily operation cap' in label,(route,label)
                    checks.append({'route':route,'status':response.status,'badge':label})
                    print(f"checked {n}:{route}",flush=True)
                assert not errors,errors
                rounds.append({'round':n,'accountTier':'legacy_pro','seedTier':'student_pro','routeCount':len(checks),'checks':checks,'pageErrors':errors})
                context.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-id170-paid-tool-badges.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'rounds':[{'round':r['round'],'accountTier':r['accountTier'],'routeCount':r['routeCount'],'pageErrors':r['pageErrors']} for r in rounds]},indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
