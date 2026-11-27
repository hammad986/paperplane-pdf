from __future__ import annotations
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'/'launch-audit-v24'/'browser-id242-default-local-processing.json'
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
 evidence={'routes':[],'merge':{},'unexpected_upload_requests':[],'page_errors':[],'console_errors':[],'live_or_production_contacted':False}
 with TemporaryDirectory(prefix='paperplane-v24-id242-') as tmp:
  temp=Path(tmp); files=[]
  for n in (1,2):
   path=temp/f'local-{n}.pdf'
   with fitz.open() as pdf:
    pdf.new_page().insert_text((72,72),f'LOCAL MODE MERGE PAGE {n}')
    pdf.save(path)
   files.append(path)
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
    context=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
    context.add_init_script("if(!sessionStorage.getItem('id242-first-load')){localStorage.removeItem('paperplane-pdf-processing-mode');sessionStorage.setItem('id242-first-load','1')}")
    page=context.new_page()
    page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
    page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
    requests=[]
    page.on('request',lambda r:requests.append({'method':r.method,'url':r.url}) if '/api/' in r.url else None)
    for route,op in [('/merge-pdf','merge'),('/split-pdf','split'),('/remove-pages','remove'),('/rotate-pdf','rotate')]:
     response=page.goto(base+route,wait_until='domcontentloaded')
     page.wait_for_function(f"window.state?.operation==='{op}'",timeout=15000)
     status=page.locator('#client-privacy-toggle').is_checked()
     mode=page.evaluate('state.clientSideMode')
     assert response and response.status==200 and status and mode,{'route':route,'status':response.status if response else None,'toggle':status,'mode':mode}
     evidence['routes'].append({'route':route,'operation':op,'http_status':response.status,'browser_processing_default':status,'client_side_mode':mode})
    page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
    page.wait_for_function("window.state?.operation==='merge' && state.clientSideMode===true")
    page.locator('label.toggle-switch-sm').filter(has=page.locator('#client-privacy-toggle')).click()
    assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")=='server'
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("window.state?.operation==='merge'",timeout=15000)
    server_mode_snapshot=page.evaluate("({path:location.pathname,operation:state.operation,clientSideMode:state.clientSideMode,stored:localStorage.getItem('paperplane-pdf-processing-mode'),checked:document.querySelector('#client-privacy-toggle')?.checked,preference:preferLocalProcessing})")
    assert server_mode_snapshot['clientSideMode'] is False and not server_mode_snapshot['checked'],server_mode_snapshot
    page.locator('label.toggle-switch-sm').filter(has=page.locator('#client-privacy-toggle')).click()
    assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')")=='local'
    page.reload(wait_until='domcontentloaded')
    page.wait_for_function("window.state?.operation==='merge' && state.clientSideMode===true")
    assert page.locator('#client-privacy-toggle').is_checked()
    evidence['preference_persists_across_reload']={'server_mode_persisted':True,'local_mode_persisted':True}
    before=len(requests)
    page.locator('#file-input').set_input_files([str(path) for path in files])
    page.wait_for_function('state.files?.length===2',timeout=10000)
    page.locator('#run-button').click()
    page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=60000)
    with page.expect_download(timeout=15000) as download_info: page.locator('#result-download-link').click()
    download=download_info.value; output=temp/'merged-local.pdf';download.save_as(output)
    with fitz.open(output) as pdf:
     page_count=pdf.page_count;text='\n'.join(p.get_text() for p in pdf)
    relevant=[r for r in requests[before:] if any(token in r['url'] for token in ('/api/jobs','/api/uploads','/api/operations','/api/process'))]
    assert page_count==2 and all(f'LOCAL MODE MERGE PAGE {n}' in text for n in (1,2)),{'pages':page_count,'text':text}
    assert not relevant,{'server_processing_requests':relevant}
    evidence['merge']={'download_name':download.suggested_filename,'output_pages':page_count,'markers_content_checked':True,'server_processing_requests':relevant}
    assert not evidence['page_errors'],evidence
    assert not evidence['console_errors'],evidence
    context.close();browser.close()
  finally:
   app.terminate()
   try: app.wait(timeout=5)
   except Exception: app.kill();app.wait(timeout=5)
 evidence['passed']=len(evidence['routes'])==4 and evidence['merge'].get('markers_content_checked') and not evidence['unexpected_upload_requests'] and not evidence['page_errors'] and not evidence['console_errors']
 OUT.write_text(json.dumps(evidence,indent=2),encoding='utf-8');print(json.dumps(evidence,indent=2))
 if not evidence['passed']: raise SystemExit(1)
if __name__=='__main__':main()
