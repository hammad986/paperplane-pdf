import base64,json
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright
pdf=Path('reports/launch-audit-v24/id322-three-page-output.pdf').read_bytes(); b64=base64.b64encode(pdf).decode()
allchecks=[]; errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for w,h in [(320,740),(390,844)]:
  page=b.new_page(viewport={'width':w,'height':h}); page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8774/',wait_until='domcontentloaded'); page.wait_for_function("typeof window.showDownloadResult === 'function'")
  page.evaluate("window.selectOperation('merge')")
  page.evaluate('''b64=>{let blob=new Blob([Uint8Array.from(atob(b64),c=>c.charCodeAt(0))],{type:'application/pdf'});window.showDownloadResult({output_name:'mobile-result.pdf',output_size:blob.size,page_count:3},URL.createObjectURL(blob),{blob});}''',b64)
  page.wait_for_timeout(800)
  data=page.evaluate('''()=>{const rect=e=>{if(!e||e.hidden||getComputedStyle(e).display==='none')return null;let r=e.getBoundingClientRect();return {left:Math.round(r.left),right:Math.round(r.right),top:Math.round(r.top),bottom:Math.round(r.bottom),width:Math.round(r.width),height:Math.round(r.height)}};const r=document.querySelector('#result'),d=document.querySelector('#result-download-link'),s=document.querySelector('#result-view-studio-btn'),run=document.querySelector('#run-button'),toast=document.querySelector('.toast-notice'),nav=document.querySelector('.mobile-workspace-bar');return {viewport:{w:innerWidth,h:innerHeight},result:rect(r),download:rect(d),downloadText:d?.innerText,studio:rect(s),run:rect(run),toast:rect(toast),mobileNav:rect(nav),scrollWidth:document.documentElement.scrollWidth}}''')
  allchecks.append(data); page.screenshot(path=f'reports/launch-audit-v24/browser-id85-v203-result-{w}.png',full_page=True)
  page.close()
 b.close()
result={'checks':allchecks,'pageErrors':errors}; Path('reports/launch-audit-v24/browser-id85-v203-result-layout.json').write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
if errors or any(x['scrollWidth']>x['viewport']['w'] for x in allchecks): raise SystemExit(1)
