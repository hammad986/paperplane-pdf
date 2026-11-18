from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id347-') as temp:
    app,base,identity=helper.start_server(Path(temp)/'db')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            results=[]
            for width,height,zoom in [(390,844,1),(390,500,1),(390,500,2)]:
                context=browser.new_context(viewport={'width':width,'height':height},is_mobile=True,has_touch=True)
                context.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base,'httpOnly':True}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/',wait_until='domcontentloaded');page.wait_for_timeout(400)
                page.evaluate("openSettingsModal('account')")
                if zoom==2:page.evaluate("document.documentElement.style.fontSize='200%'")
                page.evaluate("document.querySelector('#settings-user-email').textContent='a.very.long.account.owner.email.for.mobile.layout.testing@example-customer-domain.example'")
                nav=page.locator('.settings-tabs');tabs=page.locator('.settings-tab-btn');details=[]
                for index in range(tabs.count()):
                    tab=tabs.nth(index);tab.scroll_into_view_if_needed();tab.click();page.wait_for_timeout(50)
                    pane=page.locator('.settings-pane:not([hidden])');details.append({'tab':tab.get_attribute('data-tab'),'active':pane.get_attribute('id'),'visible':pane.is_visible()})
                account=page.locator('#settings-tab-btn-account');account.scroll_into_view_if_needed();account.click();page.wait_for_timeout(50)
                pane=page.locator('#pane-account')
                password=page.locator('#settings-old-password')
                keyboard_case=None
                if password.is_visible():
                    password.scroll_into_view_if_needed();password.focus()
                    keyboard_case=page.evaluate("""()=>{const m=document.querySelector('.settings-modal-card'),p=document.querySelector('#settings-old-password'),r=p.getBoundingClientRect(),mr=m.getBoundingClientRect();return {focused:document.activeElement===p,input:{top:r.top,bottom:r.bottom,left:r.left,right:r.right},modal:{top:mr.top,bottom:mr.bottom,left:mr.left,right:mr.right},viewport:{width:innerWidth,height:innerHeight},docWidth:document.documentElement.scrollWidth}}""")
                metrics=page.evaluate("""()=>{const m=document.querySelector('.settings-modal-card'),n=document.querySelector('.settings-tabs'),c=document.querySelector('.settings-content');const r=e=>{let x=e.getBoundingClientRect();return {left:x.left,right:x.right,top:x.top,bottom:x.bottom,width:x.width,height:x.height,clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,clientHeight:e.clientHeight,scrollHeight:e.scrollHeight}};return {modal:r(m),nav:r(n),content:r(c),tabRects:[...document.querySelectorAll('.settings-tab-btn')].map(e=>({key:e.dataset.tab,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right,width:e.getBoundingClientRect().width})),documentWidth:document.documentElement.scrollWidth,viewport:{width:innerWidth,height:innerHeight}}}""")
                assert all(x['visible'] for x in details),details
                assert metrics['modal']['left']>=0 and metrics['modal']['right']<=metrics['viewport']['width']+1,metrics
                assert metrics['nav']['scrollWidth']>=metrics['nav']['clientWidth'],metrics
                assert metrics['documentWidth']<=metrics['viewport']['width']+1,metrics
                if keyboard_case:assert keyboard_case['focused'] and keyboard_case['input']['right']<=keyboard_case['viewport']['width']+1,keyboard_case
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id347-settings-{width}-{height}-zoom{zoom}.png'))
                results.append({'viewport':[width,height],'zoom':zoom,'tabs':details,'layout':metrics,'keyboard_emulation':keyboard_case,'errors':errors})
                context.close()
            browser.close()
            (OUT/'browser-id347-mobile-settings.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
            print(json.dumps(results,indent=2))
    finally:app.terminate();app.wait(timeout=5)
