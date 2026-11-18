from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id156-') as td:
 root=Path(td);src=root/'three-pages.pdf'
 with fitz.open() as d:
  for n in range(1,4):d.new_page().insert_text((72,72),f'SPLIT-PAGE-MARKER-{n}')
  d.save(src)
 app,base,_=h.start_server(root/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);rounds=[]
   for n in (1,2):
    c=b.new_context(viewport={'width':1366,'height':900},accept_downloads=True);page=c.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)));page.goto(base+'/split-pdf',wait_until='domcontentloaded');page.locator('#file-input').set_input_files(str(src));page.wait_for_function("document.querySelector('#run-button')&&!document.querySelector('#run-button').disabled");opt=page.locator('#split_mode');label=opt.locator('option[value="all_pages"]').inner_text();opt.select_option('all_pages');page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
    with page.expect_download(timeout=20000) as ev:page.locator('#result-download-link').click()
    dl=ev.value;target=root/f'split-round{n}.zip';dl.save_as(target);items=[]
    with ZipFile(target) as z:
     for name in sorted(z.namelist()):
      data=z.read(name)
      try:
       with fitz.open(stream=data,filetype='pdf') as pdf:items.append({'name':name,'pages':pdf.page_count,'text':pdf[0].get_text().strip()})
      except Exception as ex:items.append({'name':name,'error':str(ex)})
    row={'round':n,'option_label':label,'download_name':dl.suggested_filename,'zip_member_count':len(items),'members':items,'page_errors':errs};assert 'PDFs (ZIP)' in label and target.read_bytes().startswith(b'PK') and len(items)==3 and all(item.get('pages')==1 and f'SPLIT-PAGE-MARKER-{i}' in item['text'] for i,item in enumerate(items,1)) and not errs
    page.screenshot(path=str(OUT/f'id156-split-all-pages-round{n}.png'));rounds.append(row);c.close()
   result={'rounds':rounds};(OUT/'browser-id156-split-label-output.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
