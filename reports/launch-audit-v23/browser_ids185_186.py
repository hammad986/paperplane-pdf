from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path.cwd(); OUT=ROOT/'reports'/'launch-audit-v23'
sys.path.insert(0,str(OUT.parent/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id185-186-') as tmp:
    tmp=Path(tmp); src=tmp/'source.pdf'
    with fitz.open() as d:
        for i in range(5): d.new_page().insert_text((72,72),f'ID185 SOURCE PAGE {i+1}')
        d.save(src)
    app,base,_=helper.start_server(tmp/'data')
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
            except OSError: time.sleep(.15)
        rows=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for r in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True)
                errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
                toggle=page.locator('#client-privacy-toggle')
                assert toggle.is_checked(), 'local default should be on'
                page.locator('label.toggle-switch-sm').first.click()
                page.wait_for_timeout(100)
                assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")== 'server'
                assert not toggle.is_checked(), 'server preference should stick after control sync'
                assert 'temporary server processing' in toggle.get_attribute('aria-label')
                page.locator('label.toggle-switch-sm').first.click()
                page.wait_for_timeout(100)
                assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")== 'local'
                assert toggle.is_checked()
                page.locator('#file-input').set_input_files(str(src)); page.wait_for_function("!document.querySelector('#run-button').disabled")
                page.locator('#run-button').click(); page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
                download_url=page.locator('#result-download-link').get_attribute('href')
                assert download_url.startswith('blob:'), download_url
                start=time.monotonic(); response=page.goto(base+'/faq',wait_until='domcontentloaded',timeout=15000); duration=round(time.monotonic()-start,3)
                assert response and response.status==200
                page.locator('body').wait_for(state='visible'); page.wait_for_timeout(100)
                assert page.locator('body').inner_text().strip()
                assert not errors, errors
                rows.append({'round':r,'server_mode_toggle':{'off_persisted':True,'on_persisted':True,'aria_updated':True},'merge_output_blob_created':True,'navigation_http':response.status,'navigation_seconds':duration,'faq_visible':True,'page_errors':errors})
                page.close()
            browser.close()
        (OUT/'browser-ids185-186.json').write_text(json.dumps(rows,indent=2),encoding='utf-8'); print(json.dumps(rows,indent=2))
    finally:
        app.terminate(); app.wait(timeout=5)

