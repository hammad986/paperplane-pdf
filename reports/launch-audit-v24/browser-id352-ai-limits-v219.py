from __future__ import annotations
import json, os, socket, sys, tempfile, threading, time
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz
import uvicorn

root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-ai-input-caps-') as td:
    os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'local-browser-admin-key','PAPERPLANE_ADMIN_CODE':'local-browser-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
    sys.path.insert(0,str(root))
    from server import app, AI_DOCUMENT_PAGE_LIMIT, AI_CHAT_QUESTION_MAX_CHARS
    import ai_engine
    import persistence
    import server
    ai_engine.AI_KILL_SWITCH=False
    ai_engine.BLUESMINDS_API_KEY='controlled-local-browser-key'
    ai_engine.call_llm=lambda *args, **kwargs: 'Controlled local browser answer.'
    server.translation_ai_available=lambda: True
    ai_engine.translate_pdf_layout=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError('over-limit input reached provider'))
    persistence.init_db()
    with fitz.open() as doc:
        for n in range(AI_DOCUMENT_PAGE_LIMIT+1):
            page=doc.new_page(); page.insert_text((60,70),f'Local AI cap verification page {n+1}.')
        oversized_pdf=doc.tobytes()
    with socket.socket() as s: s.bind(('127.0.0.1',0)); port=s.getsockname()[1]
    uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False))
    thread=threading.Thread(target=uv.run,daemon=True); thread.start()
    result={'build':'local current worktree','page_limit':AI_DOCUMENT_PAGE_LIMIT,'chat_question_max_chars':AI_CHAT_QUESTION_MAX_CHARS,'responses':[],'browser_errors':[],'console_errors':[]}
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.1)
        else: raise RuntimeError('Local Uvicorn app did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            context=browser.new_context(viewport={'width':1365,'height':900})
            page=context.new_page()
            page.on('pageerror',lambda e:result['browser_errors'].append(str(e)))
            page.on('console',lambda m:result['console_errors'].append(m.text) if m.type=='error' else None)
            page.goto(f'http://127.0.0.1:{port}/',wait_until='domcontentloaded')
            page.wait_for_function("()=>!document.body.classList.contains('auth-pending')")
            bootstrap=page.locator('#paperplane-bootstrap').evaluate('(el)=>JSON.parse(el.textContent)')
            result['rendered_quota_copy']=page.locator('#settings-quota-description').inner_text()
            result['plan_limits']=bootstrap['planLimits']
            page.evaluate("switchWorkspaceView('pricing', 'billing', false)")
            page.wait_for_selector('#pricing-limits-table')
            result['pricing_ai_limits']=page.locator('#pricing-limits-table').inner_text()
            page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id352-ai-limits-v219.png'),full_page=True)
            def post(path, data=None, attach=False):
                kw={}
                if attach:
                    kw['multipart']={'file':{'name':'over-120-pages.pdf','mimeType':'application/pdf','buffer':oversized_pdf}}
                    if data: kw['multipart'].update(data)
                elif data is not None:
                    kw['form']=data
                response=page.request.post(f'http://127.0.0.1:{port}{path}',**kw)
                try: body=response.json()
                except Exception: body={'text':response.text()[:300]}
                result['responses'].append({'endpoint':path,'status':response.status,'detail':body.get('detail')})
            post('/api/ai/chat',{'question':'x'*AI_CHAT_QUESTION_MAX_CHARS})
            post('/api/ai/chat',{'question':'x'*(AI_CHAT_QUESTION_MAX_CHARS+1)})
            post('/api/ai/chat',{'question':'Summarize the document'},True)
            post('/api/ai/summarize',attach=True)
            post('/api/ai/extract',attach=True)
            post('/api/ai/translate',{'target_language':'es'},True)
            result['assets']=page.evaluate("performance.getEntriesByType('resource').filter(e=>e.name.includes('/assets/app.js')).map(e=>e.name)")
            browser.close()
        result['passed']=(result['plan_limits']['free_operations_per_day']==10 and result['plan_limits']['ai_document_page_limit']==AI_DOCUMENT_PAGE_LIMIT and result['plan_limits']['ai_chat_question_max_chars']==AI_CHAT_QUESTION_MAX_CHARS and [x['status'] for x in result['responses']]==[200,422,422,422,422,422] and f'{AI_DOCUMENT_PAGE_LIMIT} pages' in result['rendered_quota_copy'] and f'{AI_CHAT_QUESTION_MAX_CHARS} characters' in result['rendered_quota_copy'] and f'{AI_DOCUMENT_PAGE_LIMIT} pages/PDF' in result['pricing_ai_limits'] and f'{AI_CHAT_QUESTION_MAX_CHARS} characters' in result['pricing_ai_limits'] and not result['browser_errors'] and not result['console_errors'])
    finally:
        uv.should_exit=True; thread.join(timeout=5)
    out=root/'reports/launch-audit-v24/browser-id352-ai-limits-v219.json'
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
