from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id51-56-') as temp:
    app, base, identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2): break
            except OSError: time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            errors = []
            page = browser.new_page(viewport={'width': 1104, 'height': 850})
            page.on('pageerror', lambda error: errors.append(str(error)))

            page.goto(base + '/ai-intelligence', wait_until='domcontentloaded')
            page.wait_for_selector('#view-ai-studio:not([hidden])')
            ai_empty = page.locator('#view-ai-studio').inner_text()
            ai_empty_geometry = page.locator('#view-ai-studio').evaluate("el => ({scrollWidth:el.scrollWidth, clientWidth:el.clientWidth, rect:(r=>({x:r.x,y:r.y,width:r.width,height:r.height}))(el.getBoundingClientRect())})")
            empty_copy_geometry = page.locator('.ai-empty-copy').evaluate("el => { const r=el.getBoundingClientRect(), h=document.querySelector('.ai-chat-header').getBoundingClientRect(); const range=document.createRange(); range.selectNodeContents(el); return {x:r.x,y:r.y,width:r.width,height:r.height,headerBottom:h.bottom,fullyVisible:r.top>=h.bottom,scrollHeight:el.scrollHeight,clientHeight:el.clientHeight,textRects:range.getClientRects().length}; }")
            ai_state_ok = 'What can I help with?' in ai_empty and 'Upload PDF' in ai_empty

            page.goto(base + '/settings', wait_until='domcontentloaded')
            page.evaluate("document.querySelector('#settings-modal')?.classList.add('open')")
            storage_nav = page.locator('#settings-tab-btn-privacy small')
            storage_rect = storage_nav.bounding_box()
            pink = page.locator('#settings-tab-btn-privacy').bounding_box()
            line_count = storage_nav.evaluate("el => { const r=document.createRange(); r.selectNodeContents(el); return r.getClientRects().length; }")
            settings_label_fits = bool(storage_rect and pink and storage_rect['x'] >= pink['x'] and storage_rect['x'] + storage_rect['width'] <= pink['x'] + pink['width'] + 1 and storage_rect['y'] + storage_rect['height'] <= pink['y'] + pink['height'] + 1 and line_count <= 2)

            page.goto(base + '/tool-desk', wait_until='domcontentloaded')
            page.context.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base}])
            page.reload(wait_until='domcontentloaded')
            page.wait_for_function("document.querySelector('#quota-text')?.textContent.trim() !== 'Checking usage…'")
            quota = page.locator('#quota-container').bounding_box()
            quota_text = page.locator('#quota-text').bounding_box()
            quota_heading = page.locator('#quota-container').inner_text()
            quota_no_overflow = bool(quota and page.locator('#quota-container').evaluate('(el)=>el.scrollWidth <= el.clientWidth + 1'))

            page.goto(base + '/download', wait_until='domcontentloaded')
            page.wait_for_selector('#waitlist-form')
            waitlist_results=[]
            for platform in ('windows','macos','linux','android','ios'):
                button=page.locator(f'.btn-platform-join[data-platform="{platform}"]')
                button.click()
                page.wait_for_function("(p)=>document.querySelector('#waitlist-platform')?.value===p", arg=platform)
                waitlist_results.append({'platform':platform,'form_visible':page.locator('#waitlist-form').is_visible(),'selected_platform':page.locator('#waitlist-platform').input_value()})

            result={
                'viewport':1104,
                'ai_empty_state_visible':ai_state_ok,
                'ai_workspace_geometry':ai_empty_geometry,
                'ai_empty_copy_geometry':empty_copy_geometry,
                'settings_storage_label_rect':storage_rect,
                'settings_selected_nav_rect':pink,
                'settings_storage_label_line_count':line_count,
                'settings_storage_label_fits':settings_label_fits,
                'quota_box_rect':quota,
                'quota_text_rect':quota_text,
                'quota_text':quota_heading,
                'quota_no_overflow':quota_no_overflow,
                'paid_account_quota_label_is_honest':'No daily operation cap' in quota_heading,
                'waitlist_platform_actions':waitlist_results,
                'page_errors':errors,
            }
            (OUT/'browser-id51-52-53-55-56.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            page.screenshot(path=str(OUT/'id51-52-53-55-56-1104.png'),full_page=True)
            print(json.dumps(result,indent=2))
            assert ai_state_ok and empty_copy_geometry['fullyVisible'] and settings_label_fits and quota_no_overflow
            assert 'No daily operation cap' in quota_heading
            assert all(x['form_visible'] and x['selected_platform']==x['platform'] for x in waitlist_results)
            assert not errors
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
