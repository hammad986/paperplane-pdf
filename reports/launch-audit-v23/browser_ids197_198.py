from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time, uuid
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-auth-197-198-') as tmp:
 app,base,identities=helper.start_server(Path(tmp)/'data')
 try:
  port=int(base.rsplit(':',1)[1])
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.15)
  results=[]
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for round_no in (1,2):
    context=browser.new_context(viewport={'width':1366,'height':900});email,token=identities['accounts'][round_no-1]
    context.add_cookies([{'name':'paperplane_token','value':token,'url':base}]);page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
    page.goto(base+'/',wait_until='domcontentloaded')
    page.wait_for_function("document.querySelector('#user-name')?.textContent.includes('audit-')",timeout=10000)
    page.locator('#topbar-user-profile-btn').click();page.locator('#settings-signout-btn').wait_for(state='visible')
    handler=page.locator('#settings-signout-btn').evaluate('(e)=>Boolean(e.onclick)');page.locator('#settings-signout-btn').click();page.wait_for_function("document.querySelector('#user-name')?.textContent==='Guest Explorer'",timeout=10000)
    page.locator('#sidebar-settings-gear-btn').click();page.locator('#settings-signin-btn').wait_for(state='visible');signed_out={'name':page.locator('#user-name').inner_text(),'signin_visible':page.locator('#settings-signin-btn').is_visible(),'email_stored':page.evaluate("sessionStorage.getItem('paperplane-last-auth-shell-email')"),'auth_cookie_present':any(c['name']=='paperplane_token' for c in context.cookies(base)),'local_token':page.evaluate("localStorage.getItem('paperplane_token')"),'me_status':page.evaluate("fetch('/api/auth/me',{cache:'no-store'}).then(r=>r.json())")}
    page.reload(wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#user-name')?.textContent==='Guest Explorer'",timeout=10000)
    page.locator('#sidebar-settings-gear-btn').click();page.locator('#settings-signin-btn').wait_for(state='visible');after={'name':page.locator('#user-name').inner_text(),'signin_visible':page.locator('#settings-signin-btn').is_visible(),'email_stored':page.evaluate("sessionStorage.getItem('paperplane-last-auth-shell-email')"),'auth_cookie_present':any(c['name']=='paperplane_token' for c in context.cookies(base)),'local_token':page.evaluate("localStorage.getItem('paperplane_token')"),'me_status':page.evaluate("fetch('/api/auth/me',{cache:'no-store'}).then(r=>r.json())")}
    assert signed_out['me_status'].get('authenticated') is False and after['me_status'].get('authenticated') is False,signed_out|{'after':after,'handler_attached':handler}
    assert signed_out['name']=='Guest Explorer' and after['name']=='Guest Explorer',signed_out|{'after':after}
    assert not signed_out['email_stored'] and not after['email_stored'],signed_out|{'after':after}
    assert after['signin_visible'],after
    assert not errors,errors
    results.append({'round':round_no,'seeded_authenticated_account':True,'after_signout':signed_out,'after_reload':after,'page_errors':errors});context.close()
   browser.close()
  (OUT/'browser-ids197-198.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
 finally:app.terminate();app.wait(timeout=5)





