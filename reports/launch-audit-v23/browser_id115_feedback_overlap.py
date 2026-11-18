from pathlib import Path
from tempfile import TemporaryDirectory
import fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id115-') as temp:
 root=Path(temp);pdf=root/'widget-studio.pdf'
 with fitz.open() as d:d.new_page().insert_text((72,72),'Studio feedback overlap check.');d.save(pdf)
 app,base,_=helper.start_server(root/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);reports=[]
   for n in (1,2):
    ctx=browser.new_context(viewport={'width':390,'height':844});page=ctx.new_page();errs=[];page.on('pageerror',lambda e:errs.append(str(e)))
    page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.wait_for_selector('.home-tool-card',timeout=15000);page.evaluate("()=>{const e=document.querySelector('#pp-feedback-launcher');if(e)e.hidden=false}")
    page.wait_for_timeout(150)
    launcher=page.locator('#pp-feedback-launcher');lr=launcher.bounding_box()
    cards=page.locator('.home-tool-card');ncard=cards.count();last=cards.nth(max(ncard-1,0));last.scroll_into_view_if_needed();page.wait_for_timeout(100)
    last_rect=last.bounding_box();intersects=lambda a,b: bool(a and b and a['x']<b['x']+b['width'] and a['x']+a['width']>b['x'] and a['y']<b['y']+b['height'] and a['y']+a['height']>b['y'])
    tool_overlap=intersects(launcher.bounding_box(),last_rect)
    page.goto(base+'/studio',wait_until='domcontentloaded');page.locator('#studio-file-input').set_input_files(str(pdf));page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
    page.evaluate("()=>{const e=document.querySelector('#pp-feedback-launcher');if(e)e.hidden=false}");page.wait_for_timeout(100)
    zoom=page.locator('#zoom-select');zoom.scroll_into_view_if_needed();zr=zoom.bounding_box();fr=launcher.bounding_box();studio_overlap=intersects(fr,zr)
    page.screenshot(path=str(OUT/f'id115-widget-studio-round{n}.png'))
    modal_checks=[]
    for selector in ('#auth-modal','#upgrade-modal'):
     page.evaluate("sel=>{document.querySelectorAll('.modal-backdrop').forEach(x=>x.hidden=true);const m=document.querySelector(sel);if(m)m.hidden=false}",selector);page.wait_for_timeout(50)
     display=page.locator('#pp-feedback-container').evaluate("e=>getComputedStyle(e).display");modal_checks.append({'modal':selector,'feedback_display':display,'hidden_behind_modal':display=='none'})
    report={'round':n,'tool_cards':ncard,'tool_last_card_feedback_overlap':tool_overlap,'tool_launcher_rect':fr,'last_card_rect':last_rect,'studio_zoom_feedback_overlap':studio_overlap,'zoom_rect':zr,'auth_and_upgrade_modals_hide_widget':modal_checks,'page_errors':errs}
    reports.append(report);assert not tool_overlap and not studio_overlap and all(x['hidden_behind_modal'] for x in modal_checks) and not errs
    ctx.close()
   result={'rounds':reports};(OUT/'browser-id115-feedback-overlap.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
