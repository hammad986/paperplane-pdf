import json,fitz
from pathlib import Path
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
from io import BytesIO
fixture=Path('reports/launch-audit-v23/orimi-pdf-test.pdf').read_bytes(); results=[]; errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch()
 for n in (1,2):
  page=browser.new_page(viewport={'width':1366,'height':900});page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
  for route,files in [('/merge-pdf',[{'name':f'orimi-{n}-a.pdf','mimeType':'application/pdf','buffer':fixture},{'name':f'orimi-{n}-b.pdf','mimeType':'application/pdf','buffer':fixture}]),('/rotate-pdf',[{'name':f'orimi-{n}-rotate.pdf','mimeType':'application/pdf','buffer':fixture}])]:
   page.goto('http://127.0.0.1:8767'+route,wait_until='domcontentloaded');page.locator('#tool-title').wait_for()
   toggle=page.locator('#client-privacy-toggle')
   if toggle.is_enabled() and toggle.is_checked(): page.locator('#sidebar label.toggle-switch-sm').click()
   page.locator('#file-input').set_input_files(files)
   page.wait_for_function("()=>!document.querySelector('#run-button')?.disabled")
   page.locator('#run-button').click();page.wait_for_function("()=>!document.querySelector('#result')?.hidden && !document.querySelector('#result-download-link')?.hidden",timeout=60000)
   with page.expect_download(timeout=15000) as d: page.locator('#result-download-link').click()
   download=d.value; saved=Path('reports/launch-audit-v24')/f'id150-current-{n}-{route.rsplit("/",1)[-1]}.pdf';download.save_as(saved);data=saved.read_bytes()
   reader=PdfReader(BytesIO(data));texts=[p.extract_text() or '' for p in reader.pages];marker=any('orimi' in t.lower() or 'pdf test' in t.lower() for t in texts)
   rotations=[p.get('/Rotate',0) for p in reader.pages]
   results.append({'round':n,'route':route,'download_name':download.suggested_filename,'bytes':len(data),'pages':len(reader.pages),'rotations':rotations,'source_marker':marker,'result_text':page.locator('#result').inner_text() if page.locator('#result').count() and not page.locator('#result').is_hidden() else ''})
  page.close()
 browser.close()
result={'build':'app.js v191/styles71/service-worker143','fixture':'reports/launch-audit-v23/orimi-pdf-test.pdf','checks':results,'browser_errors':errors,'passed':len(results)==4 and all(x['bytes']>1000 and x['source_marker'] and not any(term in x['result_text'].lower() for term in ['error','failed','protected pdf detected']) and (x['route']!='/rotate-pdf' or 90 in x['rotations']) for x in results) and not errors}
Path('reports/launch-audit-v24/browser-id150-orimi-current-image.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))