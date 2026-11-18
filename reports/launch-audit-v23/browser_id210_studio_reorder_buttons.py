from pathlib import Path
from tempfile import TemporaryDirectory
import base64,fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id210-') as tmp:
 root=Path(tmp);pdf=root/'order.pdf'
 with fitz.open() as d:
  for label in ('ID210 PAGE ALPHA','ID210 PAGE BETA','ID210 PAGE GAMMA'): d.new_page().insert_text((72,72),label)
  d.save(pdf)
 app,base,_=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  rounds=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for n in (1,2):
    page=browser.new_page(viewport={'width':1920,'height':1080});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf))
    page.wait_for_function("window.PaperplanePageOrganizer?.state.totalCount===3 && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=30000)
    page.locator('#btn-mode-organize').click()
    move_orders=[]
    for page_num,button_id in ((2,'batch-move-down-btn'),(3,'batch-move-up-btn')):
     card=page.locator(f'.organizer-thumb-card[data-page="{page_num}"]');card.locator('.thumb-checkbox-label').click()
     button=page.locator('#'+button_id);button.wait_for(state='visible');box=button.bounding_box();hit=page.evaluate("([x,y])=>{const e=document.elementFromPoint(x,y);return e?.id||e?.closest('button')?.id||e?.className}",[box['x']+box['width']/2,box['y']+box['height']/2])
     assert box and box['x']>=0 and box['x']+box['width']<=1920 and box['y']>=0 and box['y']+box['height']<=1080 and hit==button_id,{'box':box,'hit':hit}
     button.click();page.wait_for_function("document.querySelector('.toast-notice')?.textContent.includes('reordered successfully')",timeout=30000)
     page.wait_for_timeout(150)
     data=page.evaluate("""async()=>{const f=window.PaperplaneEditor?.editorState?.sourceFile;if(!f)return null;const a=new Uint8Array(await f.arrayBuffer());let b='';for(let i=0;i<a.length;i+=8192)b+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(b)}""")
     temp_pdf=OUT/f'id210-round{n}-step{len(move_orders)+1}.pdf';temp_pdf.write_bytes(base64.b64decode(data))
     with fitz.open(temp_pdf) as doc:move_orders.append([x.get_text() for x in doc])
    payload=page.evaluate("""async()=>{const f=window.PaperplaneEditor?.editorState?.sourceFile;if(!f)return null;const a=new Uint8Array(await f.arrayBuffer());let b='';for(let i=0;i<a.length;i+=8192)b+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(b)}""")
    assert payload
    out=OUT/f'id210-reordered-round{n}.pdf';out.write_bytes(base64.b64decode(payload))
    with fitz.open(out) as d:texts=[p.get_text() for p in d]
    assert len(move_orders)==2 and 'ID210 PAGE GAMMA' in move_orders[0][1] and 'ID210 PAGE BETA' in move_orders[0][2],move_orders
    assert len(texts)==3 and all(s in texts[i] for i,s in enumerate(('ID210 PAGE ALPHA','ID210 PAGE BETA','ID210 PAGE GAMMA'))),texts
    assert not errors,errors
    rounds.append({'round':n,'after_move_later':move_orders[0],'after_move_earlier':move_orders[1],'final_pages':texts,'controls_inside_viewport_and_uncovered':True,'page_errors':errors});page.close()
   browser.close()
  (OUT/'browser-id210-studio-reorder-buttons.json').write_text(json.dumps(rounds,indent=2),encoding='utf-8');print(json.dumps(rounds,indent=2))
 finally:app.terminate();app.wait(timeout=5)

