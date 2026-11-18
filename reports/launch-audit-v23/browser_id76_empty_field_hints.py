from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

operations={
  'remove':{'input':'#pages','hint':'Enter one or more pages to remove'},
  'watermark':{'input':'#text','hint':'Enter watermark text or choose an image'},
  'redact':{'input':'#terms','hint':'Enter a word or phrase to redact'},
}
with TemporaryDirectory(prefix='paperplane-id76-') as temp:
    root=Path(temp);source=root/'empty-fields.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((72,72),'ID76 empty-field validation fixture')
        doc.save(source)
    app,base,_=helper.start_server(root/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        results=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for round_number in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                for operation,details in operations.items():
                    page.goto(base+'/?tool='+operation,wait_until='domcontentloaded')
                    page.locator('#file-input').set_input_files(str(source))
                    field=page.locator(details['input']);field.wait_for(state='visible')
                    assert not field.input_value().strip(),(operation,field.input_value())
                    button=page.locator('#run-button');assert button.is_disabled(),operation
                    hint=field.get_attribute('aria-describedby')
                    hint_text=page.locator('#'+hint).inner_text() if hint else ''
                    assert hint_text and 'Operation Failed' not in hint_text,(operation,hint_text)
                    results.append({'round':round_number,'operation':operation,'run_disabled':True,'hint':hint_text,'aria_invalid':field.get_attribute('aria-invalid')})
                assert not errors,errors
                if round_number==1:page.screenshot(path=str(OUT/'id76-empty-field-desktop.png'),full_page=True)
                context.close()
            browser.close()
        payload={'cases':results};(OUT/'browser-id76-empty-field-hints.json').write_text(json.dumps(payload,indent=2),encoding='utf-8');print(json.dumps(payload,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
