import base64,json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-v24-id301-') as td:
  tmp=Path(td); source=tmp/'sparse-gallery-24.pdf'
  with fitz.open() as doc:
   for n in range(1,25):
    page=doc.new_page(); page.insert_text((72,72),f'Photo {n}')
   doc.save(source)
  app,base,_=helper.start_server(tmp/'data'); evidence={'browser_errors':[],'console_errors':[],'api_responses':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(150):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.2)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844})
    page.on('pageerror',lambda e:evidence['browser_errors'].append(str(e)))
    page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
    page.on('response',lambda r:evidence['api_responses'].append({'url':r.url.split('/')[-1],'status':r.status}) if '/api/ai/chat/stream' in r.url else None)
    response=page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
    page.locator('#ai-file-input').set_input_files(str(source))
    page.wait_for_function("state.files?.[0]?.name === 'sparse-gallery-24.pdf'",timeout=10000)
    page.locator('#chat-input').fill('What is this document about?')
    send_state=page.locator('#chat-send-btn').evaluate("b=>({visible:!!(b.offsetWidth||b.offsetHeight),disabled:b.disabled,rect:(()=>{const r=b.getBoundingClientRect();return [r.left,r.top,r.right,r.bottom]})()})")
    page.locator('#chat-form').evaluate('form=>form.requestSubmit()')
    page.wait_for_timeout(6000)
    text=page.locator('#chat-messages').inner_text()
    answer_text=page.locator('.ai-stream-bubble .ai-stream-text').inner_text() if page.locator('.ai-stream-bubble .ai-stream-text').count() else ''
    evidence['checks']={'route_status':response.status if response else None,'active_document':page.evaluate('state.files?.[0]?.name'),'file_size':page.evaluate('state.files?.[0]?.size'),'question_sent':"What is this document about?" in text,'sparse_text_explanation':'very little searchable text' in text,'recommends_OCR':'Run OCR' in text,'misleading_no_match':'No relevant information found' in text,'assistant_text':answer_text,'send_button':send_state,'viewport':[390,844]}
    page.screenshot(path=str(ROOT/'reports/launch-audit-v24/browser-id301-sparse-gallery-mobile.png'),full_page=True)
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
 evidence['passed']=evidence['checks']['route_status']==200 and evidence['checks']['active_document']=='sparse-gallery-24.pdf' and evidence['checks']['sparse_text_explanation'] and evidence['checks']['recommends_OCR'] and not evidence['checks']['misleading_no_match'] and not evidence['browser_errors'] and not evidence['console_errors'] and all(x['status']==200 for x in evidence['api_responses'])
 out=ROOT/'reports/launch-audit-v24/browser-id301-sparse-gallery-mobile.json'; out.write_text(json.dumps(evidence,indent=2),encoding='utf-8'); print(json.dumps(evidence,indent=2))
 if not evidence['passed']: raise SystemExit(1)
if __name__=='__main__': main()

