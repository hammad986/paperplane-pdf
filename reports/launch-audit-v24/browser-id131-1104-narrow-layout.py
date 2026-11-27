import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent/'browser-id131-1104-narrow-layout.json';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id131-') as td:
 app,base,_=h.start_server(Path(td)/'data')
 try:
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':1104,'height':768});e={'page_errors':[],'console_errors':[]};page.on('pageerror',lambda x:e['page_errors'].append(str(x)));page.on('console',lambda m:e['console_errors'].append(m.text) if m.type=='error' else None);checks=[]
   for route in ('/download','/developers'):
    r=page.goto(base+route,wait_until='domcontentloaded');page.wait_for_timeout(500);metrics=page.evaluate("""()=>{const box=e=>{if(!e)return null;const r=e.getBoundingClientRect();return{x:Math.round(r.x),y:Math.round(r.y),right:Math.round(r.right),bottom:Math.round(r.bottom),width:Math.round(r.width),height:Math.round(r.height)}};const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.display!=='none'&&s.visibility!=='hidden'};const visibleText=(text)=>[...document.querySelectorAll('*')].find(e=>e.children.length===0&&e.textContent.trim()===text&&visible(e));const view=document.querySelector(routeView());const headings=[...(view||document).querySelectorAll('h1,h2,h3,h4')].filter(visible).map(e=>({text:e.textContent.trim(),box:box(e)}));const label=visibleText('LIMITS & RESET');const card=label?.parentElement?.parentElement;return{viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,sidebar:box(document.querySelector('#sidebar')),main:box(document.querySelector('.main-area')),view:box(view),headings,limitsLabel:box(label),limitsCard:box(card)}};function routeView(){return location.pathname==='/download'?'#view-download':'#view-developers'}""");checks.append({'route':route,'status':r.status if r else None,'metrics':metrics});page.screenshot(path=str(OUT.parent/f'browser-id131-{route[1:]}-1104.png'))
   def in_content(metrics, target):
    box=metrics.get(target)
    if not box:return False
    sidebar=metrics.get('sidebar') or {'right':0}
    main=metrics.get('main') or {'right':metrics['viewport']}
    return box['x']>=sidebar['right']-1 and box['right']<=min(main['right'],metrics['viewport'])+1
   for item in checks:
    m=item['metrics']
    targets=[h['box'] for h in m['headings'] if h['text']=='Native Apps Early Access'] if item['route']=='/download' else [m.get('limitsCard')]
    item['target_count']=len(targets);item['target_in_content']=bool(targets) and all(in_content(m,'limitsCard') if item['route']=='/developers' else (t['x']>= (m.get('sidebar') or {'right':0})['right']-1 and t['right']<=min((m.get('main') or {'right':m['viewport']})['right'],m['viewport'])+1) for t in targets)
   e['checks']=checks;e['passed']=all(x['status']==200 and x['metrics']['documentWidth']<=1104 and x['target_count']==1 and x['target_in_content'] for x in checks) and not e['page_errors'] and not e['console_errors'];OUT.write_text(json.dumps(e,indent=2),encoding='utf-8');print(json.dumps(e,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
