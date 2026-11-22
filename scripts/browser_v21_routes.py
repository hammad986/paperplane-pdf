import ast,json
from pathlib import Path
from playwright.sync_api import sync_playwright
root=Path('.');tree=ast.parse((root/'server.py').read_text(encoding='utf-8'))
slugs=next(ast.literal_eval(n.value) for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OPERATION_SLUGS' for t in n.targets))
rows=[];out=root/'reports/launch-audit-v21/layout/catalog';out.mkdir(parents=True,exist_ok=True)
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True)
 for width in (390,820,1366,1920):
  page=b.new_page(viewport={'width':width,'height':900})
  for op,slug in slugs.items():
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   res=page.goto('http://127.0.0.1:8765/'+slug,wait_until='domcontentloaded');page.wait_for_timeout(200)
   data=page.evaluate('''() => ({width:innerWidth,scrollWidth:document.documentElement.scrollWidth,title:document.title})''')
   page.screenshot(path=str(out/f'{op}-{width}.png'))
   rows.append({'operation':op,'width':width,'status':res.status,'layout':data,'errors':errors})
  page.close()
 b.close()
(out/'results.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print('route checks:',len(rows),'overflow:',sum(x['layout']['scrollWidth']>x['width']+2 for x in rows),'errors:',sum(bool(x['errors']) for x in rows))
