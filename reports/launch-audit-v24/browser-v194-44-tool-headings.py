import json
from pathlib import Path
from playwright.sync_api import sync_playwright
routes=[x['route'] for x in json.loads(Path('reports/launch-audit-v24/route-layout-matrix.json').read_text())['copy_routes'] if x['route'] not in ['/','/pricing']]
errors=[]; console_errors=[]; rounds=[]
with sync_playwright() as p:
 b=p.chromium.launch(); page=b.new_page(viewport={'width':1366,'height':900}); page.set_default_timeout(10000); page.set_default_navigation_timeout(15000); page.on('pageerror',lambda e:errors.append(str(e))); page.on('console',lambda m:console_errors.append(m.text) if m.type=='error' else None)
 for rn in (1,2):
  round_rows=[]
  for route in routes:
   page.goto('http://127.0.0.1:8768'+route,wait_until='domcontentloaded')
   expected=page.title().replace(' | Paperplane','')
   if route=='/ai-pdf-chat': expected='AI Document Intelligence'
   page.wait_for_function("expected => [...document.querySelectorAll('h1')].some(x=>x.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}) && x.innerText.trim()===expected)",arg=expected)
   d=page.evaluate('''() => {let hs=[...document.querySelectorAll('h1')].filter(x=>x.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}));let dz=document.querySelector('#dropzone h2, #dropzone h3');return {title:document.title,h1:hs.map(x=>x.innerText.trim()),dropHeading:dz?{tag:dz.tagName,text:dz.innerText.trim()}:null,css:[...document.querySelectorAll('link[rel=stylesheet]')].map(x=>new URL(x.href).pathname+new URL(x.href).search)}}''')
   round_rows.append({'route':route,**d})
  rounds.append(round_rows)
 b.close()
issues=[]
for n,rr in enumerate(rounds,1):
 for row in rr:
  expected='AI Document Intelligence' if row['route']=='/ai-pdf-chat' else row['title'].replace(' | Paperplane','')
  if row['h1']!=[expected] or (row['route'] not in ['/html-to-pdf'] and row['dropHeading']!={'tag':'H2','text':'Drop your document here'}) or '/assets/styles.css?v=71' not in row['css']:
   issues.append({'round':n,'route':row['route'],'expected':expected,'h1':row['h1'],'dropHeading':row['dropHeading'],'css':row['css']})
result={'build':'app.js v194 / styles.css v71 / service-worker v146','route_count':len(routes),'round_sizes':[len(x) for x in rounds],'rounds':rounds,'issues':issues,'browser_errors':errors,'console_errors':console_errors,'passed':len(rounds)==2 and all(len(x)==44 for x in rounds) and not issues and not errors and not console_errors}
Path('reports/launch-audit-v24/browser-v194-44-tool-headings.json').write_text(json.dumps(result,indent=2,ensure_ascii=False))
print(json.dumps({'route_count':len(routes),'round_sizes':[len(x) for x in rounds],'issue_count':len(issues),'issues':issues[:10],'browser_errors':errors,'console_errors':console_errors,'passed':result['passed']},ensure_ascii=False,indent=2))