from __future__ import annotations
import json, os, secrets, socket, subprocess, sys, time
from pathlib import Path
from tempfile import TemporaryDirectory
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent / 'browser-id193-quota-error-round1.json'

def main():
    with TemporaryDirectory(prefix='paperplane-v24-id193-') as tmp:
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = {k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}
        env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(tmp)/'data'),'PAPERPLANE_PORT':str(port),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(48),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(32),'PAPERPLANE_SESSION_SECRET':secrets.token_urlsafe(48),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT),'PYTHONIOENCODING':'utf-8'})
        app=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        evidence={'server':'isolated local app.py','live_or_production_contacted':False,'page_errors':[],'console_errors':[],'expected_console_events':[],'cases':[]}
        try:
            for _ in range(120):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError('local server did not start')
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport={'width':1280,'height':900})
                page.on('pageerror',lambda e:evidence['page_errors'].append(str(e)))
                def record_console(message):
                    if message.type != 'error': return
                    if 'status of 402 (Payment Required)' in message.text:
                        evidence['expected_console_events'].append(message.text)
                    else:
                        evidence['console_errors'].append(message.text)
                page.on('console',record_console)
                base=f'http://127.0.0.1:{port}'
                export_hits=[]
                def quota_export(route):
                    export_hits.append(route.request.url)
                    route.fulfill(status=402, content_type='application/json', body=json.dumps({'detail':{'code':'TIER_LIMIT_REACHED','message':{'message':'Studio export limit reached. Try again tomorrow.'}}}))
                page.route('**/api/studio/apply-edits', quota_export)
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.locator('#save-studio-btn').wait_for(state='visible',timeout=15000)
                page.evaluate("() => window.PaperplaneEditor.editorState.setSource(new File(['%PDF-1.4'], 'controlled-quota.pdf', {type:'application/pdf'}), 'controlled-quota.pdf', 1)")
                page.locator('#save-studio-btn').click()
                page.wait_for_function("document.querySelector('#upgrade-modal')?.hidden === false && document.querySelector('#upgrade-context-alert')?.textContent.includes('Studio export limit reached')",timeout=10000)
                export_ui={'export_api_intercepted':len(export_hits)==1,'modal_visible':not page.locator('#upgrade-modal').is_hidden(),'quota_message':page.locator('#upgrade-context-alert').inner_text()}
                assert export_ui['export_api_intercepted'] and 'Studio export limit reached' in export_ui['quota_message'],export_ui
                result=page.evaluate('''async () => {
                  const quota = {detail:{code:'TIER_LIMIT_REACHED',message:{message:'Daily cloud operation limit reached. Try again tomorrow.'}}};
                  const quotaResult = await window.readStudioResponseError(new Response(JSON.stringify(quota),{status:402,headers:{'content-type':'application/json'}}),'Export failed');
                  const modal = document.querySelector('#upgrade-modal');
                  const alert = document.querySelector('#upgrade-context-alert');
                  const quotaText = alert?.textContent?.trim();
                  const structured = {detail:{error:{message:'A structured export error.'}}};
                  const structuredResult = await window.readStudioResponseError(new Response(JSON.stringify(structured),{status:500,headers:{'content-type':'application/json'}}),'Export failed');
                  const objectOnly = await window.readStudioResponseError(new Response(JSON.stringify({detail:{code:'TIER_LIMIT_REACHED',message:{reason:'cap'}}}),{status:402,headers:{'content-type':'application/json'}}),'Export failed');
                  return {quotaResult,modalVisible:!!modal&&!modal.hidden,quotaText,structuredResult,objectOnly,loadedScripts:[...document.scripts].map(s=>s.src).filter(s=>s.includes('app.js')),objectLeak:[quotaResult,alert?.textContent,structuredResult,objectOnly].some(x=>String(x).includes('[object Object]'))};
                }''')
                assert result['quotaResult'] is None and result['modalVisible'],result
                assert 'Daily cloud operation limit reached' in result['quotaText'],result
                assert result['structuredResult']=='A structured export error.',result
                assert result['objectOnly'] is None and not result['objectLeak'],result
                evidence.update(result=result,actual_export=export_ui,app_asset=page.locator('script[src*="app.js"]').get_attribute('src'),passed=True)
                assert not evidence['page_errors'],evidence
                assert not evidence['console_errors'],evidence
                browser.close()
        finally:
            app.terminate()
            try: app.wait(timeout=5)
            except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
    OUT.write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))

if __name__=='__main__': main()



