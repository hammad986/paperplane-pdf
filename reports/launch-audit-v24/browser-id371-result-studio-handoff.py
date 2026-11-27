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
  with TemporaryDirectory(prefix='paperplane-v24-id371-') as td:
    tmp=Path(td); src=tmp/'result.pdf'
    with fitz.open() as d:
      p=d.new_page(); p.insert_text((72,90),'ID371 Studio handoff marker')
      d.save(src)
    b64=base64.b64encode(src.read_bytes()).decode()
    app,base,_=helper.start_server(tmp/'data')
    evidence={'checks':[],'page_errors':[],'console_errors':[]}
    try:
      port=int(base.rsplit(':',1)[1])
      for _ in range(150):
        try:
          with socket.create_connection(('127.0.0.1',port),timeout=.2): break
        except OSError: time.sleep(.2)
      with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        page=browser.new_page(viewport={'width':390,'height':844})
        page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
        page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
        resp=page.goto(base+'/rotate-pdf',wait_until='domcontentloaded')
        page.evaluate('''b64=>{const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0)); const blob=new Blob([bytes],{type:'application/pdf'}); window.showDownloadResult({output_name:'id371-result.pdf',output_size:blob.size,page_count:1},URL.createObjectURL(blob),{blob});}''',b64)
        btn=page.locator('#result-view-studio-btn')
        btn.wait_for(state='visible')
        button_visible_before_click=not btn.is_hidden()
        btn.click()
        page.locator('#view-pdf-studio:not([hidden])').wait_for(timeout=15000)
        page.wait_for_function("state.studio.pdfDoc && state.studio.totalCount===1",timeout=20000)
        evidence['checks'].append({'route_status':resp.status if resp else None,'button_visible_for_pdf_output':button_visible_before_click,'studio_active':not page.locator('#view-pdf-studio').is_hidden(),'studio_page_count':page.evaluate('state.studio.totalCount'),'studio_source_name':page.evaluate('state.studio.srcFile?.name'),'studio_loaded':bool(page.evaluate('state.studio.pdfDoc')),'viewport':390})
        # A non-PDF result must not offer an invalid Studio handoff.
        page.evaluate("window.showDownloadResult({output_name:'result.docx',output_size:12},URL.createObjectURL(new Blob(['docx'],{type:'application/vnd.openxmlformats-officedocument.wordprocessingml.document'})))")
        evidence['checks'].append({'non_pdf_result_hides_studio_button':btn.is_hidden(),'output_name':'result.docx'})
        browser.close()
    finally:
      app.terminate(); app.wait(timeout=5)
    evidence['result']=len(evidence['checks'])==2 and evidence['checks'][0]['route_status']==200 and evidence['checks'][0]['button_visible_for_pdf_output'] and evidence['checks'][0]['studio_loaded'] and evidence['checks'][0]['studio_page_count']==1 and evidence['checks'][1]['non_pdf_result_hides_studio_button'] and not evidence['page_errors'] and not evidence['console_errors']
    out=Path(__file__).parent/'browser-id371-result-studio-handoff.json'; out.write_text(json.dumps(evidence,indent=2),encoding='utf-8'); print(json.dumps(evidence,indent=2))
    if not evidence['result']: raise SystemExit(1)
if __name__=='__main__': main()


