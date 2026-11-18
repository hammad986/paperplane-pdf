from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id289-') as temp:
    rounds=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for n in (1,2):
            app,base,identity=helper.start_server(Path(temp)/f'db-{n}')
            try:
                port=int(base.rsplit(':',1)[1])
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                    except OSError:time.sleep(.15)
                email,token=identity['accounts'][0]
                context=browser.new_context(viewport={'width':1366,'height':900})
                context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
                page.wait_for_function("!!state.user?.user_id")
                first=page.locator('#quota-text').inner_text()
                page.wait_for_function("!document.querySelector('#quota-text').textContent.includes('Checking')",timeout=8000)
                resolved=page.locator('#quota-text').inner_text()
                assert 'Checking' not in resolved and ('No daily operation cap' in resolved or 'unlimited' in resolved.lower()),(first,resolved)
                page.locator('#sidebar-settings-gear-btn').click();page.wait_for_function("!document.querySelector('#settings-modal').hidden")
                settings=page.locator('#settings-quota-text').inner_text()
                assert 'Checking' not in settings and ('No daily operation cap' in settings or 'unlimited' in settings.lower()),settings
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id289-quota-round{n}.png'))
                rounds.append({'round':n,'first_paint':first,'resolved_sidebar':resolved,'settings':settings,'page_errors':errors})
                context.close()
            finally:app.terminate();app.wait(timeout=5)
        browser.close()
    result={'rounds':rounds};(OUT/'browser-id289-quota-label.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
