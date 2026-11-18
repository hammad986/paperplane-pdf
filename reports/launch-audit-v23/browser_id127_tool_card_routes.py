from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id127-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900});page=c.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    response=page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.wait_for_function("document.querySelectorAll('#tool-desk-tools-catalog a.home-tool-card').length>=40",timeout=15000)
    links=page.locator('#tool-desk-tools-catalog a.home-tool-card').evaluate_all("es=>es.map(e=>({text:e.innerText.trim().replace(/\\s+/g,' '),href:e.getAttribute('href'),tag:e.tagName}))")
    unique=sorted(set(x['href'] for x in links if x['href']))
    statuses=[]
    for url in unique:
     res=page.request.get(base+url);statuses.append({'path':url,'status':res.status})
    aliases=[]
    for path,target in (('/scan-pdf','/scan-to-pdf'),('/tools','/tool-desk'),('/all-tools','/tool-desk')):
     r=page.request.get(base+path,max_redirects=0)
     aliases.append({'path':path,'status':r.status,'location':r.headers.get('location'),'expected_location':target})
    item={'round':n,'tool_cards':len(links),'anchor_cards':sum(x['tag']=='A' and bool(x['href']) for x in links),'unique_routes':len(unique),'non_200_routes':[x for x in statuses if x['status']!=200],'legacy_aliases':aliases,'page_errors':errors}
    print(json.dumps(item,indent=2))
    assert item['tool_cards']>=40 and item['anchor_cards']==item['tool_cards'] and len(unique)==item['tool_cards'] and not item['non_200_routes'] and all(a['status']==301 and a['location']==a['expected_location'] for a in aliases) and not errors
    page.screenshot(path=str(OUT/f'id127-tool-card-links-round{n}.png'));rounds.append(item);c.close()
   result={'rounds':rounds};(OUT/'browser-id127-tool-card-routes.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
