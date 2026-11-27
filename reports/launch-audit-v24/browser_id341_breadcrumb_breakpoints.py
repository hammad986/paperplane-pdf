import json
from pathlib import Path
from playwright.sync_api import sync_playwright
widths=[320,390,820,846,900,901,1024,1366]
rows=[]; errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for w in widths:
  page=b.new_page(viewport={'width':w,'height':800}); page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8774/ai-intelligence',wait_until='domcontentloaded')
  row=page.evaluate('''()=>{const rect=e=>{if(!e)return null;const r=e.getBoundingClientRect();return {x:Math.round(r.x),right:Math.round(r.right),width:Math.round(r.width),y:Math.round(r.y),height:Math.round(r.height),display:getComputedStyle(e).display}};const crumb=document.querySelector('.breadcrumb-trail');return {width:innerWidth,breadcrumbText:crumb?.innerText,breadcrumb:rect(crumb),crumbChildren:[...(crumb?.children||[])].map(e=>({text:e.innerText,rect:rect(e),flex:getComputedStyle(e).flex,minWidth:getComputedStyle(e).minWidth})),tabs:rect(document.querySelector('.workspace-tabs')),mobileBar:rect(document.querySelector('.mobile-workspace-bar')),bodyWidth:document.body.scrollWidth,docWidth:document.documentElement.scrollWidth}}''')
  rows.append(row); page.close()
 b.close()
result={'route':'/ai-intelligence','checks':rows,'pageErrors':errors}
Path('reports/launch-audit-v24/browser-id341-v203-breadcrumb-breakpoints.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
