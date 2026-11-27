from __future__ import annotations
import json, socket, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
PDF=Path('C:/Users/mdham/Downloads/notes.pdf')
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
rounds=[]
with TemporaryDirectory(prefix='paperplane-id122-width-cache-') as tmp:
 app,base,_=helper.start_server(Path(tmp)/'data')
 try:
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
   except OSError: time.sleep(.2)
  else: raise RuntimeError('Local app failed to start')
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for i in (1,2):
    context=browser.new_context(viewport={'width':390,'height':844},device_scale_factor=3,is_mobile=True,has_touch=True)
    page=context.new_page(); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
    resp=page.goto(base+'/studio',wait_until='domcontentloaded',timeout=30000)
    assert resp and resp.status==200
    page.locator('#studio-file-input').set_input_files(str(PDF))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim()==='69' && document.querySelector('#studio-loading-overlay')?.hidden===true",timeout=90000)
    checks=[]
    for width in (390,320,820,390):
     await_width={'width':width,'height':844 if width<500 else 1180}
     page.set_viewport_size(await_width)
     page.wait_for_function("window.state?.studio?.canvasAreaWidth === document.querySelector('#studio-canvas-area')?.clientWidth && window.state.studio.canvasAreaWidth > 0",timeout=10000)
     page.wait_for_timeout(250)
     m=page.evaluate("""async()=>{
       const area=document.querySelector('#studio-canvas-area');
       const baseWidth=(await window.state.studio.pdfDoc.getPage(1)).getViewport({scale:1}).width;
       return {cache:window.state.studio.canvasAreaWidth,client:area.clientWidth,inner:innerWidth,baseWidth,
         currentScale:window.getStudioPageScale({width:baseWidth})};
     }""")
     # Verify width cache and scale from known source page width, then force a current-page repaint.
     assert m['cache']==m['client'] and m['cache']>0,m
     expected=max(.3,min(1,(m['client']-(28 if width<=900 else 64))/m['baseWidth']))
     assert abs(m['currentScale']-expected)<.02,(m,expected)
     rendered=page.evaluate("window.renderStudioPage(1,{priority:true,force:true})")
     # Playwright evaluate awaits a returned promise.
     assert rendered is True
     canvas=page.locator('.studio-page-sheet[data-page="1"] .pdf-page-canvas')
     assert canvas.get_attribute('data-rendered')=='true'
     checks.append({'viewport':width,'canvas_area_cache_px':m['cache'],'client_width_px':m['client'],'expected_scale':round(expected,4),'rendered_scale':float(canvas.get_attribute('data-rendered-scale'))})
    assert not errors,errors
    rounds.append({'round':i,'checks':checks,'page_errors':errors})
    context.close()
   browser.close()
 finally: app.terminate(); app.wait(timeout=10)
result={'fixture':str(PDF),'fixture_pages':69,'rounds':rounds,'verdict':'PASS'}
(OUT/'browser-id122-canvas-area-width-cache.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result,indent=2))
