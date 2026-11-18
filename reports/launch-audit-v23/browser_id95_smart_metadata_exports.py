from pathlib import Path
from tempfile import TemporaryDirectory
import csv, fitz, io, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

fixture={
  'status':'success',
  'data':{
    'document_type':'invoice','total_pages':1,
    'invoice_data':{'invoice_number':'INV-95-2026','invoice_date':'2026-11-17','due_date':'2026-12-17','vendor':'Northwind Supplies','customer':'Paperplane QA','currency':'USD','subtotal':'100.00','tax_amount':'25.00','total_amount':'125.00','payment_terms':'Net 30','line_items':[{'description':'Audit sample','quantity':2,'unit_price':'50.00','amount':'100.00'}]},
    'resume_data':None,'general_data':None,'contact':{'emails':['billing@northwind.example'],'phones':[]},
    'source_pages':[1],'warnings':[],
    'csv_export':'invoice_number,vendor,total_amount,currency\nINV-95-2026,Northwind Supplies,125.00,USD\n'
  }
}

with TemporaryDirectory(prefix='paperplane-id95-') as temp:
    root=Path(temp);source=root/'invoice-95-fixture.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Invoice INV-95-2026 Northwind Supplies total USD 125.00')
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
                page=context.new_page();errors=[];requests=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/ai/extract',lambda route: (requests.append(route.request.post_data),route.fulfill(status=200,content_type='application/json',body=json.dumps(fixture))))
                response=page.goto(base+'/ai-intelligence',wait_until='domcontentloaded');assert response.status==200
                page.locator('#ai-file-input').set_input_files(str(source))
                page.wait_for_function("window.state?.files?.some(file=>file.name==='invoice-95-fixture.pdf')",timeout=10000)
                page.locator('#ai-extract-type-select').select_option('invoice')
                page.locator('#trigger-extract-btn').click()
                page.locator('#extraction-results-modal:not([hidden])').wait_for(state='visible',timeout=15000)
                json_button=page.locator('#extraction-export-json-btn');csv_button=page.locator('#extraction-export-csv-btn')
                assert json_button.is_visible() and csv_button.is_visible()
                assert page.locator('#extraction-fields-grid').inner_text().find('INV-95-2026')>=0
                with page.expect_download(timeout=10000) as event:json_button.click()
                json_download=event.value;json_file=root/f'id95-round{number}.json';json_download.save_as(json_file)
                exported=json.loads(json_file.read_text(encoding='utf-8'))
                assert json_download.suggested_filename=='invoice-95-fixture_extracted.json'
                assert exported['invoice_data']['invoice_number']=='INV-95-2026' and exported['source_pages']==[1]
                with page.expect_download(timeout=10000) as event:csv_button.click()
                csv_download=event.value;csv_file=root/f'id95-round{number}.csv';csv_download.save_as(csv_file)
                csv_text=csv_file.read_text(encoding='utf-8-sig')
                parsed=list(csv.DictReader(io.StringIO(csv_text)))
                assert csv_download.suggested_filename=='invoice-95-fixture_extracted.csv'
                assert parsed==[{'invoice_number':'INV-95-2026','vendor':'Northwind Supplies','total_amount':'125.00','currency':'USD'}],parsed
                assert len(requests)==1 and not errors,(requests,errors)
                page.screenshot(path=str(OUT/f'id95-smart-metadata-round{number}.png'),full_page=True)
                rounds.append({'round':number,'json_button_visible':True,'csv_button_visible':True,'json_filename':json_download.suggested_filename,'json_content_checked':True,'csv_filename':csv_download.suggested_filename,'csv_content_checked':True,'controlled_extraction_requests':len(requests),'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds,'provider_mode':'controlled browser response; export UI/downloads exercised'};(OUT/'browser-id95-smart-metadata-exports.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
