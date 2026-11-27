"""Verify mobile-aware result scrolling for rich AI cards on current source."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports/launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id402-v234-') as td:
 app,base,_=helper.start_server(Path(td)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(120):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  evidence={'candidate':'app.js v234/styles.css v90/service-worker v210','checks':[],'page_errors':[],'console_errors':[]}
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for width,height in [(320,640),(390,844),(768,900),(1366,900)]:
    page=browser.new_page(viewport={'width':width,'height':height})
    page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
    page.on('console',lambda m:evidence['console_errors'].append(m.text) if m.type=='error' else None)
    page.goto(base+'/summarize-pdf',wait_until='domcontentloaded');page.wait_for_function('typeof showRichAiResult === "function" && document.readyState === "complete"');page.wait_for_timeout(400)
    page.evaluate("showRichAiResult('Executive Summary','Controlled local evidence', '<p>Summary paragraph with a page reference <a href=\"#\">Page 1</a>.</p><div class=\"ai-result-actions\"><a class=\"btn-download\" id=\"rich-download\" href=\"#\">Download PDF</a><button type=\"button\" class=\"btn-secondary-action\" id=\"rich-next\">Open in Studio</button></div>')")
    page.wait_for_timeout(900)
    row=page.evaluate('''()=>{const r=document.querySelector('#result'),nav=document.querySelector('.mobile-workspace-bar'),nr=nav?.getBoundingClientRect();const nodes=[...document.querySelectorAll('#result .ai-result-actions > *')];return {width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth,resultTop:r.getBoundingClientRect().top,resultBottom:r.getBoundingClientRect().bottom,actions:nodes.map(e=>{const x=e.getBoundingClientRect();return {name:e.innerText,top:x.top,bottom:x.bottom,height:x.height,display:getComputedStyle(e).display}}),nav:nr?{top:nr.top,bottom:nr.bottom,height:nr.height}:null}}''')
    row['viewport']=f'{width}x{height}'
    row['actions_visible']=len(row['actions'])==2 and all(a['display']!='none' and a['height']>=(44 if width<=900 else 36) and a['top']>=0 and a['bottom']<=height for a in row['actions'])
    row['actions_clear_of_nav']=not row['nav'] or all(a['bottom']<=row['nav']['top'] or a['top']>=row['nav']['bottom'] for a in row['actions'])
    row['result']='passed' if row['scrollWidth']<=width and row['actions_visible'] and row['actions_clear_of_nav'] else 'failed'
    page.screenshot(path=str(OUT/f'browser-id402-v234-style90-rich-result-{width}x{height}.png'))
    evidence['checks'].append(row);page.close()
   browser.close()
  evidence['result']='passed' if all(x['result']=='passed' for x in evidence['checks']) and not evidence['page_errors'] and not evidence['console_errors'] else 'failed'
  (OUT/'browser-id402-v234-style90-rich-result-mobile-dock.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
  print(json.dumps(evidence,indent=2))
  if evidence['result']!='passed':raise SystemExit(1)
 finally:app.terminate();app.wait(timeout=5)



