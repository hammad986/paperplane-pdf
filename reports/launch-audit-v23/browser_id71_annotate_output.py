from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
import os
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id71-') as temp:
    root=Path(temp);source=root/'annotate-source.pdf'
    with fitz.open() as doc:
        page=doc.new_page(width=612,height=792);page.insert_text((72,100),'ID71 exact marker for annotation',fontsize=18)
        doc.save(source)
    external_base = os.environ.get('PAPERPLANE_AUDIT_BASE')
    app,base,_ = (None, external_base.rstrip('/'), None) if external_base else helper.start_server(root/'data')
    try:
        if not external_base:
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
                response=page.goto(base+'/annotate-pdf',wait_until='domcontentloaded');assert response.status==200
                page.locator('#file-input').set_input_files(str(source))
                page.locator('#annot_type').select_option('note')
                page.locator('#page').fill('1');page.locator('#content').fill('ID71 review annotation persisted')
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=45000)
                with page.expect_download(timeout=20000) as event:page.locator('#result-download-link').click()
                output=root/f'id71-round{number}.pdf';event.value.save_as(output)
                with fitz.open(output) as result:
                    annotations=list(result[0].annots() or [])
                    annotation_content=annotations[0].info.get('content') if annotations else None
                    text=result[0].get_text()
                    page_count=result.page_count
                assert page_count==1 and annotation_content=='ID71 review annotation persisted' and 'ID71 exact marker for annotation' in text,(page_count,annotation_content,text)
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id71-annotate-round{number}.png'))
                rounds.append({'round':number,'pages':page_count,'annotation_count':len(annotations),'annotation_content':annotation_content,'source_text_retained':'ID71 exact marker for annotation' in text,'page_errors':errors})
                context.close()
            browser.close()
        data={'base':base,'runtime':'external-production-mode-image' if external_base else 'isolated-local-server','rounds':rounds}
        evidence=OUT/'browser-id71-annotate-output.json'
        if external_base:
            image_tag = os.environ.get('PAPERPLANE_EVIDENCE_TAG', 'v132')
            evidence=OUT/f'browser-id71-annotate-output-docker-{image_tag}.json'
        evidence.write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        if app is not None:
            app.terminate();app.wait(timeout=5)
