import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
widths=[320,390,820,846,900,1366,1920];tabs=['account','appearance','billing','privacy','api'];checks=[];errors=[]
with TemporaryDirectory(prefix='paperplane-v24-id311-') as temp:
 app,base,_=helper.start_server(Path(temp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.2)
  else:raise RuntimeError('Local Paperplane server did not start')
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True)
   for w in widths:
    page=b.new_page(viewport={'width':w,'height':800});page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/',wait_until='domcontentloaded');page.evaluate('window.openSettingsModal()');page.locator('#settings-modal:not([hidden])').wait_for()
    for tab in tabs:
     if tab!='account':page.locator(f'#settings-tab-btn-{tab}').click()
     page.wait_for_timeout(80)
     checks.append(page.evaluate('''tab=>{const modal=document.querySelector('#settings-modal .settings-modal-card'),rail=modal.querySelector('.settings-tabs');const vis=e=>!!(e&&e.getClientRects().length&&getComputedStyle(e).display!=='none');const rect=e=>{let r=e.getBoundingClientRect();return {x:Math.round(r.x),right:Math.round(r.right),width:Math.round(r.width),height:Math.round(r.height)}};const els=[...modal.querySelectorAll('input,select,textarea,button,.settings-tabs,.settings-content,.settings-card-item')].filter(e=>vis(e)&&!e.classList.contains('settings-tab-btn')).map(e=>({tag:e.tagName,id:e.id||'',cls:String(e.className||'').split(' ')[0],rect:rect(e)}));return {width:innerWidth,tab,modal:rect(modal),docWidth:document.documentElement.scrollWidth,tabsRail:{clientWidth:rail.clientWidth,scrollWidth:rail.scrollWidth,scrollable:rail.scrollWidth>rail.clientWidth},overflowing:els.filter(e=>e.rect.right>innerWidth+1||e.rect.x< -1),elementCount:els.length}}''',tab))
    page.close()
   b.close()
 finally:app.terminate()
result={'build':'current workspace source','checks':checks,'pageErrors':errors};Path('reports/launch-audit-v24/browser-id311-settings-layout-current.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'checks':len(checks),'overflow':[(x['width'],x['tab'],x['overflowing']) for x in checks if x['overflowing']],'documentOverflows':[(x['width'],x['tab'],x['docWidth']) for x in checks if x['docWidth']>x['width']],'pageErrors':errors},indent=2))
if errors or any(x['overflowing'] or x['docWidth']>x['width'] for x in checks):raise SystemExit(1)
