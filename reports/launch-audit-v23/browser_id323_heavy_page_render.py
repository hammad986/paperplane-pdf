from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,sys,socket,time,json
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports'/'launch-audit-v23'
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
source=OUT/'fixtures'/'totpdf-sample-scanned.pdf'
with TemporaryDirectory(prefix='paperplane-id323-heavy-') as temp:
 root=Path(temp); fixture=root/'69-image-pages.pdf'
 with fitz.open(source) as one, fitz.open() as heavy:
  for _ in range(69): heavy.insert_pdf(one)
  heavy.save(fixture,deflate=True,garbage=3)
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
   for width,height in [(390,844),(1366,900)]:
    page=browser.new_page(viewport={'width':width,'height':height},is_mobile=width<500,has_touch=width<500)
    errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
    page.goto(base+'/studio',wait_until='domcontentloaded')
    page.locator('#studio-file-input').set_input_files(str(fixture))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent.trim() === '69' && document.querySelector('#studio-loading-overlay')?.hidden === true",timeout=60000)
    first=page.evaluate("""()=>({width:innerWidth,docWidth:document.documentElement.scrollWidth,pageCount:document.querySelector('#page-total-indicator').textContent,firstRendered:document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas').dataset.rendered})""")
    timings=[]
    for n in [4,5,20,69]:
     started=time.perf_counter()
     page.locator(f'.studio-page-sheet[data-page="{n}"]').scroll_into_view_if_needed()
     page.wait_for_function("n=>document.querySelector(`.studio-page-sheet[data-page=\"${n}\"] .pdf-page-canvas`)?.dataset.rendered === 'true'",arg=n,timeout=20000)
     canvas=page.locator(f'.studio-page-sheet[data-page="{n}"] .pdf-page-canvas')
     data=canvas.evaluate("e=>({width:e.width,height:e.height,rendered:e.dataset.rendered})")
     assert data['rendered']=='true' and data['width']>1 and data['height']>1,data
     timings.append({'page':n,'seconds':round(time.perf_counter()-started,3),**data})
    metrics=page.evaluate("""()=>({docWidth:document.documentElement.scrollWidth,width:innerWidth,errors:[],pages:[4,5,20,69].map(n=>{const c=document.querySelector(`.studio-page-sheet[data-page=\"${n}\"] .pdf-page-canvas`),r=c.getBoundingClientRect();return {page:n,width:c.width,height:c.height,visible:r.height>0,rendered:c.dataset.rendered}})})""")
    assert first['pageCount']=='69' and first['firstRendered']=='true',first
    assert metrics['docWidth']<=width and all(x['rendered']=='true' for x in timings),metrics
    assert not errors,errors
    page.screenshot(path=str(OUT/f'id323-69-image-pages-{width}.png'))
    rounds.append({'viewport':width,'fixture_bytes':fixture.stat().st_size,'first_page':first,'later_pages':timings,'layout':metrics,'page_errors':errors})
    page.close()
   browser.close()
  result={'source_fixture':str(source),'source_pages':1,'generated_page_count':69,'generated_bytes':fixture.stat().st_size,'rounds':rounds}
  (OUT/'browser-id323-69-image-page-render.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
  print(json.dumps(result,indent=2))
 finally:
  app.terminate();app.wait(timeout=5)
