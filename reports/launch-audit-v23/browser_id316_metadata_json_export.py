from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent
with TemporaryDirectory(prefix='paperplane-id316-') as temp:
 root=Path(temp);source=root/'metadata-source.pdf'
 with fitz.open() as pdf:
  page=pdf.new_page();page.insert_text((72,72),'Metadata JSON export verification source.')
  pdf.set_metadata({'title':'Original title','author':'Original author','subject':'Original subject','creator':'Original creator','producer':'Original producer'})
  pdf.save(source)
 app,base,identity=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  errors=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   context=browser.new_context(accept_downloads=True,viewport={'width':1366,'height':900})
   page=context.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(base+'/pdf-metadata',wait_until='domcontentloaded')
   page.locator('#file-input').set_input_files(str(source))
   page.locator('#run-button').wait_for(state='visible',timeout=10000)
   page.wait_for_function("!document.querySelector('#run-button').disabled",timeout=15000)
   page.locator('#title').fill('Metadata JSON roundtrip')
   page.locator('#author').fill('Paperplane Test Author')
   page.locator('#subject').fill('Metadata export verification')
   with page.expect_response(lambda r:'/api/jobs' in r.url and r.request.method=='POST',timeout=15000) as job_wait:
    page.locator('#run-button').click()
   job_response=job_wait.value
   page.wait_for_function("document.querySelector('#result')?.hidden === false",timeout=45000)
   page.locator('#metadata-json-result').wait_for(state='visible',timeout=20000)
   page.wait_for_function("document.querySelector('#metadata-json-output')?.textContent.includes('Metadata JSON roundtrip')",timeout=20000)
   with page.expect_download(timeout=15000) as json_download_wait:
    page.locator('#metadata-json-export-btn').click()
   json_download=json_download_wait.value
   json_path=root/'metadata-output.json';json_download.save_as(str(json_path));metadata_json=json.loads(json_path.read_text(encoding='utf-8'))
   with page.expect_download(timeout=15000) as pdf_download_wait:
    page.locator('#result-download-link').click()
   pdf_download=pdf_download_wait.value;pdf_path=root/'metadata-output.pdf';pdf_download.save_as(str(pdf_path))
   with fitz.open(pdf_path) as output_pdf:
    pdf_meta=output_pdf.metadata
    page_count=output_pdf.page_count
   compared_fields={'title':'title','author':'author','subject':'subject','keywords':'keywords','creator':'creator','producer':'producer','creation_date':'creationDate','modification_date':'modDate'}
   fields_match=all(metadata_json.get(json_key)==pdf_meta.get(pdf_key) for json_key,pdf_key in compared_fields.items())
   evidence={'route':base+'/pdf-metadata','job_http_status':job_response.status,'json_download_name':json_download.suggested_filename,'json_download_bytes':json_path.stat().st_size,'json':metadata_json,'pdf_download_name':pdf_download.suggested_filename,'pdf_download_bytes':pdf_path.stat().st_size,'pdf_pages':page_count,'pdf_metadata':pdf_meta,'metadata_fields_match_downloaded_pdf':fields_match,'json_preview_matches_download':page.locator('#metadata-json-output').inner_text()==json.dumps(metadata_json,indent=2),'page_errors':errors}
   page.screenshot(path=str(OUT/'id316-metadata-json-export.png'),full_page=True)
   context.close();browser.close()
  (OUT/'browser-id316-metadata-json-export.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
  print(json.dumps(evidence,indent=2))
  assert evidence['job_http_status']==202 and evidence['json_download_name'].endswith('.metadata.json') and metadata_json['title']=='Metadata JSON roundtrip' and metadata_json['author']=='Paperplane Test Author' and evidence['pdf_download_bytes']>500 and evidence['metadata_fields_match_downloaded_pdf'] and evidence['json_preview_matches_download'] and not errors,evidence
 finally:
  app.terminate();app.wait(timeout=5)
