from pathlib import Path
from tempfile import TemporaryDirectory
import json, re, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id282-') as temp:
    root=Path(temp);a=root/'tiny-a.pdf';b=root/'tiny-b.pdf'
    for path,text in ((a,'Counter fixture A'),(b,'Counter fixture B')):
        with fitz.open() as doc:
            page=doc.new_page();page.insert_text((72,72),text);doc.save(path)
    rounds=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for n in (1,2):
            app,base,identity=helper.start_server(root/f'data-{n}')
            try:
                port=int(base.rsplit(':',1)[1])
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                    except OSError:time.sleep(.15)
                email,token=identity['accounts'][0]
                context=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
                context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded')
                page.wait_for_function("state.operation==='merge'")
                if page.locator('#client-privacy-toggle').is_checked():page.locator('label:has(#client-privacy-toggle)').click()
                page.wait_for_function("state.clientSideMode===false")
                page.locator('#file-input').set_input_files([str(a),str(b)])
                page.wait_for_function("document.querySelectorAll('#file-list .file-row-card').length===2")
                uploads=page.locator('#file-list .file-row-card').all_text_contents()
                assert all(name in ' '.join(uploads) for name in ('tiny-a.pdf','tiny-b.pdf')),uploads
                page.locator('#run-button').click()
                page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=90000)
                with page.expect_download() as info:page.locator('#result-download-link').click()
                merge_download=info.value
                merged_name=merge_download.suggested_filename
                merged=root/f'{n}-merged.pdf';merge_download.save_as(merged)
                with fitz.open(merged) as doc:
                    assert doc.page_count==2 and 'Counter fixture A' in doc[0].get_text() and 'Counter fixture B' in doc[1].get_text()
                assert not re.match(r'^\d+[-_]',merged_name),merged_name

                page.goto(base+'/compare-pdf',wait_until='domcontentloaded')
                page.wait_for_function("state.operation==='compare'")
                page.locator('#file-input').set_input_files([str(a),str(b)])
                page.wait_for_function("document.querySelectorAll('#file-list .file-row-card').length===2")
                compare_uploads=page.locator('#file-list .file-row-card').all_text_contents()
                assert all(name in ' '.join(compare_uploads) for name in ('tiny-a.pdf','tiny-b.pdf')),compare_uploads
                page.locator('#run-button').click()
                page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=90000)
                with page.expect_download() as info:page.locator('#result-download-link').click()
                diff_download=info.value;diff_name=diff_download.suggested_filename
                diff_path=root/f'{n}-diff.txt';diff_download.save_as(diff_path);diff=diff_path.read_text(encoding='utf-8')
                assert '--- tiny-a.pdf' in diff and '+++ tiny-b.pdf' in diff and 'Counter fixture' in diff,diff
                assert not re.match(r'^\d+[-_]',diff_name),diff_name

                # Studio restore notice must use the original source name too.
                studio=context.new_page();studio.on('pageerror',lambda e:errors.append(str(e)))
                studio.goto(base+'/studio',wait_until='domcontentloaded')
                studio.locator('#studio-file-input').set_input_files(str(a))
                studio.wait_for_function("document.querySelector('#studio-page-count')?.textContent.trim()==='1'")
                studio.reload(wait_until='domcontentloaded');studio.wait_for_function("state.studio.srcFile?.name==='tiny-a.pdf' && document.querySelector('#studio-page-count')?.textContent.trim()==='1'",timeout=15000)
                studio.wait_for_function("[...document.querySelectorAll('.toast-notice')].some(e=>e.textContent.includes('Restored tiny-a.pdf'))",timeout=10000)
                toasts=studio.locator('.toast-notice').all_text_contents()
                assert any('Restored tiny-a.pdf' in text for text in toasts),toasts
                assert not any(re.search(r'Restored \d+[-_]',text) for text in toasts),toasts
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id282-round{n}.png'))
                rounds.append({'round':n,'upload_names':uploads,'merge_filename':merged_name,'merge_pages':2,
                    'compare_upload_names':compare_uploads,'compare_filename':diff_name,'compare_text':diff,
                    'studio_restore_toasts':toasts,'page_errors':errors})
                context.close()
            finally:
                app.terminate();app.wait(timeout=5)
        browser.close()
    result={'rounds':rounds}
    (OUT/'browser-id282-filename-counter.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
