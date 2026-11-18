from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id91-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
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
                response=page.goto(base+'/settings',wait_until='domcontentloaded');assert response.status==200
                settings=page.locator('#settings-modal');settings.wait_for(state='visible',timeout=15000)
                metrics=page.evaluate("""()=>({path:location.pathname,viewHidden:document.querySelector('#view-settings')?.hidden,viewTitle:document.querySelector('#view-settings h1')?.textContent,panelHost:document.querySelector('#settings-modal')?.parentElement?.id,inline:document.querySelector('#settings-modal')?.classList.contains('workspace-inline-panel'),visibleTabs:[...document.querySelectorAll('#settings-modal .settings-tab-btn')].filter(e=>e.offsetWidth>0).map(e=>e.innerText.trim()),activeView:window.state?.activeView})""")
                assert metrics['path']=='/settings' and metrics['viewHidden'] is False and metrics['panelHost']=='settings-page-content' and metrics['inline'],metrics
                assert 'Account' in ' '.join(metrics['visibleTabs']) and len(metrics['visibleTabs'])>=4,metrics
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id91-settings-deeplink-round{number}.png'),full_page=True)
                rounds.append({'round':number,'http_status':response.status,'metrics':metrics,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds};(OUT/'browser-id91-settings-deeplink.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
