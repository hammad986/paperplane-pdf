from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as h
with TemporaryDirectory(prefix='paperplane-id128-') as td:
 app,base,identity=h.start_server(Path(td)/'db')
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2):break
   except OSError:time.sleep(.15)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True);rounds=[];token=identity['accounts'][0][1]
   for n in (1,2):
    ctx=browser.new_context(viewport={'width':1366,'height':900});ctx.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}]);page=ctx.new_page();errors=[];api=[]
    page.on('pageerror',lambda e:errors.append(str(e)));page.on('response',lambda r:api.append({'url':r.url,'status':r.status}) if r.url.endswith('/api/feedback') else None)
    page.goto(base+'/tool-desk',wait_until='domcontentloaded');page.wait_for_function("window.state?.user?.user_id && document.querySelector('#pp-feedback-launcher') && !document.querySelector('#pp-feedback-launcher').hidden",timeout=15000)
    initial=page.locator('#pp-feedback-launcher').is_visible();
    if n==1:
     page.locator('#pp-feedback-dismiss').click();page.wait_for_function("document.querySelector('#pp-feedback-launcher').hidden")
     dismissed=page.evaluate("()=>Object.entries(localStorage).filter(([k,v])=>k.includes('feedback')&&v==='1').map(([k])=>k)")
     page.goto(base+'/settings',wait_until='domcontentloaded');page.locator('#sidebar-settings-gear-btn').click();page.locator('#settings-tab-btn-privacy').click();settings_button=page.locator('#settings-feedback-open');settings_button.wait_for(state='visible',timeout=10000);settings_entry=settings_button.is_visible();settings_button.click();page.wait_for_function("getComputedStyle(document.querySelector('#pp-feedback-popover')).display==='flex'")
     reopened=page.locator('#pp-feedback-popover').is_visible();page.screenshot(path=str(OUT/f'id128-feedback-settings-round{n}.png'))
     item={'round':n,'first_time_signed_in_launcher_visible':initial,'dismiss_hid_launcher':page.locator('#pp-feedback-launcher').evaluate('e=>e.hidden'),'feedback_local_flags':dismissed,'settings_reopen_button_visible':settings_entry,'settings_reopened_feedback':reopened,'page_errors':errors}
     assert initial and any('dismissed' in key for key in dismissed) and settings_entry and reopened and not errors
    else:
     page.locator('#pp-btn-feedback-toggle').click();page.locator('#pp-fb-star-group [data-rating="4"]').click();page.locator('.pp-fb-cat-pill[data-cat="suggestion"]').click();page.locator('#pp-fb-text-input').fill('Synthetic local audit suggestion; please add keyboard help.')
     page.locator('#pp-btn-feedback-submit').click();page.wait_for_function("getComputedStyle(document.querySelector('#pp-feedback-success-body')).display==='block'",timeout=10000)
     success=page.locator('#pp-feedback-success-body').is_visible();hidden=page.locator('#pp-feedback-launcher').evaluate('e=>e.hidden');
     page.goto(base+'/settings',wait_until='domcontentloaded');page.locator('#sidebar-settings-gear-btn').click();page.locator('#settings-tab-btn-privacy').click();settings_button=page.locator('#settings-feedback-open');settings_button.wait_for(state='visible',timeout=10000);settings_entry=settings_button.is_visible();settings_button.click();page.wait_for_function("getComputedStyle(document.querySelector('#pp-feedback-popover')).display==='flex'")
     item={'round':n,'first_time_signed_in_launcher_visible':initial,'submit_success_visible':success,'launcher_hidden_after_submit':hidden,'local_feedback_api':api,'settings_reopen_button_visible':settings_entry,'settings_reopened_feedback':page.locator('#pp-feedback-popover').is_visible(),'page_errors':errors}
     assert initial and success and hidden and any(x['status']==200 for x in api) and item['settings_reopened_feedback'] and not errors
    rounds.append(item);ctx.close()
   result={'rounds':rounds};(OUT/'browser-id128-feedback-lifecycle.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2));browser.close()
 finally:app.terminate();app.wait(timeout=5)
