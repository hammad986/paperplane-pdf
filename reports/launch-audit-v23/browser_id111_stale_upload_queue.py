from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from docx import Document
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id111-') as temp:
    root=Path(temp);pdfs=[]
    for n in (1,2):
        path=root/f'merge-{n}.pdf'
        with fitz.open() as doc:
            page=doc.new_page();page.insert_text((72,72),f'Merge source marker {n}');doc.save(path)
        pdfs.append(path)
    docx=root/'single-word.docx';word=Document();word.add_paragraph('Single Word input after Merge files');word.save(docx)
    app,base,_=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/merge',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files([str(x) for x in pdfs])
                page.wait_for_function('window.state?.files?.length === 2',timeout=10000)
                assert page.locator('#file-list').inner_text().count('merge-')>=2
                page.locator('a[href="/word-to-pdf"]').first.evaluate('(el)=>el.click()')
                page.wait_for_function("window.state?.operation === 'word_to_pdf'",timeout=10000)
                page.wait_for_function('window.state?.files?.length === 0',timeout=10000)
                page.locator('#file-input').set_input_files(str(docx))
                page.wait_for_function('window.state?.files?.length === 1',timeout=10000)
                assert page.locator('#file-list').inner_text().count('single-word.docx')==1
                with page.expect_response('**/api/jobs') as event:page.locator('#run-button').click()
                job_response=event.value;payload=job_response.json()
                detail=str(payload.get('detail') or payload)
                assert 'at most 1 files' not in detail,detail
                assert job_response.status in (200,202,503),{'status':job_response.status,'body':payload}
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id111-stale-upload-queue-round{number}.png'),full_page=True)
                rounds.append({'round':number,'merge_queue_before_switch':2,'word_queue_after_switch':0,'word_inputs_after_upload':1,'word_job_http_status':job_response.status,'stale_batch_limit_error':False,'detail':detail[:180],'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'note':'This verifies stale Merge files are not sent with the single-file Word operation. Local Word conversion provider availability is reported separately.'}
        (OUT/'browser-id111-stale-upload-queue.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
