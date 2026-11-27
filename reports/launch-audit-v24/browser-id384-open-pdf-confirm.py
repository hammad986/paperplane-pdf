from __future__ import annotations
import base64,json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
  with TemporaryDirectory(prefix='paperplane-v24-id384-') as td:
    tmp=Path(td); src=tmp/'open-test.pdf'
    with fitz.open() as d:
      p=d.new_page(); p.insert_text((72,90),'ID384 open action marker'); d.save(src)
    encoded=base64.b64encode(src.read_bytes()).decode(); app,base,_=helper.start_server(tmp/'data')
    evidence={'checks':[],'page_errors':[],'console_errors':[]}
    try:
      port=int(base.rsplit(':',1)[1])
      for _ in range(150):
        try:
          with socket.create_connection(('127.0.0.1',port),timeout=.2): break
        except OSError: time.sleep(.2)
      with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True); page=browser.new_page(viewport={'width':390,'height':844})
        page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
        page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
        response=page.goto(base+'/studio',wait_until='domcontentloaded')
        await_loaded=page.evaluate('''async b64=>{const a=Uint8Array.from(atob(b64),c=>c.charCodeAt(0)); const f=new File([a],'id384-open-test.pdf',{type:'application/pdf'}); return await loadDocumentIntoStudio(f)}''',encoded)
        page.wait_for_function('state.studio.pdfDoc && state.studio.totalCount===1',timeout=20000)
        page.evaluate("switchWorkspaceView('studio')")
        page.locator('#view-pdf-studio:not([hidden])').wait_for(timeout=5000)
        with page.expect_file_chooser(timeout=5000) as fc_info:
          page.locator('#studio-upload-btn').click()
        chooser=fc_info.value
        dialog_visible=page.locator('.app-confirm-dialog:visible').count()>0
        evidence['checks'].append({'route_status':response.status if response else None,'fixture_loaded':await_loaded,'studio_page_count':page.evaluate('state.studio.totalCount'),'open_pdf_opens_file_chooser':chooser is not None,'unexpected_confirmation_visible':dialog_visible,'confirm_copy':page.locator('.app-confirm-dialog p').inner_text() if dialog_visible else None})
        evidence['checks'].append({'studio_close_button_visible_after_open':page.locator('#studio-close-doc-btn').is_visible(),'studio_view_visible_after_open':page.locator('#view-pdf-studio').is_visible()})
        browser.close()
    finally: app.terminate(); app.wait(timeout=5)
    evidence['result']=len(evidence['checks'])==2 and evidence['checks'][0]['route_status']==200 and evidence['checks'][0]['fixture_loaded'] and evidence['checks'][0]['open_pdf_opens_file_chooser'] and not evidence['checks'][0]['unexpected_confirmation_visible'] and evidence['checks'][1]['studio_view_visible_after_open'] and not evidence['page_errors'] and not evidence['console_errors']
    out=Path(__file__).parent/'browser-id384-open-pdf-confirm.json'; out.write_text(json.dumps(evidence,indent=2),encoding='utf-8'); print(json.dumps(evidence,indent=2))
    if not evidence['result']: raise SystemExit(1)
if __name__=='__main__': main()

