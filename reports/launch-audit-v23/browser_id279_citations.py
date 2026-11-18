from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id279-') as temp:
    app,base,identity=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
                chat=page.evaluate("""() => { showAiChatDeskResult({answer:'Test answer with repeated citations.', citations:[3,3,3,2,3]});
                    return {pages:[...document.querySelectorAll('#result-content .ai-result-citations .ai-citation-tag:not(.muted)')].map(e=>e.textContent.trim()),
                    labels:[...document.querySelectorAll('#result-content .ai-result-citations .ai-citation-tag:not(.muted)')].map(e=>e.getAttribute('data-ai-page')),
                    mode:document.querySelector('#result-meta').textContent}; }""")
                assert chat['pages']==['Page 3','Page 2'] and chat['labels']==['3','2'],chat
                summary=page.evaluate("""() => {document.querySelector('#result-content').innerHTML=summaryCitationHtml([3,3,3,2,3]);
                    return [...document.querySelectorAll('#result-content .ai-citation-tag:not(.muted)')].map(e=>e.textContent.trim());}""")
                assert summary==['Page 2','Page 3'],summary
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id279-citations-round{n}.png'))
                rounds.append({'round':n,'chat':chat,'summary_pages':summary,'page_errors':errors})
                page.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-id279-citations.json').write_text(json.dumps(result,indent=2))
        print(json.dumps(result,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
