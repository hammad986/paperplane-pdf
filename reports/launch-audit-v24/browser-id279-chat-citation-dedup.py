import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def main():
 ev={'page_errors':[],'console_errors':[]}
 with TemporaryDirectory(prefix='paperplane-id279-') as td:
  tdp=Path(td); pdf=tdp/'citation-fixture.pdf'
  doc=fitz.open(); page=doc.new_page(); page.insert_text((72,72),'Citation fixture source. Amount due: 200 units.') ; doc.save(pdf); doc.close()
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
    page=browser.new_page(viewport={'width':1366,'height':900})
    page.on('pageerror',lambda e:ev['page_errors'].append(str(e)))
    page.on('console',lambda m:ev['console_errors'].append(m.text) if m.type=='error' else None)
    def synthetic_stream(route):
     body=(
      'event: stage\ndata: {"stage":"Generating…"}\n\n'
      'event: token\ndata: {"text":"The amount is 200 units. [Page 3]. I checked again [Page 3]. Third reference [Page 3]."}\n\n'
      'event: done\ndata: {"citations":[3,3,2],"mode":"provider"}\n\n'
     )
     route.fulfill(status=200,content_type='text/event-stream; charset=utf-8',body=body,headers={'Cache-Control':'no-cache'})
    page.route('**/api/ai/chat/stream',synthetic_stream)
    response=page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
    page.locator('#ai-file-input').set_input_files(str(pdf))
    page.wait_for_function("state.files?.some(file=>file.name==='citation-fixture.pdf')",timeout=30000)
    page.locator('#chat-input').fill('What is the amount?')
    page.locator('#chat-send-btn').click()
    page.wait_for_function("[...document.querySelectorAll('.ai-stream-bubble')].some(b=>b.innerText.includes('Third reference'))",timeout=30000)
    bubble=page.locator('.ai-stream-bubble').last
    ev.update({'http_status':response.status,'file_loaded':True,'answer':bubble.locator('.ai-stream-text').inner_text(),'inline_page3_count':bubble.locator('.ai-stream-text [data-ai-page="3"]').count(),'standalone_page3_count':bubble.locator('.chat-citation-tags [data-ai-page="3"]').count(),'standalone_page2_count':bubble.locator('.chat-citation-tags [data-ai-page="2"]').count(),'all_page_chips':bubble.locator('[data-ai-page]').evaluate_all("els=>els.map(e=>({page:e.dataset.aiPage,text:e.innerText,zone:e.closest('.chat-citation-tags')?'standalone':'inline'}))"),'url':page.url})
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
 ev['passed']=ev['http_status']==200 and ev['file_loaded'] and ev['inline_page3_count']==1 and ev['standalone_page3_count']==0 and ev['standalone_page2_count']==1 and len(ev['all_page_chips'])==2 and not ev['page_errors'] and not ev['console_errors']
 (ROOT/'reports/launch-audit-v24/browser-id279-chat-citation-dedup.json').write_text(json.dumps(ev,indent=2),encoding='utf-8')
 print(json.dumps(ev,indent=2))
 if not ev['passed']: raise SystemExit(1)
if __name__=='__main__': main()
