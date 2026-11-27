from __future__ import annotations
import hashlib,json,os,socket,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz,uvicorn
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-id121-sign-canvas-') as td:
 os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'id121-local-admin-key','PAPERPLANE_ADMIN_CODE':'id121-local-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
 sys.path.insert(0,str(root))
 from server import app
 import persistence
 persistence.init_db()
 with fitz.open() as doc:
  page=doc.new_page(width=612,height=792);page.insert_text((60,80),'SIGNATURE SOURCE CONTENT CHECK')
  source=doc.tobytes()
 source_path=Path(td)/'signature-source.pdf';source_path.write_bytes(source)
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=uv.run,daemon=True);thread.start()
 out={'rounds':[],'page_errors':[],'console_errors':[],'file_processing_requests':[]}
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for width in (390,1365):
    context=browser.new_context(viewport={'width':width,'height':844 if width==390 else 900},accept_downloads=True)
    page=context.new_page();errors=[]
    page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
    page.on('console',lambda m:out['console_errors'].append(m.text) if m.type=='error' else None)
    page.on('request',lambda r:out['file_processing_requests'].append(r.url) if any(x in r.url for x in ('/api/jobs','/api/process')) else None)
    page.goto(f'http://127.0.0.1:{port}/sign-pdf',wait_until='domcontentloaded');page.wait_for_function("typeof selectOperation==='function' && document.querySelector('#sign-draw-canvas')")
    canvas=page.locator('#sign-draw-canvas');canvas.scroll_into_view_if_needed();page.wait_for_timeout(100);box=canvas.bounding_box();page.mouse.move(box['x']+22,box['y']+box['height']*.72);page.mouse.down();page.mouse.move(box['x']+box['width']*.25,box['y']+box['height']*.25,steps=5);page.mouse.move(box['x']+box['width']*.5,box['y']+box['height']*.7,steps=5);page.mouse.move(box['x']+box['width']*.78,box['y']+box['height']*.3,steps=5);page.mouse.up()
    ink=page.locator('#signature_data').input_value();page.locator('#signature').fill('Morgan Audit')
    page.locator('#file-input').set_input_files(str(source_path));page.wait_for_function("document.querySelector('#run-button') && !document.querySelector('#run-button').disabled")
    if width==390:page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id121-sign-canvas-mobile-v220.png'),full_page=True)
    page.locator('#run-button').click();page.wait_for_function("!document.querySelector('#result').hidden",timeout=20000)
    name=page.locator('#result-meta').inner_text().split(' · ')[0]
    with page.expect_download() as dl:page.locator('#result-download-link').click()
    download=dl.value;out_pdf=Path(td)/f'sign-{width}.pdf';download.save_as(str(out_pdf))
    with fitz.open(out_pdf) as result:
     txt=result[0].get_text();image_count=len(result[0].get_images(full=True));bbox=fitz.Rect(0,0,0,0)
     for img in result[0].get_images(full=True):
      for item in result[0].get_image_rects(img):bbox|=item
     check={'pages':result.page_count,'text':txt,'image_count':image_count,'signature_image_bbox':list(bbox)}
    out['rounds'].append({'viewport':width,'draw_canvas_visible':canvas.is_visible(),'signature_data_created':ink.startswith('data:image/png;base64,') and len(ink)>500,'canvas_box':box,'result_name':name,'download_name':download.suggested_filename,'sha256':hashlib.sha256(out_pdf.read_bytes()).hexdigest(),'output':check,'button_text':page.locator('#run-button').inner_text()})
    context.close()
   browser.close()
  out['passed']=len(out['rounds'])==2 and all(x['draw_canvas_visible'] and x['signature_data_created'] and x['output']['pages']==1 and 'SIGNATURE SOURCE CONTENT CHECK' in x['output']['text'] and x['output']['image_count']>=1 and x['output']['signature_image_bbox'][2]>x['output']['signature_image_bbox'][0] for x in out['rounds']) and not out['page_errors'] and not out['console_errors'] and not out['file_processing_requests']
 finally:uv.should_exit=True;thread.join(timeout=5)
 (root/'reports/launch-audit-v24/browser-id121-sign-canvas-v220.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
