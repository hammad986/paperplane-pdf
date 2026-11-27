from __future__ import annotations
import json,os,socket,sys,tempfile,threading,time
from pathlib import Path
from playwright.sync_api import sync_playwright
import fitz,uvicorn
root=Path(__file__).resolve().parents[2]
with tempfile.TemporaryDirectory(prefix='paperplane-id86-ai-polish-') as td:
 os.environ.update({'PAPERPLANE_SKIP_DOTENV':'1','PAPERPLANE_ENV':'development','PAPERPLANE_DATA_DIR':str(Path(td)/'data'),'PAPERPLANE_ADMIN_KEY':'id86-local-admin-key','PAPERPLANE_ADMIN_CODE':'id86-local-admin-code','PAPERPLANE_SECURE_COOKIES':'false'})
 sys.path.insert(0,str(root))
 from server import app
 import persistence
 persistence.init_db()
 with fitz.open() as doc:
  p=doc.new_page();p.insert_text((60,70),'Document title marker for AI Docs preview.');fixture=Path(td)/'original-name.pdf';fixture.write_bytes(doc.tobytes())
 with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
 uv=uvicorn.Server(uvicorn.Config(app,host='127.0.0.1',port=port,log_level='warning',access_log=False));thread=threading.Thread(target=uv.run,daemon=True);thread.start()
 out={'viewports':[],'page_errors':[],'console_errors':[]}
 try:
  for _ in range(100):
   try:
    with socket.create_connection(('127.0.0.1',port),timeout=.2):break
   except OSError:time.sleep(.1)
  with sync_playwright() as p:
   browser=p.chromium.launch(channel='chrome',headless=True)
   for width in (390,1365):
    page=browser.new_page(viewport={'width':width,'height':844 if width<600 else 900})
    page.on('pageerror',lambda e:out['page_errors'].append(str(e)))
    page.on('console',lambda m:out['console_errors'].append(m.text) if m.type=='error' else None)
    def mock(route):
     body='event: stage\ndata: {"stage":"Thinking…"}\n\nevent: replace\ndata: {"text":"The key date is October 25, 2026. [Page 2]"}\n\nevent: done\ndata: {"citations":[2],"mode":"local_extraction"}\n\n'
     route.fulfill(status=200,headers={'content-type':'text/event-stream','cache-control':'no-cache'},body=body)
    page.route('**/api/ai/chat/stream',mock)
    page.goto(f'http://127.0.0.1:{port}/ai-intelligence',wait_until='domcontentloaded')
    page.locator('#ai-file-input').set_input_files(str(fixture));page.wait_for_function("!document.querySelector('#ai-active-doc-bar').hidden")
    page.locator('#chat-input').fill('What is the key date in this document?');page.locator('#chat-send-btn').click();page.wait_for_function("document.querySelector('.ai-stream-bubble')?.classList.contains('ai-stream-complete') || document.querySelector('.ai-stream-bubble .chat-citation-tags')?.textContent.includes('Page')",timeout=12000);page.wait_for_timeout(150)
    bubble=page.locator('.ai-stream-bubble').last
    details=page.evaluate("""()=>{const b=[...document.querySelectorAll('.ai-stream-bubble')].at(-1),t=b?.querySelector('.chat-markdown'),tags=b?.querySelector('.chat-citation-tags'),steps=b?.querySelector('.ai-stage-timeline'),input=document.querySelector('#chat-messages'),doc=document.querySelector('#ai-doc-name');return{filename:doc?.textContent,bodyText:t?.innerText,bodyHtml:t?.innerHTML,citationText:tags?.innerText,citationHtml:tags?.innerHTML,stageCount:steps?.children.length,stageClientWidth:steps?.clientWidth,stageScrollWidth:steps?.scrollWidth,chatClientWidth:input?.clientWidth,chatScrollWidth:input?.scrollWidth,emptyStateHidden:document.querySelector('#ai-empty-state')?.hidden,documentGreetCount:[...document.querySelectorAll('.chat-bubble.ai')].filter(x=>x.innerText.includes('Your PDF is ready')).length,docCardVisible:!document.querySelector('#ai-active-doc-bar').hidden}}""")
    details['viewport']=width;out['viewports'].append(details)
    page.screenshot(path=str(root/f'reports/launch-audit-v24/browser-id86-ai-polish-{width}-v220.png'),full_page=True);page.close()
   browser.close()
  out['passed']=len(out['viewports'])==2 and all(x['filename']=='original-name.pdf' and 'October 25, 2026.' in x['bodyText'] and '[Page 2]' not in x['bodyText'] and 'Page 2' in x['citationText'] and x['stageCount']==5 and x['stageClientWidth']==x['stageScrollWidth'] and x['chatClientWidth']==x['chatScrollWidth'] and x['emptyStateHidden'] and x['docCardVisible'] and x['documentGreetCount']==1 for x in out['viewports']) and not out['page_errors'] and not out['console_errors']
 finally:uv.should_exit=True;thread.join(timeout=5)
 (root/'reports/launch-audit-v24/browser-id86-ai-polish-v220.json').write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
