from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id66-') as temp:
    app, base, _ = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2):break
            except OSError:time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for number in (1,2):
                for width,height in ((320,800),(390,844),(820,900)):
                    page=browser.new_page(viewport={'width':width,'height':height})
                    errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                    page.goto(base+'/developers',wait_until='domcontentloaded')
                    page.wait_for_function("document.querySelector('#view-api-docs')?.hidden===false && document.querySelector('.endpoints-table')")
                    measurements=page.evaluate("""()=>{
                      const r=e=>{const x=e.getBoundingClientRect();return {x:Math.round(x.x),right:Math.round(x.right),width:Math.round(x.width),height:Math.round(x.height)}};
                      const table=document.querySelector('.endpoints-table'),wrapper=document.querySelector('.endpoints-table-wrapper'),rows=[...table.querySelectorAll('tbody tr')];
                      return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,table:r(table),wrapper:r(wrapper),rowCount:rows.length,rowOverflow:rows.flatMap((row,index)=>[...row.querySelectorAll('td')].map((cell)=>({row:index+1,label:cell.dataset.label,rect:r(cell),scrollWidth:cell.scrollWidth,clientWidth:cell.clientWidth}))).filter(cell=>cell.rect.right>wrapper.getBoundingClientRect().right+1||cell.rect.x<wrapper.getBoundingClientRect().x-1),tableScrollWidth:table.scrollWidth,wrapperClientWidth:wrapper.clientWidth};
                    }""")
                    assert measurements['documentWidth']<=width,measurements
                    assert measurements['rowOverflow']==[],measurements['rowOverflow'][:5]
                    page.screenshot(path=str(OUT/f'id66-developers-{width}-round{number}.png'))
                    assert not errors,errors
                    rounds.append({'round':number,'viewport':width,'metrics':measurements,'page_errors':errors})
                    page.close()
            browser.close()
        result={'rounds':rounds};(OUT/'browser-id66-developer-tables.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
