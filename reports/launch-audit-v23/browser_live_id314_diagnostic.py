from pathlib import Path
import json
from playwright.sync_api import sync_playwright
BASE='https://paperplane.qd.je'
OUT=Path('reports/launch-audit-v23')
FIXTURE=OUT/'fixtures/v23-id2-69-pages.pdf'
evidence={'base':BASE,'fixture_pages':69,'network':[],'page_errors':[]}
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(accept_downloads=True)
    page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
    page.on('request',lambda r:evidence['network'].append({'event':'request','url':r.url,'method':r.method}) if '/api/ai/summarize' in r.url else None)
    page.on('response',lambda r:evidence['network'].append({'event':'response','url':r.url,'status':r.status}) if '/api/ai/summarize' in r.url else None)
    r=page.goto(BASE+'/ai-intelligence',wait_until='domcontentloaded',timeout=45000)
    evidence['page_status']=r.status if r else None
    evidence['loaded_app_js']=page.locator('script[src*="app.js"]').get_attribute('src')
    page.locator('#ai-file-input').set_input_files(str(FIXTURE))
    page.locator('#ai-active-doc-bar').wait_for(state='visible',timeout=30000)
    button=page.locator('#trigger-summary-btn')
    evidence['button_before']={'visible':button.is_visible(),'enabled':button.is_enabled(),'text':button.inner_text()}
    button.click()
    try:
        page.wait_for_response(lambda r:'/api/ai/summarize' in r.url,timeout=60000)
    except Exception as e:
        evidence['wait_error']=str(e)
    evidence['button_after']={'visible':button.is_visible(),'enabled':button.is_enabled(),'text':button.inner_text()}
    evidence['summary_text']=page.locator('#summary-display').inner_text()[:1000]
    evidence['badge']=page.locator('#summary-mode-badge').inner_text()
    evidence['requests_seen']=evidence['network']
    evidence['page_errors']=evidence['page_errors']
    page.screenshot(path=str(OUT/'browser-live-id314-diagnostic.png'),full_page=True)
    browser.close()
(OUT/'browser-live-id314-diagnostic.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
