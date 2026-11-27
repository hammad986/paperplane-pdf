import io,json,random
from pathlib import Path
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright
random.seed(210)
im=Image.new('RGB',(800,600),'white');draw=ImageDraw.Draw(im)
for i in range(500):
 x=random.randrange(800);y=random.randrange(600);draw.rectangle((x,y,x+3,y+3),fill=(random.randrange(256),random.randrange(256),random.randrange(256)))
buf=io.BytesIO();im.save(buf,format='JPEG',quality=94);blob=buf.getvalue()
small=Image.new('RGB',(120,80),(40,120,200));b2=io.BytesIO();small.save(b2,format='JPEG');small_data=b2.getvalue()
errors=[];checks=[]
with sync_playwright() as p:
 browser=p.chromium.launch()
 for n in (1,2):
  page=browser.new_page(viewport={'width':1366,'height':900});page.set_default_timeout(20000);page.on('pageerror',lambda e:errors.append(str(e)));page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None);requests=[];page.on('request',lambda r:requests.append(r.url) if '/api/' in r.url else None)
  for route,inputs in [('/ssc-photo-resizer',[{'name':f'ssc-{n}.jpg','mimeType':'image/jpeg','buffer':blob}]),('/compress-image-online',[{'name':f'compress-{n}.jpg','mimeType':'image/jpeg','buffer':blob}]),('/resize-image-dimensions',[{'name':f'resize-{n}.jpg','mimeType':'image/jpeg','buffer':blob}]),('/merge-photos-online',[{'name':f'merge-{n}-a.jpg','mimeType':'image/jpeg','buffer':small_data},{'name':f'merge-{n}-b.jpg','mimeType':'image/jpeg','buffer':small_data}])]:
   page.goto('http://127.0.0.1:8767'+route,wait_until='domcontentloaded');page.wait_for_function("()=>window.state?.operation")
   toggle=page.locator('#client-privacy-toggle');local=toggle.is_checked();disabled=toggle.is_disabled()
   if route=='/resize-image-dimensions':
    if page.locator('#width').count():page.locator('#width').fill('160')
    if page.locator('#height').count():page.locator('#height').fill('120')
   page.locator('#file-input').set_input_files(inputs);page.wait_for_function("()=>!document.querySelector('#run-button')?.disabled")
   before=len(requests);page.locator('#run-button').click();page.wait_for_function("()=>!document.querySelector('#result')?.hidden && !document.querySelector('#result-download-link')?.hidden",timeout=60000)
   newrequests=[u for u in requests[before:] if any(x in u for x in ['/api/jobs','/api/operations','/api/process'])]
   with page.expect_download(timeout=15000) as ev:page.locator('#result-download-link').click()
   download=ev.value;target=Path('reports/launch-audit-v24')/f'id152-{n}-{route.rsplit("/",1)[-1]}{Path(download.suggested_filename).suffix}';download.save_as(target);data=target.read_bytes();dims=None;pages=None
   try:
    out=Image.open(io.BytesIO(data));dims=list(out.size);out.verify()
   except Exception:
    try:
     from pypdf import PdfReader
     rr=PdfReader(io.BytesIO(data));pages=len(rr.pages);dims=[round(float(rr.pages[0].mediabox.width)),round(float(rr.pages[0].mediabox.height))]
    except Exception: pass
   checks.append({'round':n,'route':route,'download':download.suggested_filename,'bytes':len(data),'image_dimensions':dims,'pdf_pages':pages,'local_toggle_checked':local,'toggle_disabled':disabled,'file_operation_api_requests':newrequests})
  page.close()
 browser.close()
result={'build':'app191/styles71','feature':'four photo/image tools process in browser','checks':checks,'browser_errors':errors,'passed':len(checks)==8 and all(x['bytes']>500 and x['local_toggle_checked'] and x['toggle_disabled'] and not x['file_operation_api_requests'] for x in checks) and not errors}
Path('reports/launch-audit-v24/browser-id152-photo-tools-local-processing.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))