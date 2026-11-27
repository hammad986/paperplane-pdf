from pathlib import Path
import json, os, secrets, socket, subprocess, sys, time, base64, hashlib
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright
ROOT=Path('.').resolve()
OWNER_URL='https://drive.google.com/file/d/1dAovOT7FCFaur33cX5_M6SsL6EvZT9rS/view'
with TemporaryDirectory(prefix='paperplane-id4-owner-v215-') as temp_name:
    temp=Path(temp_name); data=temp/'data'; data.mkdir()
    with socket.socket() as sock: sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    env={k:v for k,v in os.environ.items() if not k.upper().startswith(('PAPERPLANE_','CASHFREE_','SMTP_','RESEND_','OPENAI_','OPENROUTER_','BLUESMINDS_','ANTHROPIC_','GEMINI_','DEEPSEEK_','GOOGLE_API_','AI_','ADMIN_')) and k not in {'TESTING','SESSION_SECRET_KEY'}}
    env.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(data),'PAPERPLANE_PORT':str(port),'PAPERPLANE_ADMIN_KEY':secrets.token_urlsafe(48),'PAPERPLANE_ADMIN_CODE':secrets.token_urlsafe(32),'PAPERPLANE_SESSION_SECRET':secrets.token_urlsafe(48),'PAPERPLANE_SECURE_COOKIES':'false','PYTHONPATH':str(ROOT)})
    app=subprocess.Popen([sys.executable,'app.py'],cwd=ROOT,env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    evidence={'candidate':'local v215 source','browser':'Google Chrome via Playwright','source':'owner_drive_link','page_errors':[],'console_errors':[]}
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError('local server did not start')
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900})
            page.on('pageerror',lambda err:evidence['page_errors'].append(str(err).splitlines()[0][:180]))
            page.on('console',lambda msg:evidence['console_errors'].append(msg.text[:180]) if msg.type=='error' else None)
            page.goto(f'http://127.0.0.1:{port}/merge-pdf',wait_until='domcontentloaded')
            page.locator('#topbar-cloud-btn').click()
            page.locator('#cloud-url').fill(OWNER_URL)
            with page.expect_response(lambda res:'/api/cloud/sync' in res.url,timeout=90000) as response_info:
                page.locator('#cloud-submit-btn').click()
            response=response_info.value
            evidence['http_status']=response.status
            if response.status==200:
                payload=response.json(); raw=base64.b64decode(payload['data_url'].split(',',1)[1])
                pdf=fitz.open(stream=raw,filetype='pdf')
                evidence.update({'valid_pdf_signature':raw.startswith(b'%PDF-'),'pages':pdf.page_count,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'extractable_text_chars':sum(len(p.get_text()) for p in pdf),'filename_redacted':True})
                pdf.close()
                page.wait_for_function("document.querySelector('#cloud-modal')?.hidden === true || document.querySelector('#cloud-error')?.hidden === false")
                evidence['ui_imported']=page.locator('#cloud-modal').evaluate('(e)=>e.hidden')
                files=page.evaluate('''() => (window.state?.files||[]).map(f=>({size:f.size,type:f.type}))''')
                evidence['ui_file_attached']=bool(files and files[0]['size']==len(raw) and files[0]['type']=='application/pdf')
                evidence['result']='passed' if evidence['valid_pdf_signature'] and evidence['pages']>0 and evidence['ui_imported'] and evidence['ui_file_attached'] else 'failed'
            else:
                detail=page.locator('#cloud-error').inner_text().strip() if page.locator('#cloud-error').is_visible() else ''
                evidence['error_detail']=detail[:250]
                evidence['result']='owner_link_rejected'
            browser.close()
    finally:
        app.terminate()
        try: app.wait(timeout=5)
        except subprocess.TimeoutExpired: app.kill(); app.wait(timeout=5)
Path('reports/launch-audit-v24/browser-id4-owner-drive-v215.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps(evidence,indent=2))
