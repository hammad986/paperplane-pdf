from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-290-291-') as temp:
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
            for n in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/history',wait_until='domcontentloaded')
                page.wait_for_function("state.activeView==='history'")
                history_title=page.title()
                assert 'Temporary results' in history_title,history_title
                page.evaluate("switchWorkspaceView('legal','privacy')")
                privacy={'path':page.evaluate('location.pathname'),'title':page.title(),'view':page.evaluate('state.activeView')}
                assert privacy=={'path':'/privacy','title':'Privacy Policy | Paperplane','view':'legal'},privacy
                page.locator('#full-legal-tab-terms').click()
                terms={'title':page.title(),'active':page.locator('#full-legal-tab-terms').get_attribute('class')}
                assert terms['title']=='Terms of Service | Paperplane' and 'active' in terms['active'],terms
                page.goto(base+'/translate-pdf',wait_until='domcontentloaded')
                page.wait_for_function("state.operation==='translate'")
                page.locator('#target_language').select_option('fr (French)')
                assert page.locator('#target_language').input_value()=='fr (French)'
                page.evaluate("renderTranslationResult(new Blob(['controlled translation fixture'],{type:'application/pdf'}),'source.pdf','fr',100,0,'layout')")
                page.locator('#result-restart-btn').click()
                page.wait_for_function("document.querySelector('#target_language')?.value==='fr (French)' && document.querySelector('#result').hidden")
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id290-291-round{n}.png'))
                rounds.append({'round':n,'history_title':history_title,'privacy':privacy,'terms':terms,
                    'translation_target_after_process_another':page.locator('#target_language').input_value(),'page_errors':errors})
                page.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-ids290-291.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
