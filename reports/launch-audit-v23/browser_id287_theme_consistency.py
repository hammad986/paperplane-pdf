from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id287-') as temp:
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
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/tool-desk',wait_until='domcontentloaded')
                page.wait_for_function("state.activeView==='tool-desk'")
                page.locator('#sidebar-settings-gear-btn').click();page.wait_for_function("!document.querySelector('#settings-modal').hidden")
                page.locator('#settings-tab-btn-appearance').click();page.locator('#theme-light-btn').click()
                views=[]
                for route,selector in [('/tool-desk','#view-tool-desk-directory'),('/merge-pdf','#view-tool-desk'),('/ai-intelligence','#view-ai-studio'),('/studio','#view-pdf-studio'),('/download','#view-download')]:
                    page.goto(base+route,wait_until='domcontentloaded')
                    page.wait_for_function("!document.body.classList.contains('auth-pending')")
                    page.wait_for_function('(selector)=>{const e=document.querySelector(selector);return e&&!e.hidden}',arg=selector)
                    value=page.evaluate("""selector=>{const side=document.querySelector('#sidebar'),body=getComputedStyle(document.body),content=document.querySelector(selector);return {
                        route:location.pathname,theme:document.documentElement.dataset.paperplaneTheme,bodyClasses:document.body.className,
                        sidebarBackground:getComputedStyle(side).backgroundColor,sidebarText:getComputedStyle(side).color,
                        contentBackground:getComputedStyle(content).backgroundColor,contentColor:getComputedStyle(content).color}}""",selector)
                    assert value['theme']=='light' and 'light-mode' in value['bodyClasses'],value
                    assert value['sidebarBackground']=='rgb(18, 26, 28)' and value['sidebarText']=='rgb(238, 243, 241)',value
                    views.append(value)
                assert views[0]['sidebarBackground']==views[-1]['sidebarBackground']
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id287-light-theme-round{n}.png'))
                rounds.append({'round':n,'views':views,'page_errors':errors});page.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id287-theme-consistency.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
