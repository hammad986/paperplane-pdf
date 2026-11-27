import base64, json
from pathlib import Path
import fitz
from playwright.sync_api import sync_playwright
pdfpath=Path('reports/launch-audit-v24/id322-three-page-output.pdf')
with fitz.open() as d:
 for n in range(1,4): d.new_page().insert_text((72,72),f'ID322 page {n}')
 d.save(pdfpath)
b64=base64.b64encode(pdfpath.read_bytes()).decode('ascii')
result={}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':1366,'height':900}); errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8774/',wait_until='domcontentloaded')
 page.wait_for_function('window.showDownloadResult && window.PaperplanePdfRuntime')
 page.evaluate("window.selectOperation('merge')")
 page.evaluate('''b64=>{const bytes=Uint8Array.from(atob(b64),c=>c.charCodeAt(0));const blob=new Blob([bytes],{type:'application/pdf'});window.state.operation='merge';window.showDownloadResult({output_name:'id322-three-page-output.pdf',output_size:blob.size,page_count:3},URL.createObjectURL(blob),{blob});}''',b64)
 page.wait_for_function("document.querySelector('#result-meta')?.textContent.includes('3 pages')")
 meta=page.locator('#result-meta').inner_text()
 result={'route':page.url,'resultMeta':meta,'downloadVisible':page.locator('#result-download-link').is_visible(),'viewInStudioVisible':page.locator('#result-view-studio-btn').is_visible(),'pageErrors':errors}
 b.close()
Path('reports/launch-audit-v24/browser-id322-v203-result-pagecount.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
if '3 pages' not in meta or not result['downloadVisible'] or errors: raise SystemExit(1)
