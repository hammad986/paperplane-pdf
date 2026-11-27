from pathlib import Path
import json, os, zipfile, xml.etree.ElementTree as ET
import fitz
from docx import Document
from playwright.sync_api import sync_playwright
BASE=os.environ.get('PAPERPLANE_TEST_BASE','http://127.0.0.1:8501'); OUT=Path('reports/launch-audit-v23'); RUNTIME=os.environ.get('PAPERPLANE_TEST_RUNTIME','local')
SOURCE=OUT/'fixtures/id37-local-text-12-pages.pdf'
with fitz.open() as pdf:
 for number in range(1,13):
  page=pdf.new_page()
  if number==1: page.insert_text((72,65),'Document Test Report',fontsize=20)
  page.insert_text((72,100),f'LOCAL_PAGE_MARKER_{number:02d}',fontsize=12)
  page.insert_text((72,130),f'Editable text from page {number}: Munich central station service update.',fontsize=12)
  page.insert_text((72,160),f'Café fare {19.50+number:.2f}; details stay searchable.',fontsize=12)
 pdf.save(SOURCE,garbage=4,deflate=True)
results=[]
with sync_playwright() as p:
 browser=p.chromium.launch(channel='chrome',headless=True)
 for round_no in (1,2):
  context=browser.new_context(accept_downloads=True,viewport={'width':1366,'height':900})
  page=context.new_page(); errors=[]; job_posts=[]
  page.on('pageerror',lambda e:errors.append(str(e)))
  page.on('request',lambda r:job_posts.append(r.url) if '/api/jobs' in r.url and r.method=='POST' else None)
  response=page.goto(BASE+'/pdf-to-word',wait_until='domcontentloaded')
  assert response and response.status==200
  page.locator('#file-input').set_input_files(str(SOURCE))
  page.locator('#run-button').wait_for(state='visible',timeout=10000)
  page.locator('#run-button').click()
  page.wait_for_function("document.querySelector('#result')?.hidden === false",timeout=30000)
  with page.expect_download(timeout=30000) as download_wait:
   page.locator('#result-download-link').click()
  download=download_wait.value; target=OUT/f'id37-local-pdf-to-word-{RUNTIME}-round{round_no}.docx'; download.save_as(target)
  with zipfile.ZipFile(target) as archive:
   bad_member=archive.testzip(); xml=archive.read('word/document.xml'); ET.fromstring(xml)
   doc=Document(target); text='\n'.join(paragraph.text for paragraph in doc.paragraphs)
   page_breaks=xml.count(b'<w:pageBreakBefore/>')
  markers=sum(f'LOCAL_PAGE_MARKER_{number:02d}' in text for number in range(1,13))
  result={'round':round_no,'app_asset':page.locator('script[src*="app.js"]').get_attribute('src'),'download_name':download.suggested_filename,'bytes':target.stat().st_size,'valid_zip':bad_member is None,'paragraph_count':len(doc.paragraphs),'page_break_count':page_breaks,'page_markers_preserved':markers,'accented_text_preserved':'Café' in text,'no_job_post':not job_posts,'page_errors':errors}
  results.append(result)
  assert result['valid_zip'] and page_breaks==11 and markers==12 and result['accented_text_preserved'] and result['no_job_post'] and not errors,result
  context.close()
 browser.close()
result={'runtime':RUNTIME,'base':BASE,'source':SOURCE.name,'source_pages':12,'rounds':results}
(OUT/f'browser-id37-local-pdf-to-word-{RUNTIME}.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
