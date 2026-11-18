from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id88-') as temp:
    root=Path(temp)
    sources=[]
    for name,marker in [('first-source.pdf','FIRST MERGE MARKER shared text old'),('second-source.pdf','SECOND MERGE MARKER shared text new')]:
        path=root/name
        with fitz.open() as doc:
            doc.new_page().insert_text((72,72),marker)
            doc.save(path)
        sources.append(path)
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
                context=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/?tool=merge',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files([str(path) for path in sources])
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=45000)
                with page.expect_download(timeout=20000) as event:page.locator('#result-download-link').click()
                merged=root/f'id88-merged-round{number}.pdf';event.value.save_as(merged)
                merge_filename=event.value.suggested_filename
                with fitz.open(merged) as result:
                    merge_pages=result.page_count;merge_text=' '.join(pg.get_text() for pg in result)
                assert merge_filename=='merged-PDF.pdf',merge_filename
                assert merge_pages==2 and all(marker in merge_text for marker in ('FIRST MERGE MARKER','SECOND MERGE MARKER')),(merge_pages,merge_text)
                page.screenshot(path=str(OUT/f'id88-merge-round{number}.png'))
                page.goto(base+'/?tool=compare',wait_until='domcontentloaded')
                body=page.locator('body').inner_text()
                assert '.txt diff file' in body,body[-2000:]
                page.locator('#file-input').set_input_files([str(path) for path in sources])
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=45000)
                with page.expect_download(timeout=20000) as event:page.locator('#result-download-link').click()
                diff=root/f'id88-compare-round{number}.txt';event.value.save_as(diff)
                diff_text=diff.read_text(encoding='utf-8')
                assert event.value.suggested_filename.lower().endswith('.txt'),event.value.suggested_filename
                assert 'shared text' in diff_text and ('old' in diff_text or 'new' in diff_text),diff_text
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id88-compare-round{number}.png'))
                rounds.append({'round':number,'merge_filename':merge_filename,'merge_pages':merge_pages,'both_merge_markers_preserved':True,'compare_description_explicitly_says_txt_diff':'.txt diff file' in body,'compare_filename':event.value.suggested_filename,'compare_output_contains_differences':True,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds};(OUT/'browser-id88-merge-compare-output.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
