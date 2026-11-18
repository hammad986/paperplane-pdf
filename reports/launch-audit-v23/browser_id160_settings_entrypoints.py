from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
TABS=('account','appearance','billing','api','privacy')
with TemporaryDirectory(prefix='paperplane-id160-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    mode_results=[]
    for mode in ('local','server'):
     c=b.new_context(viewport={'width':1366,'height':900});c.add_init_script(f"localStorage.setItem('paperplane-pdf-processing-mode','{mode}')");errors=[]
     contexts={}
     for entry in ('modal','page'):
      page=c.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
      page.goto(base+'/' if entry=='modal' else base+'/settings',wait_until='domcontentloaded')
      if entry=='modal':page.locator('#sidebar-settings-gear-btn').click();page.wait_for_function("!document.querySelector('#settings-modal').hidden")
      else:page.wait_for_function("document.querySelector('#view-settings') && !document.querySelector('#view-settings').hidden")
      record={}
      for tab in TABS:
       page.locator(f'#settings-tab-btn-{tab}').evaluate('(e)=>e.click()');page.wait_for_timeout(100);record[tab]=page.locator(f'#pane-{tab}').inner_text().strip()
      contexts[entry]=record;page.screenshot(path=str(OUT/f'id160-{entry}-{mode}-round{n}.png'))
     checks={tab:contexts['modal'][tab]==contexts['page'][tab] for tab in TABS};assert all(checks.values()),{'mode':mode,'checks':checks,'modalPrivacy':contexts['modal']['privacy'],'pagePrivacy':contexts['page']['privacy']};assert not errors
     mode_results.append({'mode':mode,'tabs_match':checks,'privacy_copy':contexts['page']['privacy'].split('Local Processing')[-1].strip()[:150],'page_errors':errors});c.close()
    rounds.append({'round':n,'modes':mode_results})
   result={'rounds':rounds};(OUT/'browser-id160-settings-entrypoints.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
