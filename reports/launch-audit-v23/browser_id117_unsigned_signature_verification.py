from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id117-') as temp:
    root=Path(temp);source=root/'unsigned-with-signature-like-text.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Unsigned source marker ID117');doc.save(source)
    source.write_bytes(source.read_bytes()+b'\n% Ordinary PDF comment /ByteRange [0 53816 62010 1705] /Contents <00>\n')
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
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(source))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent==='1' && document.querySelector('#studio-loading-overlay')?.hidden",timeout=20000)
                page.locator('#btn-more-tools-trigger').click();page.locator('#studio-sign-btn').click()
                page.locator('#digital-sign-modal:not([hidden])').wait_for(state='visible')
                with page.expect_response('**/api/studio/sign/verify') as event:page.locator('#sign-tab-verify').click()
                response=event.value;assert response.status==200
                report=response.json()
                assert report['is_signed'] is False and report['signature_count']==0 and report['signatures']==[] and report['overall_status']=='NO_SIGNATURES',report
                result=page.locator('#verify-report-container')
                result.get_by_text('No Digital Signatures Found',exact=True).wait_for(timeout=10000)
                assert 'CRYPT' not in result.inner_text().upper() or 'NO DIGITAL SIGNATURES FOUND' in result.inner_text().upper()
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id117-unsigned-signature-round{number}.png'),full_page=True)
                rounds.append({'round':number,'api_status':response.status,'is_signed':report['is_signed'],'signature_count':report['signature_count'],'overall_status':report['overall_status'],'false_tampering_claim':False,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'fixture_contains_ordinary_byte_range_and_contents_comment':True};(OUT/'browser-id117-unsigned-signature.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
