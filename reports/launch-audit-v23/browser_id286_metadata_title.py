from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id286-') as temp:
    source=Path(temp)/'atlas-report.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_text((90,100),'Project Atlas Evaluation',fontsize=22)
        page.insert_text((90,155),'A report on the evaluation of sample systems.',fontsize=11)
        pdf.save(source)
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        email,token=identity['accounts'][0]
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
                page.wait_for_function("!document.body.classList.contains('auth-pending')")
                response=page.evaluate("""async b64=>{
                  const raw=atob(b64),bytes=Uint8Array.from(raw,c=>c.charCodeAt(0));
                  const form=new FormData();form.append('file',new File([bytes],'atlas-report.pdf',{type:'application/pdf'}));
                  form.append('question','What is the title of this document?');
                  const r=await fetch('/api/ai/chat/stream',{method:'POST',body:form,credentials:'same-origin'});
                  return {status:r.status,body:await r.text()};
                }""",__import__('base64').b64encode(source.read_bytes()).decode())
                events=[]
                for frame in response['body'].split('\n\n'):
                    name=next((line[7:].strip() for line in frame.splitlines() if line.startswith('event: ')),None)
                    data=next((line[6:] for line in frame.splitlines() if line.startswith('data: ')),None)
                    if data:events.append({'event':name,**json.loads(data)})
                answer=next((event.get('text','') for event in events if event.get('event')=='replace'),None)
                assert response['status']==200 and answer and 'Project Atlas Evaluation' in answer, (response,events)
                assert 'atlas-report.pdf' in answer and 'chat_stream.pdf' not in answer,(answer,events)
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id286-title-round{n}.png'))
                rounds.append({'round':n,'status':response['status'],'answer':answer,'events':events,'page_errors':errors})
                context.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-id286-metadata-title.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
