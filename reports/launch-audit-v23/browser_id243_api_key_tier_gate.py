from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path.cwd();OUT=ROOT/'reports'/'launch-audit-v23';sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'));import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id243-') as tmp:
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
   for n in (1,2):
    checks=[]
    for account_index,expected in ((1,'free'),(0,'student_pro')):
     context=browser.new_context(viewport={'width':1366,'height':900});email,token=identities['accounts'][account_index];context.add_cookies([{'name':'paperplane_token','value':token,'url':base}]);admin_headers={'X-Admin-Session':identities['admin']};user_list=context.request.get(base+'/api/admin/users',headers=admin_headers).json()['users'];target=next(u for u in user_list if u['email']==email);reset=context.request.post(base+'/api/admin/users/set-plan',headers={**admin_headers,'Content-Type':'application/json'},data={'user_id':target['id'],'tier':expected});assert reset.status==200,reset.status;page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
     page.goto(base+'/settings',wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#settings-user-email')?.textContent.includes('audit-')",timeout=10000);page.locator('#settings-tab-btn-api').click()
     assert page.locator('#settings-create-key-form').is_hidden(),(expected,'form visible')
     assert page.locator('#settings-api-key-upgrade-hint').is_visible(),(expected,'hint hidden')
     blocked=page.evaluate("async()=>{const f=new FormData();f.append('name','disallowed synthetic key');const r=await fetch('/api/developer/keys',{method:'POST',body:f});return r.status}")
     assert blocked==403,(expected,blocked)
     if expected=='student_pro':
      activation=page.evaluate("async ({admin,email})=>{const h={'X-Admin-Session':admin};const list=await fetch('/api/admin/users',{headers:h}).then(r=>r.json());const user=list.users.find(u=>u.email===email);const r=await fetch('/api/admin/users/set-plan',{method:'POST',headers:{...h,'Content-Type':'application/json'},body:JSON.stringify({user_id:user.id,tier:'cyber_cafe'})});return {status:r.status,body:await r.json()}}",{'admin':identities['admin'],'email':email})
      assert activation['status']==200,activation
      page.reload(wait_until='domcontentloaded');page.wait_for_function("document.querySelector('#settings-user-email')?.textContent.includes('audit-')",timeout=10000);page.locator('#settings-tab-btn-api').click()
      assert page.locator('#settings-create-key-form').is_visible()
      assert page.locator('#settings-api-key-upgrade-hint').is_hidden()
      page.locator('#settings-key-name').fill('Synthetic audit key')
      with page.expect_response(lambda r:'/api/developer/keys' in r.url and r.request.method=='POST') as event:
       page.locator('#settings-create-key-form button[type=submit]').click()
      response=event.value;assert response.status==200,response.status
      page.locator('#settings-new-key-alert').wait_for(state='visible');assert 'API Key Generated' in page.locator('#settings-new-key-alert').inner_text();assert page.locator('#settings-new-key-alert [data-copy-value]').count()==2
      eligible=True
     else: eligible=False
     page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(100)
     mobile=page.evaluate('({viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth})')
     assert mobile['documentWidth']<=390 and mobile['bodyWidth']<=390,(expected,mobile)
     if eligible:
      rect=page.locator('#settings-create-key-form').bounding_box();assert rect and rect['x']>=0 and rect['x']+rect['width']<=390,(expected,rect)
     assert not errors,errors
     checks.append({'tier_checked':expected,'generate_form_hidden':True,'server_create_status':blocked,'eligible_tier_after_controlled_upgrade':eligible,'eligible_form_and_key_creation_verified':eligible,'mobile_layout':mobile})
     context.close()
    results.append({'round':n,'checks':checks})
   browser.close()
  (OUT/'browser-id243-api-key-tier-gate.json').write_text(json.dumps(results,indent=2),encoding='utf-8');print(json.dumps(results,indent=2))
 finally:app.terminate();app.wait(timeout=5)
