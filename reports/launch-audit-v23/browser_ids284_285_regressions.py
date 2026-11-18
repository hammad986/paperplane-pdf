from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-284-285-') as temp:
    root=Path(temp);source=root/'stamp-source.pdf';html=root/'invalid.html'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Stamp regression source')
        doc.save(source)
    html.write_text('<html><body>Must use the public page URL</body></html>',encoding='utf-8')
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
                page=context.new_page();errors=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda req:requests.append(req.url))
                page.goto(base+'/watermark-pdf',wait_until='domcontentloaded');page.wait_for_function("state.operation==='watermark'")
                page.locator('#file-input').set_input_files(str(source));page.wait_for_function("state.files.length===1")
                page.locator('#text').fill('v20 stamp ✓ café — APPROVED')
                page.locator('#run-button').click()
                page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=90000)
                with page.expect_download() as info:page.locator('#result-download-link').click()
                download=info.value;output=root/f'{n}-stamp.pdf';download.save_as(output)
                with fitz.open(output) as pdf:
                    extracted='\n'.join(p.get_text() for p in pdf)
                    assert 'v20 stamp ✓ café — APPROVED' in extracted,extracted
                    font_maps=[pdf.xref_get_key(font[0],'ToUnicode')[0] for p in pdf for font in p.get_fonts(full=True)]
                    assert any(value!='null' for value in font_maps),font_maps
                page.goto(base+'/html-to-pdf',wait_until='domcontentloaded');page.wait_for_function("state.operation==='html_to_pdf'")
                before=sum('/api/jobs' in url for url in requests)
                page.locator('#file-input').set_input_files(str(html))
                page.wait_for_function("document.querySelectorAll('.toast-notice').length>0")
                notices=page.locator('.toast-notice').all_text_contents()
                assert any('does not accept uploaded .html files' in text for text in notices),notices
                page.wait_for_timeout(250)
                after=sum('/api/jobs' in url for url in requests)
                assert after==before and not errors,(before,after,errors)
                page.screenshot(path=str(OUT/f'id284-285-round{n}.png'))
                rounds.append({'round':n,'stamp_filename':download.suggested_filename,'stamp_text':extracted.strip(),
                    'to_unicode_values':font_maps,'html_rejection':notices,'job_requests_before_after':[before,after],'page_errors':errors})
                context.close()
            finally:app.terminate();app.wait(timeout=5)
        browser.close()
    result={'rounds':rounds};(OUT/'browser-ids284-285.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
