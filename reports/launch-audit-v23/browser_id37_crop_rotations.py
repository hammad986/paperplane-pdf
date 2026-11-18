from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from PIL import Image, ImageChops
from playwright.sync_api import sync_playwright
root=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(root/'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper
with TemporaryDirectory(prefix='crop-rotation-') as temp:
    d=Path(temp); src=d/'rotations.pdf'
    with fitz.open() as doc:
        for rotation in (0,90,180,270):
            p=doc.new_page(width=300,height=200)
            for x,y,c in [(5,5,(1,0,0)),(275,5,(0,1,0)),(5,175,(0,0,1)),(275,175,(0,0,0))]:
                p.draw_rect(fitz.Rect(x,y,x+20,y+20),fill=c)
            p.insert_text((70,90),f'ROTATION {rotation}')
            p.set_rotation(rotation)
        doc.save(src)
    app,base,_=helper.start_server(d/'data')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1',int(base.rsplit(':',1)[1])),timeout=.2): break
            except OSError: time.sleep(.2)
        results=[]
        with sync_playwright() as pw:
            browser=pw.chromium.launch(channel='chrome',headless=True)
            for round_no in (1,2):
                context=browser.new_context(accept_downloads=True); page=context.new_page(); errors=[]; posts=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                context.on('request',lambda r:posts.append(r.url) if r.method=='POST' and r.url.endswith('/api/jobs') else None)
                page.goto(base+'/crop-pdf',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(src))
                for side,value in [('left',10),('top',15),('right',20),('bottom',25)]: page.locator('#'+side).fill(str(value))
                page.locator('#run-button').click(); page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
                with page.expect_download() as event: page.locator('#result-download-link').click()
                out=d/f'out{round_no}.pdf'; event.value.save_as(out)
                with fitz.open(src) as source, fitz.open(out) as result:
                    for n in range(4):
                        before=source[n].get_pixmap(alpha=False); after=result[n].get_pixmap(alpha=False)
                        image=Image.frombytes('RGB',[before.width,before.height],before.samples)
                        expected=image.crop((10,15,before.width-20,before.height-25))
                        actual=Image.frombytes('RGB',[after.width,after.height],after.samples)
                        assert expected.size==actual.size,(n,expected.size,actual.size)
                        assert ImageChops.difference(expected,actual).getbbox() is None, f'rotation {n*90} pixels differ'
                assert not errors and not posts,(errors,posts)
                results.append({'round':round_no,'rotations':[0,90,180,270],'visible_pixels_match':True,'api_posts':len(posts),'page_errors':errors})
                context.close()
            browser.close()
        report={'results':results,'status':'PASS'}
        (root/'reports/launch-audit-v23/browser-id37-crop-rotations.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
    finally:
        app.terminate()
        try: app.wait(timeout=15)
        except Exception: app.kill()
