from pathlib import Path
from tempfile import TemporaryDirectory
import base64,fitz,json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id228-') as temp:
    root=Path(temp);pdf=root/'Sample.pdf'
    with fitz.open() as doc:
        p=doc.new_page();p.insert_text((72,72),'ID228 one-page cloud import marker');doc.save(pdf)
    data_url='data:application/pdf;base64,'+base64.b64encode(pdf.read_bytes()).decode('ascii')
    app,base,_=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True);rounds=[]
            for n in (1,2):
                page=browser.new_page(viewport={'width':1366,'height':900});errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.route('**/api/cloud/sync',lambda route:route.fulfill(status=200,content_type='application/json',body=json.dumps({'data_url':data_url,'filename':'Sample.pdf'})))
                page.goto(base+'/merge-pdf',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
                page.locator('#topbar-cloud-btn').click();page.locator('#cloud-url').fill('https://drive.example.test/Sample.pdf');page.locator('#cloud-submit-btn').click()
                page.wait_for_function("document.querySelector('.toast-notice')?.innerText.includes('Imported Sample.pdf')",timeout=15000)
                toast=page.locator('.toast-notice').inner_text().strip()
                file_name=page.locator('.file-row-name').inner_text().strip()
                assert toast.endswith('· 1 page') and file_name=='Sample.pdf' and not errors,(toast,file_name,errors)
                page.screenshot(path=str(OUT/f'id228-cloud-import-round{n}.png'))
                rounds.append({'round':n,'toast':toast,'file_chip':file_name,'page_errors':errors});page.context.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id228-cloud-import-plural.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
