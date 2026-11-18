from pathlib import Path
from tempfile import TemporaryDirectory
import io,json,socket,sys,time
from PIL import Image
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id229-') as temp:
    root=Path(temp);photo=root/'portrait.png'
    Image.new('RGB',(600,400),(225,140,90)).save(photo)
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
                page=browser.new_page(viewport={'width':1366,'height':900},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/resize-image-dimensions',wait_until='domcontentloaded');page.wait_for_function("!document.body.classList.contains('auth-pending')")
                page.locator('#preset').select_option('passport')
                before=page.evaluate("({width:document.querySelector('#width').value,height:document.querySelector('#height').value,scale:document.querySelector('#scale_percent').value})")
                page.locator('#file-input').set_input_files(str(photo))
                after=page.evaluate("({width:document.querySelector('#width').value,height:document.querySelector('#height').value,scale:document.querySelector('#scale_percent').value})")
                assert before=={'width':'350','height':'450','scale':''} and after==before,(before,after)
                page.locator('#run-button').click();page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=15000)
                with page.expect_download(timeout=10000) as evt:page.locator('#result-download-link').click()
                output=root/f'passport-round{n}.jpg';evt.value.save_as(output)
                with Image.open(output) as result:assert result.size==(350,450)
                page.screenshot(path=str(OUT/f'id229-passport-fields-round{n}.png'))
                rounds.append({'round':n,'fields_before_upload':before,'fields_after_upload':after,'download':evt.value.suggested_filename,'output_dimensions':list(Image.open(output).size),'page_errors':errors});assert not errors
                page.context.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id229-passport-fields.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
