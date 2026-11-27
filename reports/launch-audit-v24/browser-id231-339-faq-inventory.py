"""Inspect FAQ route and home FAQ content in current local Chrome."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/launch-audit-v24/browser-id231-339-faq-inventory.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-faq-') as td:
  app,base,_=helper.start_server(Path(td)/'data');ev={'rounds':[],'page_errors':[],'console_errors':[]}
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2):break
    except OSError:
     if app.poll() is not None:raise RuntimeError('server exited')
     time.sleep(.15)
   with sync_playwright() as pw:
    b=pw.chromium.launch(channel='chrome',headless=True)
    for _ in range(2):
     p=b.new_page(viewport={'width':1366,'height':900});p.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));p.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error' else None)
     response=p.goto(base+'/faq',wait_until='domcontentloaded');p.wait_for_timeout(100)
     ev['rounds'].append({'faq_status':response.status if response else None,'faq_questions':p.locator('#view-faq details').evaluate_all("es=>es.map(e=>e.querySelector('summary')?.innerText.trim())"),'active_heading':p.locator('#view-faq h1').inner_text() if p.locator('#view-faq h1').count() else None})
     detail=p.locator('#view-faq details').filter(has_text='Where can I find refund information?')
     detail.locator('summary').click(); ev['rounds'][-1]['refund_expanded']=detail.evaluate('(e)=>e.open')
     ev['rounds'][-1]['required_links']=p.evaluate("""()=>['/pricing','/refund','/feedback'].every(href=>[...document.querySelectorAll('#view-faq a')].some(a=>a.getAttribute('href')===href))""")
     p.goto(base+'/',wait_until='domcontentloaded');p.wait_for_timeout(100)
     ev['rounds'][-1]['home_questions']=p.locator('.seo-content .seo-faq .seo-faq-item').evaluate_all("es=>es.map(e=>e.querySelector('summary')?.innerText.trim())")
     ev['rounds'][-1]['same_questions_home'] = ev['rounds'][-1]['faq_questions'] == ev['rounds'][-1]['home_questions']
     p.close()
    b.close()
  finally:app.terminate();app.wait(timeout=5)
  ev['overall']='passed' if all(len(r['faq_questions'])==7 and r['same_questions_home'] and r['refund_expanded'] and r['required_links'] for r in ev['rounds'])and not ev['page_errors']and not ev['console_errors']else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8');print(json.dumps(ev,indent=2))
if __name__=='__main__':main()
