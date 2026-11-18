from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id84-') as temp:
    app,base,_identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/tool-desk',wait_until='domcontentloaded')
            page.locator('#mobile-menu-btn').click()
            page.wait_for_function("document.querySelector('#sidebar')?.classList.contains('mobile-open')")
            page.keyboard.press('Escape')
            page.wait_for_function("!document.querySelector('#sidebar')?.classList.contains('mobile-open')")
            drawer_closed=page.locator('#sidebar').evaluate("el=>!el.classList.contains('mobile-open') && document.querySelector('#mobile-menu-btn')?.getAttribute('aria-expanded')==='false'")
            page.screenshot(path=str(OUT/'id84-mobile-drawer-after-escape.png'))

            page.set_viewport_size({'width':1366,'height':900})
            page.evaluate("window.openUpgradeModal(); window.openAuthModal('Sign in to continue.', 'login')")
            page.wait_for_function("!document.querySelector('#upgrade-modal')?.hidden && !document.querySelector('#auth-modal')?.hidden")
            before=page.evaluate("()=>({upgradeHidden:document.querySelector('#upgrade-modal').hidden,authHidden:document.querySelector('#auth-modal').hidden,upgradeZ:getComputedStyle(document.querySelector('#upgrade-modal')).zIndex,authZ:getComputedStyle(document.querySelector('#auth-modal')).zIndex})")
            page.keyboard.press('Escape')
            page.wait_for_timeout(80)
            after_first=page.evaluate("()=>({upgradeHidden:document.querySelector('#upgrade-modal').hidden,authHidden:document.querySelector('#auth-modal').hidden})")
            one_remains=(after_first['upgradeHidden'] != after_first['authHidden'])
            page.keyboard.press('Escape')
            page.wait_for_function("document.querySelector('#upgrade-modal')?.hidden && document.querySelector('#auth-modal')?.hidden")
            result={'mobile_drawer_closes_on_escape':drawer_closed,'stacked_overlays_before':before,'after_first_escape':after_first,'exactly_one_overlay_remains_after_first_escape':one_remains,'after_second_escape':page.evaluate("()=>({upgradeHidden:document.querySelector('#upgrade-modal').hidden,authHidden:document.querySelector('#auth-modal').hidden})"),'page_errors':errors}
            (OUT/'browser-id84-escape-overlay-stack.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            page.screenshot(path=str(OUT/'id84-overlays-after-first-escape.png'))
            assert drawer_closed and one_remains and result['after_second_escape']['upgradeHidden'] and result['after_second_escape']['authHidden'] and not errors
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
