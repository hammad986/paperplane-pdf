from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-pricing-layout-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                context=browser.new_context(viewport={'width':1920,'height':1080})
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                response=page.goto(base+'/pricing',wait_until='domcontentloaded')
                assert response and response.status==200
                page.locator('#view-pricing').wait_for(state='visible')
                cards=page.locator('#pricing-page-content .pricing-tier-card')
                page.wait_for_function("document.querySelectorAll('#pricing-page-content .pricing-tier-card').length >= 4",timeout=10000)
                desktop=page.evaluate("""() => {const root=document.querySelector('#view-pricing'),card=document.querySelector('#pricing-page-content .pricing-modal-card'),grid=document.querySelector('#pricing-page-content .pricing-tiers-grid'),text=root.innerText;const r=e=>{const x=e.getBoundingClientRect();return {x:x.x,y:x.y,width:x.width,height:x.height,right:x.right,bottom:x.bottom}};return {view:r(root),card:r(card),grid:{...r(grid),columns:getComputedStyle(grid).gridTemplateColumns.split(' ').length},tiers:document.querySelectorAll('#pricing-page-content .pricing-tier-card').length,pay:[...document.querySelectorAll('#pricing-page-content button')].filter(b=>/Pay /.test(b.innerText)).map(b=>({text:b.innerText.trim(),...r(b)})),modalOverlay:[...document.querySelectorAll('.modal-overlay')].some(e=>!e.hidden&&getComputedStyle(e).display!=='none'),stalePrices:['₹750','$299/month'].filter(x=>text.includes(x)),currentPrices:['₹19','₹49','₹299'].every(x=>text.includes(x))}}""")
                assert desktop['tiers']==4 and desktop['grid']['columns']==2,desktop
                assert not desktop['stalePrices'] and desktop['currentPrices'],desktop
                assert not desktop['modalOverlay'],desktop
                assert desktop['view']['width']<=1920 and desktop['card']['x']>=0 and desktop['card']['right']<=1920,desktop
                assert len(desktop['pay'])==3 and all(x['x']>=0 and x['right']<=1920 for x in desktop['pay']),desktop
                page.evaluate("const e=document.querySelector('.main-area');e.scrollTop=400")
                desktop_after_scroll=page.locator('#pricing-page-content button').evaluate_all("els=>els.filter(b=>/^Pay /.test(b.innerText.trim())).map(b=>{const r=b.getBoundingClientRect();return {text:b.innerText.trim(),x:r.x,y:r.y,width:r.width,height:r.height,right:r.right,bottom:r.bottom}})")
                assert len(desktop_after_scroll)==3 and all(x['x']>=0 and x['right']<=1920 and x['y']>=0 and x['bottom']<=1080 for x in desktop_after_scroll),desktop_after_scroll
                page.set_viewport_size({'width':390,'height':844})
                mobile=[]
                for button in page.locator('#pricing-page-content button').all():
                    if button.inner_text().strip().startswith('Pay '):
                        button.scroll_into_view_if_needed()
                        box=button.bounding_box()
                        assert box and box['x']>=0 and box['x']+box['width']<=390 and box['y']>=0 and box['y']+box['height']<=844,(button.inner_text(),box)
                        mobile.append({'text':button.inner_text().strip(),'box':box})
                assert len(mobile)==3 and not errors,(mobile,errors)
                page.screenshot(path=str(OUT/f'ids141-177-pricing-round{n}.png'),full_page=True)
                rounds.append({'round':n,'desktop':desktop,'desktopAfterOneScroll':desktop_after_scroll,'mobilePayButtons':mobile,'pageErrors':errors})
                context.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-ids141-177-pricing-layout.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
