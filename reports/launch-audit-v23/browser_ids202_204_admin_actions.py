from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
runs=[]
for round_no in (1,2):
 with TemporaryDirectory(prefix=f'paperplane-admin-202-204-{round_no}-') as tmp:
  app,base,identities=helper.start_server(Path(tmp)/'data')
  try:
   port=int(base.rsplit(':',1)[1])
   for _ in range(100):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2):break
    except OSError:time.sleep(.15)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    context=browser.new_context(viewport={'width':1440,'height':900});admin_token=identities['admin'];accounts=identities['accounts']
    context.add_init_script("sessionStorage.setItem('pp_admin_session',"+json.dumps(admin_token)+")")
    page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/admin',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#count-users')?.textContent !== '0'",timeout=15000)
    user_email,user_token=accounts[1];row=page.locator('#users-tbody tr').filter(has_text=user_email);row.wait_for(state='visible')
    row.locator('select').select_option('exam_pass')
    with page.expect_response(lambda r:'/api/admin/users/set-plan' in r.url) as plan_event:
     page.once('dialog',lambda d:d.accept())
     row.locator('[data-admin-user-action="set-plan"]').click()
    plan_response=plan_event.value;assert plan_response.status==200,plan_response.status
    page.wait_for_function("document.querySelector('#users-tbody')?.innerText.includes('EXAM_PASS')",timeout=10000)
    row=page.locator('#users-tbody tr').filter(has_text=user_email)
    with page.expect_response(lambda r:'/api/admin/users/reset-usage' in r.url) as reset_event:
     page.once('dialog',lambda d:d.accept())
     row.locator('[data-admin-user-action="reset-usage"]').click()
    reset_response=reset_event.value;assert reset_response.status==200,reset_response.status
    page.locator('#tab-sessions-btn').click();page.wait_for_function("document.querySelector('#sessions-tbody')?.querySelectorAll('tr').length===1",timeout=10000)
    session_count=page.locator('#count-sessions').inner_text();assert session_count=='1',session_count
    assert not errors,errors
    runs.append({'round':round_no,'target_test_account':user_email,'set_plan_status':plan_response.status,'set_plan_visible':True,'reset_usage_status':reset_response.status,'admin_session_list_count':int(session_count),'page_errors':errors})
    context.close();browser.close()
  finally:app.terminate();app.wait(timeout=5)
(OUT/'browser-ids202-204-admin-actions.json').write_text(json.dumps(runs,indent=2),encoding='utf-8');print(json.dumps(runs,indent=2))
