"""Verify the Translate result's View in Studio handoff with a controlled Hindi-named PDF."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/launch-audit-v24/browser-id270-translate-studio-handoff.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id270-') as td:
  td=Path(td);source=td/'hindi-translated.pdf'
  with fitz.open() as d:
   p=d.new_page();p.insert_text((72,90),'ID270 HINDI TRANSLATION RESULT');d.save(source)
  app,base,_=helper.start_server(td/'data');ev={'rounds':[],'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2):break
    except OSError:
     if app.poll() is not None:raise RuntimeError('server exited')
     time.sleep(.15)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    for _ in range(2):
     page=browser.new_page(viewport={'width':1366,'height':900});page.set_default_timeout(20000);page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));page.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error'else None)
     page.goto(base+'/translate-pdf',wait_until='domcontentloaded')
     ev['rounds'].append({'operation':page.evaluate('state.operation')})
     raw=source.read_bytes().hex()
     page.evaluate("""hex=>{let b=new Uint8Array(hex.match(/.{1,2}/g).map(x=>parseInt(x,16)));let blob=new Blob([b],{type:'application/pdf'});showDownloadResult({output_name:'hindi-translated.pdf',output_size:blob.size,page_count:1},URL.createObjectURL(blob),{blob})}""",raw)
     page.locator('#result-view-studio-btn:not([hidden])').wait_for()
     ev['rounds'][-1]['button_visible']=page.locator('#result-view-studio-btn').is_visible()
     page.locator('#result-view-studio-btn').click()
     page.wait_for_function("state.studio.pdfDoc && state.studio.srcFile?.name==='hindi-translated.pdf'",timeout=30000)
     page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=30000)
     ev['rounds'][-1].update({'url':page.url.split(base)[-1],'restored_filename':page.evaluate('state.studio.srcFile?.name'),'pages':page.evaluate('state.studio.totalCount'),'canvas_rendered':page.locator('#pdf-canvas').get_attribute('data-rendered'),'pdf_text':page.evaluate("""async()=>{const page=await state.studio.pdfDoc.getPage(1);const text=await page.getTextContent();return text.items.map(x=>x.str).join(' ')}""")})
     page.close()
    browser.close()
  finally:app.terminate();app.wait(timeout=5)
  ev['overall']='passed' if len(ev['rounds'])==2 and all(r['operation']=='translate' and r['button_visible'] and r['url']=='/studio' and r['restored_filename']=='hindi-translated.pdf' and r['pages']==1 and r['canvas_rendered']=='true' and 'ID270 HINDI TRANSLATION RESULT' in r['pdf_text'] for r in ev['rounds']) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8');print(json.dumps(ev,indent=2))
  if ev['overall']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
