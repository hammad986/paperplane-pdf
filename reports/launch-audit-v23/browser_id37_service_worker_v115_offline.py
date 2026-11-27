from pathlib import Path
import json
import os
from playwright.sync_api import sync_playwright
OUT=Path('reports/launch-audit-v23'); BASE=os.environ.get('PAPERPLANE_TEST_BASE','http://127.0.0.1:8501')
results=[]
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True)
 for round_no in (1,2):
  ctx=b.new_context(service_workers='allow'); page=ctx.new_page(); errors=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  response=page.goto(BASE+'/pdf-to-word',wait_until='domcontentloaded'); assert response and response.status==200
  page.wait_for_function("navigator.serviceWorker.controller !== null",timeout=15000)
  page.wait_for_timeout(1000)
  before=page.evaluate("""async()=>({caches:await caches.keys(),assets:await (async()=>{const c=await caches.open('paperplane-shell-v46');return {app:!!await c.match('/assets/app.js?v=115'),css:!!await c.match('/assets/styles.css?v=55')}})()})""")
  ctx.set_offline(True)
  offline=page.goto(BASE+'/',wait_until='domcontentloaded',timeout=15000)
  loaded=page.evaluate("""()=>({controller:!!navigator.serviceWorker.controller,title:document.title,appAsset:document.querySelector('script[src*="app.js"]')?.getAttribute('src'),background:getComputedStyle(document.body).backgroundColor})""")
  result={'round':round_no,'before':before,'offline_navigation_status':offline.status if offline else None,'offline_page':loaded,'page_errors':errors}
  results.append(result)
  assert 'paperplane-shell-v46' in before['caches'] and before['assets']['app'] and before['assets']['css'] and loaded['controller'] and loaded['appAsset']=='/assets/app.js?v=115' and not errors,result
  ctx.close()
 b.close()
result={'rounds':results}
(OUT/'browser-id42-service-worker-v46-offline.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
