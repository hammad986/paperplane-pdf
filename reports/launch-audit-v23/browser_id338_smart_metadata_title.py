from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

def make_fixture(path):
 with fitz.open() as pdf:
  page=pdf.new_page(width=612,height=792)
  page.insert_text((72,48),'Provided proper attribution is provided, Google hereby grants permission to use this paper.',fontsize=9)
  page.insert_text((105,170),'Attention Is All You Need',fontsize=26)
  page.insert_text((72,230),'Ashish Vaswani and Noam Shazeer',fontsize=14)
  page.insert_text((72,280),'We propose a new simple network architecture, the Transformer.',fontsize=11)
  pdf.save(path)

with TemporaryDirectory(prefix='paperplane-id338-') as temp:
 root=Path(temp);fixture=root/'attention-is-all-you-need.pdf';make_fixture(fixture)
 app,base,identity=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);page=browser.new_page()
   errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
   page.locator('#ai-file-input').set_input_files(str(fixture))
   page.locator('#ai-active-doc-bar').wait_for(state='visible',timeout=20000)
   with page.expect_response(lambda response:'/api/ai/extract' in response.url,timeout=30000) as response_wait:
    page.locator('#trigger-extract-btn').click()
   response=response_wait.value
   result=response.json()
   page.locator('#extraction-results-modal').wait_for(state='visible',timeout=15000)
   page.locator('#ext-tab-json').click()
   rendered_json=json.loads(page.locator('#extraction-json-code').inner_text())
   data=result.get('data',{})
   evidence={'route':base+'/ai-intelligence','http_status':response.status,'document_title':data.get('general_data',{}).get('title'),'json_view_title':rendered_json.get('general_data',{}).get('title'),'detected_topics':data.get('general_data',{}).get('detected_topics'),'warnings':data.get('warnings'),'page_errors':errors}
   (OUT/'browser-id338-smart-metadata-title.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
   page.screenshot(path=str(OUT/'id338-smart-metadata-title.png'),full_page=True)
   browser.close()
  print(json.dumps(evidence,indent=2))
  assert evidence['http_status']==200 and evidence['document_title']=='Attention Is All You Need' and evidence['json_view_title']=='Attention Is All You Need',evidence
  assert 'provided proper attribution' not in evidence['document_title'].lower()
  assert not errors
 finally:
  app.terminate();app.wait(timeout=5)
