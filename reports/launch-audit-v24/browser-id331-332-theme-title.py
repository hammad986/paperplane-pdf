"""Recheck current Settings theme default and SPA developer-page title."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'reports/launch-audit-v24/browser-id331-332-theme-title.json'
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper

def main():
 with TemporaryDirectory(prefix='paperplane-331-332-') as td:
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
    browser=pw.chromium.launch(channel='chrome',headless=True)
    for _ in range(2):
     page=browser.new_page(viewport={'width':1366,'height':900});page.on('pageerror',lambda e:ev['page_errors'].append(str(e)[:200]));page.on('console',lambda m:ev['console_errors'].append(m.text[:200])if m.type=='error'else None)
     page.goto(base+'/settings',wait_until='domcontentloaded');page.locator('#settings-tab-btn-appearance').wait_for(state='visible');page.locator('#settings-tab-btn-appearance').click();page.locator('#pane-appearance:not([hidden])').wait_for()
     ev['rounds'].append({'theme':page.evaluate("""()=>({rootTheme:document.documentElement.dataset.paperplaneTheme,bodyDark:document.body.classList.contains('dark-mode'),lightActive:document.querySelector('#theme-light-btn')?.classList.contains('active'),darkActive:document.querySelector('#theme-dark-btn')?.classList.contains('active'),lightText:document.querySelector('#theme-light-btn strong')?.textContent.trim(),darkText:document.querySelector('#theme-dark-btn strong')?.textContent.trim()})""")})
     page.goto(base+'/faq',wait_until='domcontentloaded');ev['rounds'][-1]['faq_title']=page.title()
     page.evaluate("""()=>{const a=document.querySelector('.main-area');if(a)a.scrollTo(0,a.scrollHeight);else window.scrollTo(0,document.body.scrollHeight)}""");page.wait_for_timeout(100)
     page.locator('#footer-link-developers').click();page.wait_for_timeout(100)
     ev['rounds'][-1]['developers']={'url':page.url.split(base)[-1],'title':page.title(),'heading':page.locator('#view-api-docs h2').inner_text() if page.locator('#view-api-docs h2').count() else None}
     page.close()
    browser.close()
  finally:app.terminate();app.wait(timeout=5)
  ev['overall']='passed' if len(ev['rounds'])==2 and all(r['theme']['rootTheme']=='light' and not r['theme']['bodyDark'] and r['theme']['lightActive'] and not r['theme']['darkActive'] and 'Default' in r['theme']['lightText'] and 'Default' not in r['theme']['darkText'] and r['developers']['url']=='/developers' and r['developers']['title'] not in ('Frequently asked questions','') and r['developers']['heading'] for r in ev['rounds']) and not ev['page_errors'] and not ev['console_errors'] else 'failed'
  OUT.write_text(json.dumps(ev,indent=2),encoding='utf-8');print(json.dumps(ev,indent=2))
  if ev['overall']!='passed':raise SystemExit(1)
if __name__=='__main__':main()
