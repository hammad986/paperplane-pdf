import json
from pathlib import Path
from playwright.sync_api import sync_playwright
routes=['merge-pdf','split-pdf','compress-pdf'];viewports=[(320,740),(390,844),(820,712),(846,712),(900,800)]
checks=[];errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for route in routes:
  for w,h in viewports:
   page=b.new_page(viewport={'width':w,'height':h});page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(f'http://127.0.0.1:8774/{route}',wait_until='domcontentloaded')
   button=page.locator('#run-button');button.scroll_into_view_if_needed()
   check=page.evaluate('''()=>{const rect=e=>{if(!e)return null;let r=e.getBoundingClientRect();return {x:r.x,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};const a=rect(document.querySelector('#run-button')),b=rect(document.querySelector('.mobile-workspace-bar'));return {width:innerWidth,height:innerHeight,run:a,bottomBar:b,overlap:!!(a&&b&&a.bottom>b.top&&a.top<b.bottom),runVisible:!!a&&a.width>0&&a.height>0,bodyWidth:document.body.scrollWidth}}''')
   check['route']=route;checks.append(check);page.close()
 b.close()
result={'checks':checks,'pageErrors':errors};Path('reports/launch-audit-v24/browser-id340-v203-mobile-action-overlap.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'count':len(checks),'overlaps':[x for x in checks if x['overlap']],'hidden':[x for x in checks if not x['runVisible']],'pageErrors':errors},indent=2))
if errors or any(x['overlap'] or not x['runVisible'] for x in checks):raise SystemExit(1)
