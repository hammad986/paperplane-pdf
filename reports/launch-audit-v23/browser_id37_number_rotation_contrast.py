from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]; sys.path.insert(0,str(root/'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='number-rotation-') as tmp:
 d=Path(tmp); src=d/'source.pdf'
 with fitz.open() as doc:
  for angle in (0,90,180,270):
   p=doc.new_page(width=400,height=300); p.draw_rect(p.rect,fill=(0,0,0)); p.set_cropbox(fitz.Rect(40,30,360,270)); p.set_rotation(angle)
  doc.save(src)
 app,base,_=helper.start_server(d/'data')
 try:
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
   except OSError: time.sleep(.2)
  results=[]
  with sync_playwright() as pw:
   browser=pw.chromium.launch(channel='chrome',headless=True)
   for rnd in (1,2):
    context=browser.new_context(accept_downloads=True); page=context.new_page(); posts=[]; errors=[]
    page.on('pageerror',lambda e:errors.append(str(e))); context.on('request',lambda r:posts.append(r.url) if r.method=='POST' and r.url.endswith('/api/jobs') else None)
    page.goto(base+'/add-page-numbers-to-pdf',wait_until='domcontentloaded'); page.locator('#file-input').set_input_files(str(src)); page.locator('#format').select_option(label='{n}'); page.locator('#position').select_option(label='Header left'); page.locator('#mark_color').fill('#000000'); page.locator('#mark_background').select_option('dark'); page.locator('#run-button').click(); page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
    with page.expect_download() as ev: page.locator('#result-download-link').click()
    out=d/f'out{rnd}.pdf'; ev.value.save_as(out)
    with fitz.open(out) as result:
     for i,p in enumerate(result):
      words=p.get_text('words'); assert len(words)==1 and words[0][4]==str(i+1),words
      rect=fitz.Rect(words[0][:4])*p.rotation_matrix
      assert 18 < rect.x0 < 30 and 20 < rect.y0 < 42,(i,rect,p.rect)
      pix=p.get_pixmap(alpha=False); assert max(pix.samples)>180, 'white outline missing'
    assert not posts and not errors,(posts,errors)
    results.append({'round':rnd,'rotations':[0,90,180,270],'cropped_page_position_checked':True,'dark_outline_visible':True,'text_extracted_once':True,'job_posts':0,'errors':errors}); context.close()
   browser.close()
  report={'result':'PASS','rounds':results}; (root/'reports/launch-audit-v23/browser-id37-number-rotation-contrast.json').write_text(json.dumps(report,indent=2)); print(json.dumps(report))
 finally:
  app.terminate()
  try: app.wait(timeout=15)
  except Exception: app.kill()
