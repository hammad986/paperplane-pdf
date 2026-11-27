"""Measure Run-button overlap with fixed mobile navigation across all operations."""
import json,socket,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper  # noqa: E402

def main():
 errors=[]; checks=[]
 with TemporaryDirectory(prefix='paperplane-v224-layout-matrix-') as td:
  app,base,_=helper.start_server(Path(td)/'data')
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(150):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError: time.sleep(.2)
   else: raise RuntimeError('local server did not start')
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844})
    page.on('pageerror',lambda e:errors.append(str(e)))
    page.on('console',lambda m:errors.append(m.text) if m.type=='error' else None)
    response=page.goto(base+'/',wait_until='domcontentloaded')
    keys=page.evaluate('Object.keys(state.operations)')
    for width,height in ((390,844),(320,568),(1366,900)):
     page.set_viewport_size({'width':width,'height':height})
     for key in keys:
      page.evaluate('key=>selectOperation(key)',key)
      page.wait_for_function('arg=>state.operation===arg.key && document.querySelector("#tool-title")?.textContent===arg.label',arg={'key':key,'label':page.evaluate('key=>state.operations[key]?.label',key)},timeout=5000)
      page.wait_for_timeout(300)
      data=page.evaluate('''()=>{const btn=document.querySelector('#run-button'),nav=document.querySelector('.mobile-workspace-bar'),title=document.querySelector('#tool-title'),topbar=document.querySelector('.topbar'),drop=document.querySelector('#dropzone');if(!btn)return null;const r=btn.getBoundingClientRect(),n=nav?.getBoundingClientRect(),t=title?.getBoundingClientRect(),h=topbar?.getBoundingClientRect(),d=drop?.getBoundingClientRect();return {button:[r.left,r.top,r.right,r.bottom],buttonVisible:!btn.hidden&&r.width>0&&r.height>0,nav:n? [n.left,n.top,n.right,n.bottom]:null,overlap:!!(n&&r.left<n.right&&r.right>n.left&&r.top<n.bottom&&r.bottom>n.top),overlapPx:n?Math.max(0,Math.min(n.bottom,r.bottom)-Math.max(n.top,r.top)):0,title:t?[t.left,t.top,t.right,t.bottom]:null,topbar:h?[h.left,h.top,h.right,h.bottom]:null,dropzone:d?[d.left,d.top,d.right,d.bottom]:null,titleVisible:!!(t&&t.width>0&&t.top>=(h?.bottom||0)&&t.bottom<innerHeight),pageOverflow:document.documentElement.scrollWidth>innerWidth}}''')
      after_wheel=None
      if data: checks.append({'width':width,'height':height,'operation':key,**data,'after_wheel':after_wheel})
     if width==390:
      page.goto(base+'/merge-pdf',wait_until='domcontentloaded'); page.wait_for_timeout(300)
      page.screenshot(path=str(ROOT/'reports/launch-audit-v24/browser-v224-merge-pdf-mobile-390-after.png'))
    browser.close()
  finally:
   app.terminate(); app.wait(timeout=5)
 summary={'operation_count':len(keys),'checks':len(checks),'page_errors':errors,'overflow':[x for x in checks if x['pageOverflow']],'intersections':[x for x in checks if x['overlap']]}
 summary['no_intersections_at_390_for_short_workflows']=not any(x['overlap'] for x in checks if x['width']==390 and x['operation'] in {'merge','split','remove','rotate','repair','pdf_to_jpg','ai_extract','photo_merge'})
 summary['all_mobile_actions_clear_of_navigation']=all(not x['overlap'] for x in checks if x['width']<=900)
 summary['mobile_tool_titles_remain_visible']=all(x['titleVisible'] for x in checks if x['width']<=900)
 summary['passed']=len(checks)==132 and not errors and not summary['overflow'] and summary['no_intersections_at_390_for_short_workflows'] and summary['all_mobile_actions_clear_of_navigation'] and summary['mobile_tool_titles_remain_visible']
 (ROOT/'reports/launch-audit-v24/browser-v224-run-button-nav-intersection.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
 print(json.dumps({'operation_count':len(keys),'checks':len(checks),'remaining_intersections':len(summary['intersections']),'no_x_overflow':not summary['overflow'],'short_workflows_clear':summary['no_intersections_at_390_for_short_workflows'],'all_mobile_actions_clear':summary['all_mobile_actions_clear_of_navigation'],'mobile_titles_visible':summary['mobile_tool_titles_remain_visible'],'browser_errors':errors,'passed':summary['passed']},indent=2))
 if not summary['passed']: raise SystemExit(1)
if __name__=='__main__': main()
