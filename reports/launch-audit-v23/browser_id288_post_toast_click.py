from pathlib import Path
from tempfile import TemporaryDirectory
import json,socket,sys,time
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id288-') as temp:
    source=Path(temp)/'protect-fixture.pdf'
    with fitz.open() as pdf:
        page=pdf.new_page();page.insert_text((72,72),'Protected download overlay fixture');pdf.save(source)
    rounds=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for n in (1,2):
            app,base,identity=helper.start_server(Path(temp)/f'db-{n}')
            try:
                port=int(base.rsplit(':',1)[1])
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                    except OSError:time.sleep(.15)
                email,token=identity['accounts'][0]
                context=browser.new_context(viewport={'width':390,'height':844},accept_downloads=True)
                context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/protect-pdf',wait_until='domcontentloaded');page.wait_for_function("state.operation==='protect'")
                page.locator('#file-input').set_input_files(str(source));page.wait_for_function("state.files.length===1")
                page.locator('#password').fill('audit-password-288')
                page.locator('#run-button').click();page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=90000)
                with page.expect_download() as first_info:page.locator('#result-download-link').click()
                first=first_info.value;first_path=Path(temp)/f'{n}-first.pdf';first.save_as(first_path)
                with fitz.open(first_path) as pdf:assert pdf.page_count==1 and pdf.is_encrypted
                immediate=page.evaluate("""() => {const e=document.querySelector('#result-download-link'),r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {hidden:e.hidden,disabled:e.disabled,hit:hit?.id||hit?.className,hitInsideLink:!!hit&&e.contains(hit),toast:document.querySelector('.toast-notice')?.innerText||null,rect:{x:r.x,y:r.y,w:r.width,h:r.height},pointer:getComputedStyle(document.querySelector('.toast-notice')).pointerEvents}}""")
                page.wait_for_timeout(6500)
                after=page.evaluate("""() => {const e=document.querySelector('#result-download-link'),r=e.getBoundingClientRect(),hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {hidden:e.hidden,disabled:e.disabled,hit:hit?.id||hit?.className,hitInsideLink:!!hit&&e.contains(hit),toast:document.querySelector('.toast-notice')?.innerText||null}}""")
                with page.expect_download() as second_info:page.locator('#result-download-link').click()
                second=second_info.value;second_path=Path(temp)/f'{n}-second.pdf';second.save_as(second_path)
                with fitz.open(second_path) as pdf:assert pdf.page_count==1 and pdf.is_encrypted
                assert immediate['pointer']=='none' and immediate['hitInsideLink'] and after['hitInsideLink'],(immediate,after)
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id288-toast-round{n}.png'))
                rounds.append({'round':n,'first_download':first.suggested_filename,'immediate_hit':immediate,'after_toast_hit':after,
                    'second_download':second.suggested_filename,'page_errors':errors})
                context.close()
            finally:app.terminate();app.wait(timeout=5)
        browser.close()
    result={'rounds':rounds};(OUT/'browser-id288-post-toast-click.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
