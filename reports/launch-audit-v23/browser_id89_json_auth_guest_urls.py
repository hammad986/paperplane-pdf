from pathlib import Path
from tempfile import TemporaryDirectory
import base64, fitz, json, socket, sys, time, uuid
import os, secrets, subprocess
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
def start_test_server(data_dir):
    with socket.socket() as candidate:
        candidate.bind(('127.0.0.1',0));port=candidate.getsockname()[1]
    env={name:value for name,value in os.environ.items() if not name.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and name not in {'TESTING','SESSION_SECRET_KEY'}}
    env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(data_dir),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(64),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(30),'PAPERPLANE_PORT':str(port),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT),'TESTING':'True'})
    process=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    return process,f'http://127.0.0.1:{port}'

with TemporaryDirectory(prefix='paperplane-id89-') as temp:
    root=Path(temp)
    pdfs=[]
    for name,marker in [('guest-a.pdf','ID89 Guest first marker'),('guest-b.pdf','ID89 Guest second marker')]:
        path=root/name
        with fitz.open() as doc:
            doc.new_page().insert_text((72,72),marker)
            doc.save(path)
        pdfs.append(path)
    app,base=start_test_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        output=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/',wait_until='domcontentloaded')
                signup_email=f'id89-{uuid.uuid4().hex[:10]}@example.test'
                signup_password='Id89SignupPassword123!'
                auth=page.evaluate("""async ({email,password})=>{
                  const headers={'Content-Type':'application/json'};
                  const registration=await fetch('/api/auth/register',{method:'POST',headers,body:JSON.stringify({email,password})});
                  const signupChallenge=await registration.json();
                  if(!registration.ok)return {registration_status:registration.status,signupChallenge};
                  const signupVerify=await fetch('/api/auth/verify-signup-otp',{method:'POST',headers,body:JSON.stringify({email,otp:signupChallenge.dev_otp})});
                  const signupSession=await signupVerify.json();
                  const logout=await fetch('/api/auth/logout',{method:'POST'});
                  const login=await fetch('/api/auth/login',{method:'POST',headers,body:JSON.stringify({email,password,require_otp:true})});
                  const loginChallenge=await login.json();
                  const loginVerify=await fetch('/api/auth/verify-login-otp',{method:'POST',headers,body:JSON.stringify({email,otp:loginChallenge.dev_otp})});
                  const loginSession=await loginVerify.json();
                  return {registration_status:registration.status,signupChallenge,signup_verify_status:signupVerify.status,signupSession,logout_status:logout.status,login_status:login.status,loginChallenge,login_verify_status:loginVerify.status,loginSession,final_url:location.href};
                }""",{'email':signup_email,'password':signup_password})
                assert auth['registration_status']==200 and auth['signupChallenge']['status']=='otp_required',auth
                assert 'token' not in auth['signupChallenge'] and auth['signup_verify_status']==200,auth
                assert auth['logout_status']==200 and auth['login_status']==200 and auth['loginChallenge']['status']=='otp_required',auth
                assert 'token' not in auth['loginChallenge'] and auth['login_verify_status']==200 and auth['loginSession'].get('token'),auth
                assert '?' not in auth['final_url'],auth['final_url']
                context.close()

                guest_context=browser.new_context(viewport={'width':1366,'height':900})
                guest=guest_context.new_page();guest_errors=[];guest.on('pageerror',lambda e:guest_errors.append(str(e)))
                guest.goto(base+'/',wait_until='domcontentloaded')
                file_data=[{'name':p.name,'bytes':base64.b64encode(p.read_bytes()).decode()} for p in pdfs]
                result=guest.evaluate("""async files=>{
                  const form=new FormData();form.append('operation','merge');form.append('options','{}');
                  for(const item of files){const raw=atob(item.bytes),data=new Uint8Array(raw.length);for(let i=0;i<raw.length;i++)data[i]=raw.charCodeAt(i);form.append('files',new File([data],item.name,{type:'application/pdf'}));}
                  const createdResponse=await fetch('/api/jobs',{method:'POST',body:form});const created=await createdResponse.json();
                  if(!createdResponse.ok)return {stage:'create',status:createdResponse.status,body:created};
                  const statusUrl=new URL(created.status_url,location.href),downloadUrl=new URL(created.download_url,location.href);
                  let state;
                  for(let n=0;n<120;n++){await new Promise(resolve=>setTimeout(resolve,250));const response=await fetch(statusUrl);state=await response.json();if(state.status==='completed'||state.status==='failed')break;}
                  if(state.status!=='completed')return {stage:'status',state,statusUrl:statusUrl.href,downloadUrl:downloadUrl.href};
                  const downloaded=await fetch(downloadUrl);const blob=await downloaded.blob();const bytes=new Uint8Array(await blob.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
                  return {status:downloaded.status,outputName:state.output_name,statusPath:statusUrl.pathname,statusSearch:statusUrl.search,downloadPath:downloadUrl.pathname,downloadSearch:downloadUrl.search,responseStatus:createdResponse.status,body: btoa(binary)};
                }""",file_data)
                assert result.get('responseStatus')==200 or result.get('status')==200,result
                assert result.get('statusPath') and not result['statusSearch'] and not result['downloadSearch'],result
                assert 'guest_token' not in result['statusPath'] and 'guest_token' not in result['downloadPath'],result
                data=base64.b64decode(result.pop('body'))
                merged=root/f'id89-guest-merged-{number}.pdf';merged.write_bytes(data)
                with fitz.open(merged) as doc:text=' '.join(page.get_text() for page in doc)
                assert all(marker in text for marker in ('ID89 Guest first marker','ID89 Guest second marker')),text
                cookies=guest_context.cookies(base)
                guest_cookie=next((cookie for cookie in cookies if cookie['name'].startswith('guest_job_')),None)
                # Successful single-use downloads delete the capability cookie. Its secret never appeared in either URL.
                assert not guest_errors,guest_errors
                guest.screenshot(path=str(OUT/f'id89-guest-api-round{number}.png'))
                output.append({'round':number,'json_login_otp':True,'json_registration_otp_gate':True,'auth_url_has_query':False,'guest_status_url_has_query':False,'guest_download_url_has_query':False,'guest_download_content_checked':True,'guest_cookie_after_single_use_download':guest_cookie,'page_errors':guest_errors})
                guest_context.close()
            browser.close()
        data={'rounds':output};(OUT/'browser-id89-json-auth-guest-urls.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
