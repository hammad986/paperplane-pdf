from __future__ import annotations
import json, os, socket, tempfile, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz
import uvicorn

root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-ai-quota-browser-') as td:
    os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'local-browser-admin-key','PAPERPLANE_ADMIN_CODE':'local-browser-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
    import sys
    sys.path.insert(0,str(root))
    from server import app, FREE_AI_CALLS_PER_DAY
    import persistence
    persistence.init_db()
    with fitz.open() as doc:
        page=doc.new_page(); page.insert_text((60,70),'Local browser AI quota verification sample document.')
        pdf=doc.tobytes()
    with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False))
    thread=threading.Thread(target=uv.run,daemon=True); thread.start()
    result={'build':'local current worktree','ai_limit':FREE_AI_CALLS_PER_DAY,'requests':[],'browser_errors':[],'console_errors':[]}
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Local uvicorn did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            context=browser.new_context(viewport={'width':1365,'height':900})
            page=context.new_page()
            page.on('pageerror',lambda e:result['browser_errors'].append(str(e)))
            page.on('console',lambda m:result['console_errors'].append(m.text) if m.type=='error' else None)
            page.goto(f'http://127.0.0.1:{port}/',wait_until='domcontentloaded')
            page.wait_for_function("()=>!document.body.classList.contains('auth-pending')")
            rendered=page.locator('#settings-quota-description').inner_text()
            result['rendered_quota_copy']=rendered
            limits=page.locator('#paperplane-bootstrap').evaluate('(el)=>JSON.parse(el.textContent).planLimits')
            result['public_plan_limits']=limits
            for i in range(1,FREE_AI_CALLS_PER_DAY+2):
                response=page.request.post(f'http://127.0.0.1:{port}/api/ai/summarize',multipart={'file':{'name':'quota-sample.pdf','mimeType':'application/pdf','buffer':pdf}})
                try: body=response.json()
                except Exception: body={'non_json':response.text()[:200]}
                result['requests'].append({'attempt':i,'status':response.status,'detail':body.get('detail'),'operation_header':response.headers.get('x-paperplane-operations-today'),'ai_header':response.headers.get('x-paperplane-ai-calls-today')})
            result['page_title']=page.title()
            result['asset_statuses']=page.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.includes('/assets/app.js?v=213')||e.name.includes('/assets/service-worker.js')).map(e=>({url:e.name,transferSize:e.transferSize}))")
            browser.close()
        result['passed']=(all(x['status']==200 for x in result['requests'][:FREE_AI_CALLS_PER_DAY]) and result['requests'][-1]['status']==402 and result['requests'][-1]['detail']['quota']=='ai' and f'including at most {FREE_AI_CALLS_PER_DAY} successful AI requests' in result['rendered_quota_copy'] and not result['browser_errors'] and not result['console_errors'])
    finally:
        uv.should_exit=True; thread.join(timeout=5)
    out=root/'reports/launch-audit-v24/browser-ai-daily-cap-v218.json'
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
