from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id68-') as temp:
    root=Path(temp);source=root/'signature-source.pdf'
    with fitz.open() as doc:
        page=doc.new_page();page.insert_text((72,72),'ID68 signature visual output check')
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
                context=browser.new_context(viewport={'width':390,'height':844},is_mobile=True,has_touch=True,accept_downloads=True)
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                page.goto(base+'/studio',wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(source))
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered==='true'",timeout=20000)
                page.locator('#tool-sig-btn').click()
                page.locator('#pdf-draw-canvas').click(position={'x':110,'y':130})
                page.locator('#editor-signature-modal').wait_for(state='visible')
                canvas=page.locator('#editor-sig-canvas');rect=canvas.bounding_box();assert rect and rect['width']>100 and rect['height']>50,rect
                cdp=context.new_cdp_session(page)
                points=[(rect['x']+40,rect['y']+90),(rect['x']+80,rect['y']+45),(rect['x']+125,rect['y']+115),(rect['x']+175,rect['y']+58),(rect['x']+220,rect['y']+100)]
                cdp.send('Input.dispatchTouchEvent',{'type':'touchStart','touchPoints':[{'x':points[0][0],'y':points[0][1],'id':1}]})
                for x,y in points[1:]:cdp.send('Input.dispatchTouchEvent',{'type':'touchMove','touchPoints':[{'x':x,'y':y,'id':1}]})
                cdp.send('Input.dispatchTouchEvent',{'type':'touchEnd','touchPoints':[]})
                pixels=page.evaluate("""()=>{const c=document.querySelector('#editor-sig-canvas'),ctx=c.getContext('2d'),data=ctx.getImageData(0,0,c.width,c.height).data;let ink=0;for(let i=0;i<data.length;i+=4)if(data[i+3]>0 && (data[i]<210||data[i+1]<210||data[i+2]<210))ink++;return {inkPixels:ink,width:c.width,height:c.height}}""")
                assert pixels['inkPixels']>100,pixels
                page.locator('#editor-sig-place-btn').click()
                page.locator('#editor-signature-modal').wait_for(state='hidden')
                modal_state=page.locator('#editor-signature-modal').evaluate("e=>({hidden:e.hidden,display:getComputedStyle(e).display,rect:e.getBoundingClientRect().toJSON(),aria:e.getAttribute('aria-hidden')})")
                page.wait_for_function("window.PaperplaneEditor?.editorState?.getObjects(1).some(item=>item.type==='signature')",timeout=8000)
                signatures=page.evaluate("window.PaperplaneEditor.editorState.getObjects(1).filter(item=>item.type==='signature').length")
                with page.expect_download(timeout=20000) as event:page.locator('#save-studio-btn').click()
                download=event.value;output=root/f'id68-signature-round{number}.pdf';download.save_as(output)
                with fitz.open(output) as result:
                    result_text=result[0].get_text();pix=result[0].get_pixmap(alpha=False)
                    rendered_nonwhite=sum(1 for y in range(pix.height) for x in range(pix.width) if tuple(pix.pixel(x,y)[:3])!=(255,255,255))
                    result_pages=result.page_count
                assert result_pages==1 and 'ID68 signature visual output check' in result_text and rendered_nonwhite>1000,(result_pages,result_text,rendered_nonwhite)
                assert signatures==1 and not errors,{'signatures':signatures,'errors':errors}
                page.screenshot(path=str(OUT/f'id68-touch-signature-round{number}.png'))
                rounds.append({'round':number,'touch_signature_ink_pixels':pixels['inkPixels'],'signature_objects_placed':signatures,'modal_hidden_state':modal_state,'download':download.suggested_filename,'output_pages':result_pages,'output_text_retained':True,'rendered_nonwhite_pixels':rendered_nonwhite,'page_errors':errors})
                context.close()
            browser.close()
        output={'rounds':rounds};(OUT/'browser-id68-draw-signature-touch.json').write_text(json.dumps(output,indent=2),encoding='utf-8');print(json.dumps(output,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
