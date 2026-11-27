import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
 ev={'rounds':[],'page_errors':[],'console_errors':[]}
 with TemporaryDirectory(prefix='paperplane-id275-') as td:
  app,base,_=helper.start_server(Path(td)/'data')
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(150):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.2)
   else: raise RuntimeError('local server did not start')
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for i in range(2):
     page=browser.new_page(viewport={'width':1366,'height':900})
     page.on('pageerror',lambda e:ev['page_errors'].append(str(e)))
     page.on('console',lambda m:ev['console_errors'].append(m.text) if m.type=='error' else None)
     page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
     page.wait_for_function("state.operation==='merge' && document.querySelector('#client-privacy-toggle')")
     side=page.locator('#client-privacy-toggle')
     if not side.is_checked(): side.check(force=True)
     page.wait_for_function("document.querySelector('#client-privacy-toggle').checked && document.querySelector('#privacy-mode-support').textContent.includes('runs in your browser; files stay on this device')")
     page.wait_for_timeout(300)
     browser_mode={'checked':side.is_checked(),'label':page.locator('#privacy-mode-label').inner_text(),'aria':side.get_attribute('aria-label'),'help':page.locator('#privacy-mode-support').inner_text(),'slider_bg':page.locator('#client-privacy-toggle + .toggle-slider-sm').evaluate('(e)=>getComputedStyle(e).backgroundColor')}
     page.goto(base+'/settings',wait_until='domcontentloaded')
     page.locator('#settings-tab-btn-privacy').click()
     page.locator('#pane-privacy').wait_for(state='visible')
     setting=page.locator('#settings-client-privacy-toggle')
     page.wait_for_function("document.querySelector('#settings-client-privacy-toggle')?.checked===true")
     setting_synced=setting.is_checked()
     settings_label=page.locator('.settings-privacy-toggle-row strong').inner_text()
     settings_aria=setting.get_attribute('aria-label')
     page.locator('label:has(#settings-client-privacy-toggle)').click()
     page.wait_for_function("document.querySelector('#settings-client-privacy-toggle')?.checked===false")
     page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
     page.wait_for_function("state.operation==='merge' && document.querySelector('#client-privacy-toggle')?.checked===false && document.querySelector('#privacy-mode-support').textContent.includes('uploads files for temporary server processing')")
     server_mode={'checked':page.locator('#client-privacy-toggle').is_checked(),'aria':page.locator('#client-privacy-toggle').get_attribute('aria-label'),'help':page.locator('#privacy-mode-support').inner_text(),'help':page.locator('#privacy-mode-support').inner_text(),'slider_bg':page.locator('#client-privacy-toggle + .toggle-slider-sm').evaluate('(e)=>getComputedStyle(e).backgroundColor')}
     page.goto(base+'/ocr-pdf',wait_until='domcontentloaded')
     page.wait_for_function("state.operation==='ocr'")
     ocr={'disabled':page.locator('#client-privacy-toggle').is_disabled(),'help':page.locator('#privacy-mode-support').inner_text(),'aria':page.locator('#client-privacy-toggle').get_attribute('aria-label')}
     ev['rounds'].append({'round':i+1,'browser_mode':browser_mode,'settings_synced':setting_synced,'settings_label':settings_label,'settings_aria':settings_aria,'server_mode':server_mode,'server_only_ocr':ocr})
     page.close()
    browser.close()
  finally: app.terminate();app.wait(timeout=5)
 ev['passed']=len(ev['rounds'])==2 and all(r['settings_synced'] and r['settings_label']=='Use browser processing' and r['settings_aria']=='Use browser processing for supported tools' and r['browser_mode']['label']=='Use browser processing' and r['browser_mode']['checked'] and 'runs in your browser; files stay on this device' in r['browser_mode']['help'] and 'Browser processing is on' in r['browser_mode']['aria'] and not r['server_mode']['checked'] and 'uploads files for temporary server processing' in r['server_mode']['help'] and 'files use temporary server processing' in r['server_mode']['aria'] and r['server_only_ocr']['disabled'] and 'uploads files for temporary server processing' in r['server_only_ocr']['help'] for r in ev['rounds']) and not ev['page_errors'] and not ev['console_errors']
 (ROOT/'reports/launch-audit-v24/browser-id275-processing-mode-labels.json').write_text(json.dumps(ev,indent=2),encoding='utf-8')
 print(json.dumps(ev,indent=2))
 if not ev['passed']: raise SystemExit(1)
if __name__=='__main__':main()



