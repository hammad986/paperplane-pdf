from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

fixture={'status':'success','data':{'document_type':'general','total_pages':1,'invoice_data':None,'resume_data':None,'general_data':{'title':'Introduction to Machine Learning Class Notes','document_date':None,'detected_topics':['Machine Learning','Model Evaluation'],'key_entities':[]},'contact':{'emails':[],'phones':[]},'source_pages':[1],'warnings':['The proposed document date could not be verified in the source text.'],'csv_export':'title,document_date\nIntroduction to Machine Learning Class Notes,\n'}}

with TemporaryDirectory(prefix='paperplane-id105-') as temp:
    root=Path(temp);source=root/'notes-with-section.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Introduction to Machine Learning Class Notes\n3.3.1\nMachine Learning\nModel Evaluation')
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
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/ai/extract',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps(fixture)))
                response=page.goto(base+'/ai-intelligence',wait_until='domcontentloaded');assert response.status==200
                page.locator('#ai-file-input').set_input_files(str(source))
                page.wait_for_function("window.state?.files?.some(file=>file.name==='notes-with-section.pdf')",timeout=10000)
                page.locator('#ai-extract-type-select').select_option('general')
                page.locator('#trigger-extract-btn').click()
                page.locator('#extraction-results-modal:not([hidden])').wait_for(state='visible',timeout=15000)
                text=page.locator('#extraction-fields-grid').inner_text()
                assert 'Introduction to Machine Learning Class Notes' in text
                assert '3.3.1' not in text and 'Document Date' not in text
                warnings=page.locator('#extraction-warnings-list').inner_text()
                assert 'could not be verified' in warnings
                page.locator('#ext-tab-json').click()
                raw_json=page.locator('#extraction-json-code').inner_text()
                json_data=json.loads(raw_json)
                assert json_data['general_data']['document_date'] is None
                assert json_data['general_data']['detected_topics']==['Machine Learning','Model Evaluation']
                with page.expect_download() as event:page.locator('#extraction-export-json-btn').click()
                file=event.value;dest=root/f'id105-round{number}.json';file.save_as(dest)
                exported=json.loads(dest.read_text(encoding='utf-8'))
                assert exported['general_data']['document_date'] is None
                assert exported['general_data']['detected_topics']==['Machine Learning','Model Evaluation']
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id105-metadata-quality-round{number}.png'),full_page=True)
                rounds.append({'round':number,'invalid_section_date_absent':True,'header_fragments_absent':True,'verified_topics':exported['general_data']['detected_topics'],'page_errors':errors,'provider':'controlled already-sanitized extraction response'})
                context.close()
            browser.close()
        data={'rounds':rounds};(OUT/'browser-id105-metadata-quality.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
