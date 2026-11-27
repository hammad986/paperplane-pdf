"""Verify Downloads label and Native Apps waitlist route are distinct."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=ROOT/'reports/launch-audit-v24/browser-id330-downloads-naming.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14')); import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-id330-') as td:
  app,base,_=helper.start_server(Path(td)/'data'); ev={'rounds':[],'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError:
     if app.poll() is not None: raise RuntimeError('server exited')
     time.sleep(.15)
   with sync_playwright() as pw:
    browser=pw.chromium.launch(channel='chrome',headless=True)
    for _ in range(2):
     page=browser.new_page(viewport={'width':1366,'height':900}); page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200])); page.on('console',lambda m:ev['console_errors'].append(m.text[:200]) if m.type=='error' else None)
     a=page.goto(base+'/download',wait_until='domcontentloaded'); page.wait_for_timeout(150)
     ev['rounds'].append({'waitlist_status':a.status if a else None,'route':page.url.split(base)[-1],'title':page.title(),'main_heading':page.locator('h1:visible').first.inner_text() if page.locator('h1:visible').count() else '', 'waitlist_copy':page.locator('body').inner_text().lower().find('waitlist')>=0})
     page.evaluate("const e=document.querySelector('.main-area');if(e)e.scrollTo(0,e.scrollHeight);else window.scrollTo(0,document.body.scrollHeight)"); page.wait_for_timeout(100)
     links=page.locator('footer a:visible').evaluate_all("es=>es.map(e=>({text:e.innerText.trim(),href:e.getAttribute('href')}))")
     ev['rounds'][-1]['footer_links']=links
     results=[x for x in links if x['text'].lower() in ('temporary results','downloads','download history')]
     ev['rounds'][-1]['results_link']=results[0] if results else None
     if results:
      page.locator('footer a:visible').filter(has_text=results[0]['text']).click(); page.wait_for_timeout(150); ev['rounds'][-1]['results_route']=page.url.split(base)[-1]; ev['rounds'][-1]['results_disclosure']='no saved history' in page.locator('body').inner_text().lower()
     page.close()
    browser.close()
  finally: app.terminate(); app.wait(timeout=5)
  ev['overall']='passed' if len(ev['rounds'])==2 and all(x['waitlist_status']==200 and x['waitlist_copy'] and x['results_link'] and x['results_link']['text']=='Temporary results' and x['results_link']['href']=='/history' and x['results_route']=='/history' and x['results_disclosure'] for x in ev['rounds']) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8'); print(json.dumps(ev,indent=2))
  if ev['overall']!='passed': raise SystemExit(1)
if __name__=='__main__': main()
