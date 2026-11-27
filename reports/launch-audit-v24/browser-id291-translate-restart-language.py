import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
 ev={'rounds':[],'page_errors':[],'console_errors':[]}
 with TemporaryDirectory(prefix='paperplane-id291-') as td:
  tdp=Path(td); source=tdp/'translate-source.pdf'
  d=fitz.open(); p=d.new_page(); p.insert_text((72,72),'ID291 translation reset fixture'); d.save(source); d.close()
  app,base,_=helper.start_server(tdp/'data')
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
     resp=page.goto(base+'/translate-pdf',wait_until='domcontentloaded')
     operation=page.evaluate('state.operation')
     page.locator('#file-input').set_input_files(str(source))
     page.wait_for_function("state.files?.some(file=>file.name==='translate-source.pdf')",timeout=30000)
     page.locator('#target_language').select_option(label='fr (French)')
     selected=page.locator('#target_language').input_value()
     page.evaluate("""()=>showDownloadResult({output_name:'translated-fr.pdf',output_size:1200,page_count:1},'/api/jobs/id291-controlled-result/download')""")
     page.locator('#result-restart-btn').wait_for(state='visible')
     page.locator('#result-restart-btn').click()
     page.wait_for_function("document.querySelector('#result').hidden && state.files.length===0")
     after=page.locator('#target_language').input_value()
     ev['rounds'].append({'round':i+1,'http_status':resp.status,'operation':operation,'selected_before':selected,'selected_after':after,'files_cleared':page.evaluate('state.files.length===0'),'result_cleared':page.locator('#result').is_hidden(),'passed':selected==after=='fr (French)' and operation=='translate' and page.evaluate('state.files.length===0') and page.locator('#result').is_hidden()})
     page.close()
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
 ev['passed']=len(ev['rounds'])==2 and all(r['passed'] and r['http_status']==200 for r in ev['rounds']) and not ev['page_errors'] and not ev['console_errors']
 (ROOT/'reports/launch-audit-v24/browser-id291-translate-restart-language.json').write_text(json.dumps(ev,indent=2),encoding='utf-8')
 print(json.dumps(ev,indent=2))
 if not ev['passed']: raise SystemExit(1)
if __name__=='__main__': main()
