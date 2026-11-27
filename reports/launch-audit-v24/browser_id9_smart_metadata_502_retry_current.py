from __future__ import annotations
import json,os,secrets,socket,subprocess,sys,time
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'reports/launch-audit-v24/browser-id9-smart-metadata-502-retry-current.json'

def main():
 with TemporaryDirectory(prefix='paperplane-id9-502-retry-') as td:
  root=Path(td); data=root/'data'; data.mkdir(); runner=root/'controlled_server.py'
  with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
  app_code=r'''import io,json,os,urllib.error,uvicorn
from fastapi.responses import JSONResponse
import ai_engine,server
provider_calls={'count':0}; route_calls={'count':0}
ai_engine.AI_KILL_SWITCH=False
ai_engine._runtime_ai_config=lambda:{'provider':'bluesminds','api_key':'synthetic','base_url':'https://provider.example/v1','model':'synthetic-model'}
ai_engine._current_agentrouter_api_key=lambda:'synthetic'
ai_engine._record_ai_provider_status=lambda *a,**k:None
ai_engine.time.sleep=lambda _seconds:None
payload={'choices':[{'message':{'content':json.dumps({'general_data':{'title':'Machine Learning Notes','document_date':'3.3.1','detected_topics':['3.3.1 Section','Machine Learning'],'key_entities':[]},'warnings':[],'source_pages':[1],'contact':{'emails':[],'phones':[]}})}}]}
def controlled_provider(request,timeout):
 provider_calls['count']+=1
 if provider_calls['count']==1: raise urllib.error.HTTPError(request.full_url,502,'controlled transient',{},io.BytesIO(b'temporary'))
 return io.BytesIO(json.dumps(payload).encode())
ai_engine._open_ai_request=controlled_provider
@server.app.middleware('http')
async def controlled_route_retry(request,call_next):
 if request.url.path=='/api/ai/extract' and request.method=='POST':
  route_calls['count']+=1
  if route_calls['count']==1: return JSONResponse({'detail':'controlled transient gateway failure'},status_code=502)
  response=await call_next(request)
  response.headers['X-Test-Route-Attempts']=str(route_calls['count'])
  response.headers['X-Test-Provider-Attempts']=str(provider_calls['count'])
  return response
 return await call_next(request)
uvicorn.run(server.app,host='127.0.0.1',port=int(os.environ['PAPERPLANE_PORT']),log_level='error')'''
  runner.write_text(app_code,encoding='utf-8')
  env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}
  env.update(PAPERPLANE_SKIP_DOTENV='1',PAPERPLANE_ENV='development',PAPERPLANE_DATA_DIR=str(data),PAPERPLANE_ADMIN_KEY=secrets.token_urlsafe(64),PAPERPLANE_ADMIN_CODE=secrets.token_urlsafe(30),PAPERPLANE_PORT=str(port),PAPERPLANE_SECURE_COOKIES='false',PYTHONPATH=str(ROOT))
  app=subprocess.Popen([sys.executable,str(runner)],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  result={'route_attempts':[],'provider_attempts':[],'page_errors':[],'console_errors':[],'expected_http_error_console_entries':[]}
  try:
   base=f'http://127.0.0.1:{port}'
   for _ in range(120):
    try:
     with socket.create_connection(('127.0.0.1',port),timeout=.2): break
    except OSError:
     if app.poll() is not None: raise RuntimeError('controlled app server exited')
     time.sleep(.15)
   pdf=root/'metadata.pdf'
   with fitz.open() as doc:
    page=doc.new_page(); page.insert_text((72,72),'Machine Learning Notes'); page.insert_text((72,120),'3.3.1 Machine Learning'); doc.save(pdf)
   with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    page=browser.new_page(viewport={'width':390,'height':844}); page.set_default_timeout(15000)
    page.on('pageerror',lambda e:result['page_errors'].append(str(e)[:200]))
    page.on('console',lambda m:(result['expected_http_error_console_entries'] if 'responded with a status of 502 (Bad Gateway)' in m.text else result['console_errors']).append(m.text[:200]) if m.type=='error' else None)
    def capture_extract_response(r):
     if r.url.endswith('/api/ai/extract'):
      result['route_attempts'].append(r.status)
      if r.status==200: result['provider_attempts'].append({'route_attempts':r.headers.get('x-test-route-attempts'),'provider_attempts':r.headers.get('x-test-provider-attempts')})
    page.on('response',capture_extract_response)
    response=page.goto(base+'/smart-metadata',wait_until='domcontentloaded'); assert response and response.status==200
    page.wait_for_function("window.state?.operation==='ai_extract'")
    page.locator('#file-input').set_input_files(str(pdf))
    page.locator('#run-button').click()
    page.locator('#extraction-results-modal').wait_for(state='visible',timeout=30000)
    visible=page.locator('#extraction-results-modal').inner_text()
    page.wait_for_timeout(300)
    result['result_text']=visible[:1500]
    result['document_date_absent']='3.3.1' not in visible and 'date' in visible.casefold()
    result['topic_visible']='Machine Learning' in visible
    browser.close()
   result['route_attempts_counted']=len(result['route_attempts'])
   result['http_status_sequence']=result['route_attempts']
   provider_ok=result['provider_attempts']==[{'route_attempts':'2','provider_attempts':'2'}]
   result['result']='passed' if result['http_status_sequence']==[502,200] and provider_ok and result['document_date_absent'] and result['topic_visible'] and not result['page_errors'] and not result['console_errors'] and len(result['expected_http_error_console_entries'])==1 else 'failed'
   OUT.write_text(json.dumps(result,indent=2),encoding='utf-8'); print(json.dumps(result,indent=2))
   if result['result']!='passed': raise SystemExit(1)
  finally:
   app.terminate(); app.wait(timeout=10)
if __name__=='__main__':main()
