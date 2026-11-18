from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT=Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id52-clear-') as temp:
    root=Path(temp)
    pdf=root/'ai-clear-state.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'AI clear-state fixture unique marker: NEBULA-5812.')
        doc.save(pdf)
    app,base,_identity=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            rounds=[]
            for number in (1,2):
                context=browser.new_context(viewport={'width':1104,'height':850})
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                page.goto(base+'/ai-intelligence',wait_until='domcontentloaded')
                page.locator('#ai-file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden === false && document.querySelector('#ai-doc-name')?.textContent.includes('ai-clear-state.pdf')",timeout=20000)
                loaded_text=page.locator('#view-ai-studio').inner_text()
                page.locator('#ai-clear-doc-btn').click()
                page.wait_for_function("document.querySelector('#ai-active-doc-bar')?.hidden === true && document.querySelector('#ai-empty-state')?.hidden === false",timeout=10000)
                empty_text=page.locator('#view-ai-studio').inner_text()
                stale_doc_bar=not page.locator('#ai-active-doc-bar').is_hidden()
                empty_visible=page.locator('#ai-empty-state').is_visible()
                page.screenshot(path=str(OUT/f'id52-ai-clear-round{number}.png'))
                item={'round':number,'document_visible_before_clear':'ai-clear-state.pdf' in loaded_text,'active_doc_bar_hidden_after_clear':not stale_doc_bar,'empty_state_visible_after_clear':empty_visible,'page_citation_prompt_visible':'page citations' in empty_text.lower(),'stale_fixture_marker_after_clear':'NEBULA-5812' in empty_text,'page_errors':errors}
                rounds.append(item)
                assert item['document_visible_before_clear'] and item['active_doc_bar_hidden_after_clear'] and item['empty_state_visible_after_clear']
                assert item['page_citation_prompt_visible'] and not item['stale_fixture_marker_after_clear'] and not errors
                context.close()
            result={'rounds':rounds}
            (OUT/'browser-id52-ai-clear-document.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            browser.close()
    finally:
        app.terminate();app.wait(timeout=5)
