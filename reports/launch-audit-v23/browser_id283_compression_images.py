from pathlib import Path
from tempfile import TemporaryDirectory
import io,json,socket,sys,time
import fitz
from PIL import Image,ImageDraw
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2];OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id283-') as temp:
    root=Path(temp);source=root/'image-heavy-5-pages.pdf'
    with fitz.open() as doc:
        for idx in range(5):
            photo=Image.new('RGB',(700,900),'white');draw=ImageDraw.Draw(photo)
            color=(205,45+idx*8,32+idx*4);draw.rectangle((70,80,630,800),fill=color)
            draw.text((100,130),f'PAGE PHOTO {idx+1}',fill='black')
            encoded=io.BytesIO();photo.save(encoded,format='JPEG',quality=88)
            page=doc.new_page(width=600,height=800);page.insert_image(fitz.Rect(30,30,570,720),stream=encoded.getvalue())
            page.insert_text((40,770),f'Source page marker {idx+1}')
        doc.save(source,deflate=True)
    rounds=[]
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for n in (1,2):
            app,base,identity=helper.start_server(root/f'data-{n}')
            try:
                port=int(base.rsplit(':',1)[1])
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1',port),timeout=.2):break
                    except OSError:time.sleep(.15)
                email,token=identity['accounts'][0]
                context=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
                context.add_cookies([{'name':'paperplane_token','value':token,'url':base,'httpOnly':True}])
                page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                modes=[]
                for preset in ('100kb','balanced'):
                    page.goto(base+'/compress-pdf',wait_until='domcontentloaded')
                    page.wait_for_function("state.operation==='compress'")
                    page.locator('#file-input').set_input_files(str(source));page.wait_for_function("state.files.length===1")
                    page.locator('#preset').select_option(preset)
                    page.evaluate("window.confirm=()=>true")
                    page.locator('#run-button').click()
                    page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=90000)
                    with page.expect_download() as info:page.locator('#result-download-link').click()
                    download=info.value;name=download.suggested_filename;output=root/f'{n}-{preset}.pdf';download.save_as(output)
                    with fitz.open(output) as pdf:
                        assert pdf.page_count==5,(preset,pdf.page_count)
                        pages=[]
                        for idx,doc_page in enumerate(pdf):
                            text=doc_page.get_text()
                            assert f'Source page marker {idx+1}' in text,(preset,idx,text)
                            point=fitz.Point(doc_page.rect.width*.5,doc_page.rect.height*.45)
                            pix=doc_page.get_pixmap(clip=fitz.Rect(point.x-2,point.y-2,point.x+2,point.y+2),alpha=False)
                            rgb=pix.pixel(1,1)[:3]
                            assert rgb[0]>150 and rgb[0]>rgb[1]*1.5 and rgb[0]>rgb[2]*2,(preset,idx,rgb)
                            pages.append({'text_marker':f'Source page marker {idx+1}','pixel':rgb})
                    assert not errors,errors
                    modes.append({'preset':preset,'filename':name,'bytes':output.stat().st_size,'pages':pages,'page_errors':errors})
                page.screenshot(path=str(OUT/f'id283-compression-round{n}.png'))
                rounds.append({'round':n,'presets':modes})
                context.close()
            finally:app.terminate();app.wait(timeout=5)
        browser.close()
    result={'rounds':rounds};(OUT/'browser-id283-compression-images.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
