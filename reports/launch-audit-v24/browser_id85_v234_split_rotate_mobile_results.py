"""Current-source mobile result-card content check for Split and Rotate."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id85-v233-') as td:
 tmp=Path(td);fixture=tmp/'id85-three-pages.pdf'
 with fitz.open() as doc:
  for n in range(1,4):
   page=doc.new_page();page.insert_text((60,80),f'ID85 MOBILE RESULT PAGE {n} MARKER')
  doc.save(fixture)
 app,base,_=helper.start_server(tmp/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(150):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  else:raise RuntimeError('server did not start')
  evidence={'candidate':'app.js v234/styles.css v89/service worker v209','checks':[],'page_errors':[],'console_errors':[]}
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for width,height in [(320,640),(390,844)]:
    for route,operation,expected in [('/split-pdf','split',(2,3)),('/rotate-pdf','rotate',(1,2,3))]:
     page=browser.new_page(viewport={'width':width,'height':height},accept_downloads=True)
     page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
     page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
     page.goto(base+route,wait_until='domcontentloaded');page.wait_for_function("typeof state !== 'undefined' && typeof state.operation === 'string'")
     if page.evaluate('state.operation')!=operation:page.evaluate(f"window.selectOperation('{operation}')")
     page.locator('#file-input').set_input_files(str(fixture));page.wait_for_function('state.files?.length===1')
     if operation=='split':
      page.locator('#split_mode').select_option('range');page.locator('#pages').fill('2-3')
     else:page.locator('#degrees').select_option('90')
     page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=60000)
     page.wait_for_timeout(900)
     dims=page.evaluate('''()=>{const rect=e=>{if(!e||e.hidden||getComputedStyle(e).display==='none')return null;const r=e.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};const nav=document.querySelector('.mobile-workspace-bar');const navR=rect(nav);const result=document.querySelector('#result');const actions=[...document.querySelectorAll('#result .result-actions > *')].map(e=>({label:e.innerText.trim(),...rect(e)}));return {viewport:{width:innerWidth,height:innerHeight},documentWidth:document.documentElement.scrollWidth,scrollY:window.scrollY,result:rect(result),actions,nav:navR,toast:rect(document.querySelector('.toast-notice'))}}''')
     with page.expect_download(timeout=30000) as di:page.locator('#result-download-link').click()
     download=di.value;out=tmp/f'{width}-{operation}-{download.suggested_filename}';download.save_as(out)
     with fitz.open(out) as doc:
      count=doc.page_count;text='\n'.join(x.get_text() for x in doc);rotations=[x.rotation for x in doc]
     expected_markers=[f'ID85 MOBILE RESULT PAGE {n} MARKER' for n in expected]
     content_ok=count==len(expected) and all(x in text for x in expected_markers) and (operation!='rotate' or all(r==90 for r in rotations))
     action_ok=all(a['left']>=0 and a['right']<=width and a['height']>=44 and (not dims['nav'] or a['bottom']<=dims['nav']['top'] or a['top']>=dims['nav']['bottom']) for a in dims['actions'])
     assert content_ok,(route,width,count,text,rotations)
     assert action_ok and dims['documentWidth']<=width,(route,width,dims)
     page.screenshot(path=str(OUT/f'browser-id85-v234-{operation}-{width}x{height}.png'))
     evidence['checks'].append({'route':route,'operation':operation,'viewport':f'{width}x{height}','download':download.suggested_filename,'pages':count,'rotations':rotations,'content_markers':expected_markers,'content_checked':content_ok,'actions':dims['actions'],'navigation':dims['nav'],'no_overflow':dims['documentWidth']<=width,'actions_unobstructed':action_ok,'result':'passed'})
     page.close()
   browser.close()
  evidence['result']='passed' if len(evidence['checks'])==4 and not evidence['page_errors'] and not evidence['console_errors'] else 'failed'
  (OUT/'browser-id85-v233-split-rotate-mobile-results.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
  print(json.dumps(evidence,indent=2))
  if evidence['result']!='passed':raise SystemExit(1)
 finally:app.terminate();app.wait(timeout=5)
