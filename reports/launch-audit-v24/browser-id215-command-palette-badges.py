import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id215-command-palette-badges.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id215-') as tmp:
 app,base,_=h.start_server(Path(tmp)/'data')
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1366,'height':900});e={'page_errors':[],'console_errors':[]};page.on('pageerror',lambda x:e['page_errors'].append(str(x)));page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None);r=page.goto(base+'/',wait_until='domcontentloaded');page.keyboard.press('Control+k');page.wait_for_function("!document.querySelector('#command-modal')?.hidden");e['route_status']=r.status if r else None;e['items']=page.locator('.command-item').evaluate_all("xs=>xs.map(x=>({operation:x.dataset.commandOperation,label:x.querySelector('strong')?.innerText,badge:x.querySelector('.command-item-badge')?.innerText}))");e['counts']={'items':len(e['items']),'api_badges':sum(x['badge'].strip().lower()=='api' for x in e['items']),'categories':sorted(set(x['badge'] for x in e['items']))};page.screenshot(path=str(OUT.parent/'browser-id215-command-palette-badges.png'));e['passed']=e['route_status']==200 and e['counts']['items']>0 and e['counts']['api_badges']==0 and not e['page_errors'] and not e['console_errors'];OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
