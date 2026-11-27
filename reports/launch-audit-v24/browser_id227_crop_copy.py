from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='paperplane-id227-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
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
                page.goto(base+'/crop-pdf',wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('.seo-lede')?.textContent.includes('without resizing the content manually in a design tool')")
                copy=page.locator('.seo-lede').inner_text().strip()
                assert 'without resizing the content manual.' not in copy and copy.endswith('without resizing the content manually in a design tool.'),copy
                page.screenshot(path=str(OUT/f'id227-crop-copy-round{n}.png'))
                rounds.append({'round':n,'rendered_copy':copy,'page_errors':errors});assert not errors
                page.context.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id227-crop-copy-current.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:app.terminate();app.wait(timeout=5)
