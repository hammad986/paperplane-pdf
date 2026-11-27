import fitz,json
from pathlib import Path
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
from io import BytesIO
outdir=Path('reports/launch-audit-v24'); errors=[]; rounds=[]
source=fitz.open()
for marker in ['PAGE_A','PAGE_B','PAGE_C']:
 p=source.new_page();p.insert_text((50,70),marker)
pdf_bytes=source.tobytes();source.close()
with sync_playwright() as p:
 b=p.chromium.launch(); page=b.new_page(viewport={'width':1366,'height':900});page.set_default_timeout(15000);page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
 for n in (1,2):
  page.goto('http://127.0.0.1:8767/organize-pdf',wait_until='domcontentloaded');page.locator('#tool-title').wait_for()
  print('round',n,'upload',flush=True)
  page.locator('#file-input').set_input_files({'name':f'id70-{n}.pdf','mimeType':'application/pdf','buffer':pdf_bytes})
  print('uploaded',flush=True)
  page.get_by_role('button',name='Move page 3 earlier').click()
  print('moved',flush=True)
  input=page.locator('#view-tool-desk input[type=text]')
  order=input.input_value()
  if order!='1,3,2': raise AssertionError(f'round {n}: visual reorder did not synchronize: {order}')
  async_download=None
  print('submit',flush=True)
  page.locator('#run-button').click()
  page.wait_for_function("() => !document.querySelector('#result')?.hidden && !document.querySelector('#result-download-link')?.hidden",timeout=30000)
  print('result-ready',flush=True)
  with page.expect_download(timeout=15000) as info:
   page.locator('#result-download-link').click()
  download=info.value; target=outdir/f'browser-id70-reordered-round{n}.pdf';download.save_as(target)
  reader=PdfReader(str(target)); extracted=[pg.extract_text() for pg in reader.pages]
  order_markers=[next((m for m in ['PAGE_A','PAGE_B','PAGE_C'] if m in (tx or '')),None) for tx in extracted]
  rounds.append({'round':n,'page_count':len(reader.pages),'order_field':order,'page_markers':order_markers,'download_name':download.suggested_filename,'file_bytes':target.stat().st_size,'content_checked':len(reader.pages)==3 and order_markers==['PAGE_A','PAGE_C','PAGE_B']})
 b.close()
result={'build':'app.js v191/styles.css v71/service-worker v143','operation':'Page Organizer','browser_rounds':rounds,'browser_errors':errors,'passed':len(rounds)==2 and all(r['content_checked'] for r in rounds) and not errors}
(outdir/'browser-id70-page-organizer-reorder.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))