import ast,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('.')
tree=ast.parse((root/'server.py').read_text(encoding='utf-8'))
slugs=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OPERATION_SLUGS' for t in n.targets))
routes=['/','/pricing']+['/'+x for x in slugs.values()]
errors=[];checks=[]
with sync_playwright() as p:
 b=p.chromium.launch();page=b.new_page(viewport={'width':320,'height':780});page.set_default_timeout(10000);page.on('pageerror',lambda e:errors.append(str(e)))
 for width in (320,390):
  page.set_viewport_size({'width':width,'height':844})
  for route in routes:
   response=page.goto('http://127.0.0.1:8768'+route,wait_until='domcontentloaded',timeout=15000)
   page.wait_for_function("()=>[...document.querySelectorAll('h1')].some(h=>h.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))",timeout=10000)
   data=page.evaluate("""()=>({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,visibleH1:[...document.querySelectorAll('h1')].filter(h=>h.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})).map(h=>h.innerText.trim())})""")
   checks.append({'route':route,'status':response.status if response else None,**data})
 b.close()
issues=[c for c in checks if c['status']!=200 or c['documentWidth']>c['viewport']+2 or not c['visibleH1']]
result={'candidate':'app.js v192/styles.css v71/service-worker v144','routes':len(routes),'viewport_widths':[320,390],'checks':checks,'issues':issues,'browser_errors':errors,'passed':len(checks)==len(routes)*2 and not issues and not errors}
Path('reports/launch-audit-v24/browser-v192-mobile-viewport.json').write_text(json.dumps(result,indent=2,ensure_ascii=True),encoding='utf-8');print(json.dumps({'routes':len(routes),'checks':len(checks),'issues':issues[:10],'errors':errors,'passed':result['passed']},indent=2))