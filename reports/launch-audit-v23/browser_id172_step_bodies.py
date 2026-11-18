from pathlib import Path
from tempfile import TemporaryDirectory
import ast,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
slugs=next(ast.literal_eval(n.value) for n in ast.parse((ROOT/'server.py').read_text(encoding='utf-8')).body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='OPERATION_SLUGS' for t in n.targets))
with TemporaryDirectory(prefix='paperplane-id172-') as td:
 app,base,_=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   b=p.chromium.launch(channel='chrome',headless=True);page=b.new_page(viewport={'width':390,'height':844});errors=[];page.on('pageerror',lambda e:errors.append(str(e)));tool_results=[]
   for width in (390,820):
    page.set_viewport_size({'width':width,'height':844})
    for operation,slug in slugs.items():
     response=page.goto(base+'/'+slug,wait_until='domcontentloaded',timeout=15000);page.wait_for_function("document.querySelectorAll('.seo-content .seo-howto-step p').length===3",timeout=10000)
     m=page.evaluate("""()=>({viewport:innerWidth,width:document.documentElement.scrollWidth,steps:[...document.querySelectorAll('.seo-content .seo-howto-step')].map(x=>({heading:x.querySelector('h3')?.innerText.trim(),body:x.querySelector('p')?.innerText.trim(),visible:x.getBoundingClientRect().width>0}))})""");row={'operation':operation,'width':width,'status':response.status,'layout_width':m['width'],'steps':m['steps']};tool_results.append(row);assert response.status==200 and m['width']<=width+2 and len(m['steps'])==3 and all(x['body'] and x['visible'] for x in m['steps']),row
   pages=[]
   for route,selector in (('/tool-desk','.tool-desk-quick-steps'),('/download','.download-howto-section .seo-howto-grid')):
    response=page.goto(base+route,wait_until='domcontentloaded');page.wait_for_function(f"document.querySelectorAll('{selector} .seo-howto-step p').length===3");data=page.evaluate(f"""()=>({{width:document.documentElement.scrollWidth,viewport:innerWidth,heading:document.querySelector('{selector}').previousElementSibling?.innerText||document.querySelector('{selector}').parentElement.querySelector('h3')?.innerText,cards:[...document.querySelectorAll('{selector} .seo-howto-step')].map(c=>({{title:c.querySelector('h3')?.innerText,body:c.querySelector('p')?.innerText}}))}})""");pages.append({'route':route,'status':response.status,**data});assert response.status==200 and data['width']<=data['viewport']+2 and len(data['cards'])==3 and all(c['body'] for c in data['cards'])
   assert not errors
   page.set_viewport_size({'width':390,'height':844});page.goto(base+'/download',wait_until='domcontentloaded');page.screenshot(path=str(OUT/'id172-download-waitlist-390.png'));page.set_viewport_size({'width':820,'height':844});page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.screenshot(path=str(OUT/'id172-tool-desk-820.png'))
   result={'tool_route_count':len(slugs),'tool_views':tool_results,'other_pages':pages,'page_errors':errors};(OUT/'browser-id172-step-body-responsive.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps({'tool_route_count':len(slugs),'tool_checks':len(tool_results),'other_pages':pages,'page_errors':errors},indent=2));b.close()
 finally:app.terminate();app.wait(timeout=5)
