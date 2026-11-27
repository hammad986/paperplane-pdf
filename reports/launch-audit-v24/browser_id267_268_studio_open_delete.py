from __future__ import annotations
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'/'launch-audit-v24'/'browser-id267-268-studio-open-delete.json'
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
 evidence={'rounds':[],'page_errors':[],'console_errors':[],'live_or_production_contacted':False}
 with TemporaryDirectory(prefix='paperplane-v24-id267-268-') as tmp:
  temp=Path(tmp); fixture=temp/'ten-pages.pdf'
  with fitz.open() as pdf:
   for n in range(1,11): pdf.new_page().insert_text((72,72),f'OPEN STUDIO PAGE {n}')
   pdf.save(fixture)
  app,base,_=helper.start_server(temp/'data')
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(150):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.2)
   else: raise RuntimeError('local server did not start')
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for round_no in (1,2):
     ctx=browser.new_context(viewport={'width':1366,'height':900})
     page=ctx.new_page()
     page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
     page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
     response=page.goto(base+'/studio',wait_until='domcontentloaded')
     page.locator('#studio-file-input').set_input_files(str(fixture))
     page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='10'",timeout=45000)
     page.wait_for_function("document.querySelector('.pdf-page-canvas[data-rendered=true]')?.width>1",timeout=20000)
     record={'round':round_no,'route_status':response.status if response else None,'loaded_page_count':page.locator('#page-total-indicator').inner_text(),'canvas_rendered':True}
     if round_no==2:
      page.locator('#editor-delete-page-btn').click()
      dialog=page.locator('dialog.app-confirm-dialog')
      dialog.wait_for(state='visible',timeout=5000)
      dialog.locator('.app-confirm-accept').click()
      try:
       page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='9'",timeout=45000)
       record.update(toolbar_delete_result='deleted',page_count_after=page.locator('#page-total-indicator').inner_text())
      except Exception:
       record.update(toolbar_delete_result='not deleted',page_count_after=page.locator('#page-total-indicator').inner_text(),toast=page.locator('.toast-notice').inner_text() if page.locator('.toast-notice').count() else '')
      evidence['rounds'].append(record)
      if record['toolbar_delete_result']!='deleted': raise AssertionError(record)
     else: evidence['rounds'].append(record)
     assert not evidence['page_errors'],evidence
     assert not evidence['console_errors'],evidence
     ctx.close()
    browser.close()
  finally:
   app.terminate()
   try: app.wait(timeout=5)
   except Exception: app.kill(); app.wait(timeout=5)
 evidence['passed']=len(evidence['rounds'])==2 and evidence['rounds'][-1].get('toolbar_delete_result')=='deleted' and not evidence['page_errors'] and not evidence['console_errors']
 OUT.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2))
 if not evidence['passed']: raise SystemExit(1)
if __name__=='__main__':main()
