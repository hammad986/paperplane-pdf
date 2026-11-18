from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id96-') as temp:
    root=Path(temp); source=root/'fillable-form.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Synthetic employment form ID96')
        widget=fitz.Widget();widget.field_name='employee_name';widget.field_label='Employee Name';widget.field_type=fitz.PDF_WIDGET_TYPE_TEXT;widget.rect=fitz.Rect(72,120,360,150);widget.field_value='';page.add_widget(widget)
        doc.save(source)
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
                page=context.new_page();errors=[];fill_requests=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.on('request',lambda request:fill_requests.append(request.post_data) if request.url.endswith('/api/studio/forms/fill') else None)
                response=page.goto(base+'/studio',wait_until='domcontentloaded');assert response.status==200
                page.locator('#studio-file-input').set_input_files(str(source))
                page.locator('#btn-more-tools-trigger').click()
                page.locator('#studio-forms-btn').wait_for(state='visible',timeout=10000)
                page.locator('#studio-forms-btn').click()
                page.locator('#forms-modal:not([hidden])').wait_for(state='visible',timeout=15000)
                page.locator('#form-input-0').wait_for(state='visible',timeout=15000)
                assert '1 field' in page.locator('#forms-field-count-badge').inner_text()
                page.locator('#form-input-0').fill('Ada Lovelace')
                assert page.locator('#form-input-0').input_value()=='Ada Lovelace'
                page.evaluate("window.__id96OriginalFile=window.PaperplaneSecurityForms.currentFile")
                with page.expect_response('**/api/studio/forms/fill') as response_info:
                    page.locator('#btn-apply-form-fill').click()
                fill_response=response_info.value;assert fill_response.status==200,fill_response.status
                page.wait_for_function("window.PaperplaneSecurityForms.currentFile !== window.__id96OriginalFile",timeout=15000)
                page.wait_for_function("document.querySelector('#form-input-0')?.value === 'Ada Lovelace'",timeout=15000)
                current_pdf=page.evaluate("""async()=>{const f=window.PaperplaneEditor.editorState.sourceFile;const bytes=new Uint8Array(await f.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return {name:f.name,base64:btoa(binary)}}""")
                import base64
                raw_fill=root/f'id96-filled-response-round{number}.pdf';raw_fill.write_bytes(base64.b64decode(current_pdf['base64']))
                with fitz.open(raw_fill) as filled:
                    api_values=[(w.field_name,w.field_value) for pg in filled for w in (pg.widgets() or [])]
                assert ('employee_name','Ada Lovelace') in api_values,{'values':api_values,'post_data':fill_requests,'input':page.locator('#form-input-0').input_value()}
                page.wait_for_function("document.querySelector('#forms-field-count-badge')?.textContent.includes('1 field')",timeout=15000)
                # Export the filled document through Studio's Save & Export action.
                page.locator('#modal-close-forms').click()
                download_button=page.locator('#save-studio-btn')
                assert download_button.count()==1
                with page.expect_download(timeout=15000) as event:download_button.click()
                download=event.value;out=root/f'id96-round{number}.pdf';download.save_as(out)
                with fitz.open(out) as result:
                    values=[(w.field_name,w.field_value) for pg in result for w in (pg.widgets() or [])]
                    text=' '.join(pg.get_text() for pg in result)
                    assert ('employee_name','Ada Lovelace') in values,values
                    assert 'Synthetic employment form ID96' in text,text
                    assert len(result)==1
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id96-fillable-form-round{number}.png'),full_page=True)
                rounds.append({'round':number,'input_field_detected':True,'fill_api_status':fill_response.status,'download_filename':download.suggested_filename,'field_value_verified':values,'source_text_retained':True,'page_count':1,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds};(OUT/'browser-id96-fillable-form.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
