from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-277-278-') as temp:
    root=Path(temp)
    image_path=root/'scan-page.png'
    image=Image.new('RGB',(900,1200),'white'); draw=ImageDraw.Draw(image)
    draw.text((70,100),'PAPERPLANE SCAN FIXTURE',fill='black')
    draw.text((70,180),'Discriminating content marker 277 278',fill='black')
    image.save(image_path)
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
                page=context.new_page(); errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                pages=[]
                for slug, operation in [('jpg-to-pdf','jpg_to_pdf'),('scan-to-pdf','scan_pdf')]:
                    if operation == 'scan_pdf':
                        scan_layouts=[]
                        for width in (320,390,1366):
                            page.set_viewport_size({'width':width,'height':760})
                            page.goto(base+'/scan-to-pdf',wait_until='domcontentloaded')
                            page.wait_for_function("state.operation==='scan_pdf'")
                            layout=page.evaluate("""() => ({viewport:innerWidth,body:document.body.scrollWidth,copy:[...document.querySelectorAll('#view-tool-desk h1,#view-tool-desk h2,#view-tool-desk h3,#view-tool-desk p')].filter(e=>e.getClientRects().length).map(e=>({text:e.innerText.trim(),scroll:e.scrollWidth,client:e.clientWidth,left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}))})""")
                            assert layout['body']<=width,layout
                            assert all(item['scroll']<=item['client']+1 for item in layout['copy']),layout
                            scan_layouts.append(layout)
                        page.set_viewport_size({'width':1366,'height':900})
                    page.goto(base+'/'+slug,wait_until='domcontentloaded')
                    page.wait_for_function('(op)=>state.operation===op',arg=operation)
                    # Current Scan page layout: inspect all visible instructional copy and bounds.
                    instructions=page.evaluate("""() => [...document.querySelectorAll('#view-tool-desk p, #view-tool-desk li, #view-tool-desk h1, #view-tool-desk h2, #view-tool-desk h3')]
                      .filter(e=>e.getClientRects().length).map(e=>({text:e.innerText.trim(),scroll:e.scrollWidth,client:e.clientWidth,rect:{left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}}))""")
                    assert not any('separate enhancement co' in item['text'].lower() for item in instructions),instructions
                    if operation == 'scan_pdf':
                        scan_copy=' '.join(item['text'] for item in instructions)
                        assert 'Automatic contrast and sharpness enhancement is applied' in scan_copy and 'original photo size at 200 DPI' in scan_copy,scan_copy
                    page.evaluate("""() => { window.__progressEvidence=[]; const record=()=>{const c=document.querySelector('#progress-card');if(c&&!c.hidden)window.__progressEvidence.push({percent:document.querySelector('#progress-percent')?.textContent,title:document.querySelector('#progress-status-title')?.textContent});};new MutationObserver(record).observe(document.querySelector('#progress-card'),{attributes:true,childList:true,subtree:true,characterData:true}); }""")
                    page.locator('#file-input').set_input_files(str(image_path))
                    page.wait_for_function("state.files.length === 1")
                    assert not page.locator('#run-button').is_disabled()
                    page.locator('#run-button').click()
                    page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=90000)
                    progress=page.evaluate('window.__progressEvidence')
                    assert any(item['percent']=='100%' and item['title']=='Finished!' for item in progress),progress
                    async_download=page.expect_download()
                    with async_download as download_info:
                        page.locator('#result-download-link').click()
                    download=download_info.value
                    output=root/f'{n}-{operation}.pdf';download.save_as(output)
                    with fitz.open(output) as pdf:
                        assert pdf.page_count==1,(slug,pdf.page_count)
                        marker=' '.join(page.get_text() for page in pdf).lower()
                        raster=pdf[0].get_pixmap(matrix=fitz.Matrix(.5,.5),alpha=False)
                        dark_pixels=sum(1 for y in range(raster.height) for x in range(raster.width) if max(raster.pixel(x,y))<245)
                        assert dark_pixels>100,(slug,dark_pixels,marker)
                        pixels=list(raster.samples)
                        output_evidence={'pages':pdf.page_count,'bytes':output.stat().st_size,'text':marker,'dark_pixels':dark_pixels,'raster_min':min(pixels),'raster_max':max(pixels),'raster_mean':sum(pixels)/len(pixels),'raster_size':[raster.width,raster.height]}
                    assert not errors,errors
                    pages.append({'route':slug,'operation':operation,'instructions':instructions,'scan_responsive_layouts':scan_layouts if operation=='scan_pdf' else [],'progress_events':progress,'download':output_evidence,'page_errors':errors})
                page.screenshot(path=str(OUT/f'id277-278-round{n}.png'))
                rounds.append({'round':n,'tool_runs':pages})
                context.close()
            finally:
                app.terminate();app.wait(timeout=5)
        browser.close()
    result={'rounds':rounds}
    (OUT/'browser-ids277-278.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
