from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id121-') as temp:
    root=Path(temp);source=root/'sign-draw-source.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'Signature source marker ID121');doc.save(source)
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
                context=browser.new_context(viewport={'width':390,'height':844},accept_downloads=True)
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/sign-pdf',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(source))
                page.wait_for_function("window.state?.files?.some(f=>f.name==='sign-draw-source.pdf')",timeout=10000)
                canvas=page.locator('#sign-draw-canvas');canvas.wait_for(state='visible')
                canvas.scroll_into_view_if_needed()
                page.evaluate('window.scrollBy(0, 180)')
                page.evaluate("window.__id121PointerEvents=[];const c=document.querySelector('#sign-draw-canvas');for(const n of ['pointerdown','pointermove','pointerup'])c.addEventListener(n,e=>window.__id121PointerEvents.push({type:e.type,x:e.clientX,y:e.clientY}))")
                bounds=canvas.bounding_box();assert bounds and bounds['width']>=300
                page.mouse.move(bounds['x']+20,bounds['y']+70);page.mouse.down();page.mouse.move(bounds['x']+90,bounds['y']+35,steps=8);page.mouse.up()
                first=page.locator('#signature_data').input_value()
                debug=page.evaluate("""()=>{const c=document.querySelector('#sign-draw-canvas'),x=c.getContext('2d'),d=x.getImageData(0,0,c.width,c.height).data,p=c.getBoundingClientRect();return {signature:document.querySelector('#signature_data').value.length,status:document.querySelector('#sign-draw-status').textContent,opaquePixels:[...d].filter((v,i)=>i%4===3&&v>0).length,rect:p.toJSON(),hit:document.elementFromPoint(p.left+20,p.top+70)?.id,events:window.__id121PointerEvents}}""")
                assert first.startswith('data:image/png;base64,'),debug
                page.locator('#sign-clear-canvas').click();assert page.locator('#signature_data').input_value()==''
                page.mouse.move(bounds['x']+25,bounds['y']+90);page.mouse.down()
                for dx,dy in ((60,-28),(110,18),(155,-44),(205,26),(260,-18),(320,6)):
                    page.mouse.move(bounds['x']+25+dx,bounds['y']+90+dy,steps=3)
                page.mouse.up()
                signature=page.locator('#signature_data').input_value();assert signature.startswith('data:image/png;base64,')
                page.locator('#signature').fill('Alex Drawn')
                with page.expect_response('**/api/jobs') as event:page.locator('#run-button').click()
                accepted=event.value;assert accepted.status==202
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=25000)
                with page.expect_download(timeout=20000) as download_event:page.locator('#result-download-link').click()
                download=download_event.value;output=root/f'id121-round{number}.pdf';download.save_as(output)
                with fitz.open(output) as result:
                    text='\n'.join(pg.get_text() for pg in result)
                    page_images=[image for pg in result for image in pg.get_images(full=True)]
                    assert len(result)==1 and 'Signature source marker ID121' in text and 'Alex Drawn' in text
                    assert page_images,page_images
                    rendered=result[0].get_pixmap(matrix=fitz.Matrix(1,1),alpha=False)
                    pixels=rendered.samples
                    ink=sum(1 for i in range(0,len(pixels),rendered.n) if min(pixels[i:i+3])<80)
                    assert ink>30,ink
                assert not errors,errors
                page.screenshot(path=str(OUT/f'id121-sign-draw-round{number}.png'),full_page=True)
                rounds.append({'round':number,'viewport':'390x844','drawn_png_data_url':True,'clear_button_reset_data':True,'download':download.suggested_filename,'page_count':1,'embedded_signature_images':len(page_images),'signer_and_source_text_checked':True,'rendered_dark_ink_pixels':ink,'page_errors':errors})
                context.close()
            browser.close()
        data={'rounds':rounds};(OUT/'browser-id121-sign-draw.json').write_text(json.dumps(data,indent=2),encoding='utf-8');print(json.dumps(data,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
