from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id80-') as temp:
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            results=[]
            for width in (320,390):
                page=browser.new_page(viewport={'width':width,'height':844},is_mobile=True,has_touch=True)
                errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
                page.context.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base}])
                page.goto(base+'/settings',wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('#settings-modal')?.classList.contains('open') || document.querySelector('#settings-page-content')?.hidden===false",timeout=10000)
                page.evaluate("document.querySelector('#settings-modal')?.classList.add('open')")
                page.wait_for_timeout(150)
                metrics=page.evaluate("()=>{const modal=document.querySelector('#settings-modal');const content=document.querySelector('#settings-page-content');const nav=document.querySelector('.settings-tabs');const pane=document.querySelector('.settings-content');const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom,scrollWidth:e.scrollWidth,clientWidth:e.clientWidth}};return{modal:rect(modal),content:rect(content),nav:rect(nav),pane:rect(pane),documentWidth:document.documentElement.scrollWidth,viewport:innerWidth,tabs:[...document.querySelectorAll('.settings-tab-btn')].map(x=>({text:x.innerText.trim(),rect:rect(x),visible:!!(x.offsetWidth||x.offsetHeight)}))}}")
                for tab in page.locator('.settings-tab-btn').all():
                    if tab.is_visible():
                        tab.click()
                        page.wait_for_timeout(30)
                page.screenshot(path=str(OUT/f'id80-settings-{width}.png'),full_page=True)
                metrics['all_tabs_clickable']=all(x['visible'] and x['rect']['x']>=0 and x['rect']['right']<=width+1 for x in metrics['tabs'])
                metrics['modal_within_viewport']=bool(metrics['modal'] and metrics['modal']['x']>=0 and metrics['modal']['right']<=width+1)
                metrics['tab_strip_no_horizontal_overflow']=bool(metrics['nav'] and metrics['nav']['scrollWidth']<=metrics['nav']['clientWidth']+1)
                metrics['page_errors']=errors
                results.append(metrics)
                print(json.dumps({'width':width,**metrics},indent=2))
                assert metrics['modal_within_viewport'] and metrics['all_tabs_clickable'] and not errors
                page.close()
            (OUT/'browser-id80-mobile-settings.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
