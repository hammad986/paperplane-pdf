from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]; OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-pricing-234-') as temp:
 app,base,identity=helper.start_server(Path(temp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
   except OSError: time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True); rounds=[]
   for n in (1,2):
    page=browser.new_page(viewport={'width':1366,'height':900}); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/pricing',wait_until='domcontentloaded'); page.wait_for_selector('.pricing-tier-card')
    cards=page.locator('.pricing-tier-card').evaluate_all("els=>els.map(c=>{const b=c.querySelector('.tier-popular-tag');if(!b)return null;const cr=c.getBoundingClientRect(),br=b.getBoundingClientRect();return {badge:b.textContent.trim(),cardTop:cr.top,badgeTop:br.top,badgeBottom:br.bottom,cardBottom:cr.bottom,contained:br.top>=cr.top&&br.bottom<=cr.bottom}}).filter(Boolean)")
    copy=page.locator('.tier-features-list').all_text_contents()
    assert len(cards)==3 and all(c['contained'] for c in cards) and any('Document Stamps & Watermarks' in x for x in copy) and not any('Shop Stamp' in x for x in copy),(cards,copy,errors)
    page.screenshot(path=str(OUT/f'id233-234-pricing-round{n}.png')); rounds.append({'round':n,'badges':cards,'copy_ok':True,'page_errors':errors}); page.close()
   browser.close()
  result={'rounds':rounds}; (OUT/'browser-ids233-234-pricing.json').write_text(json.dumps(result,indent=2)); print(json.dumps(result,indent=2))
 finally: app.terminate(); app.wait(timeout=5)
