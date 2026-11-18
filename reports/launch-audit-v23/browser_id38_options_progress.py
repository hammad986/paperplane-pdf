from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id38-') as temp:
    root = Path(temp)
    pdf = root / 'split-10-pages.pdf'
    image = root / 'exam-photo.jpg'
    with fitz.open() as doc:
        for n in range(1, 11):
            page = doc.new_page()
            page.insert_text((72, 72), f'Combobox test page {n}')
        doc.save(pdf)
    photo = Image.new('RGB', (900, 1200), '#c48765')
    draw = ImageDraw.Draw(photo)
    draw.ellipse((260, 120, 640, 650), fill='#e1b093')
    draw.rectangle((160, 620, 740, 1199), fill='#254b62')
    photo.save(image, quality=92)
    app, base, _identity = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            errors = []
            options = []
            for viewport_width in (390, 1366):
                context = browser.new_context(viewport={'width': viewport_width, 'height': 900})
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/split-pdf', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelector('#split_mode') && document.querySelector('#split_mode option[value=all_pages]')?.textContent.includes('All 10 pages')", timeout=20000)
                split_select = page.locator('#split_mode')
                split_option = page.locator('#split_mode option[value=all_pages]').text_content()
                split_widths = split_select.evaluate("el => { const c=document.createElement('canvas').getContext('2d'); c.font=getComputedStyle(el).font; return {available:el.clientWidth-parseFloat(getComputedStyle(el).paddingLeft)-parseFloat(getComputedStyle(el).paddingRight)-28,label:c.measureText(el.options[0].text).width}; }")
                page.goto(base + '/ssc-photo-resizer', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(image))
                page.wait_for_function("document.querySelector('#preset option[value=ssc_photo]')?.textContent.includes('SSC Photo')", timeout=15000)
                preset_select = page.locator('#preset')
                ssc_option = page.locator('#preset option[value=ssc_photo]').text_content()
                ssc_widths = preset_select.evaluate("el => { const c=document.createElement('canvas').getContext('2d'); c.font=getComputedStyle(el).font; return {available:el.clientWidth-parseFloat(getComputedStyle(el).paddingLeft)-parseFloat(getComputedStyle(el).paddingRight)-28,label:c.measureText(el.options[0].text).width}; }")
                options.append({'viewport_width':viewport_width,'split_option':split_option,'split_text_fit':split_widths['label']<=split_widths['available'],'split_widths':split_widths,'ssc_option':ssc_option,'ssc_text_fit':ssc_widths['label']<=ssc_widths['available'],'ssc_widths':ssc_widths})
                context.close()

            progress_cases = []
            for slug, signature in (('flatten-pdf', None), ('sign-pdf', 'Paperplane Test Signer')):
                context = browser.new_context(viewport={'width':1366,'height':900})
                page = context.new_page()
                page.on('pageerror', lambda error: errors.append(str(error)))
                status_reads = {'count':0}
                def hold_processing(route):
                    response=route.fetch()
                    body=response.json()
                    status_reads['count']+=1
                    if status_reads['count'] <= 3:
                        body['status']='processing'
                        body['progress']=35
                        route.fulfill(response=response, json=body)
                    else:
                        route.fulfill(response=response)
                page.route('**/api/jobs/*', hold_processing)
                page.goto(base + '/' + slug, wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(pdf))
                page.locator('#run-button').wait_for(state='visible',timeout=10000)
                page.wait_for_function("!document.querySelector('#run-button').disabled",timeout=20000)
                if signature:
                    page.locator('#signature').fill(signature)
                page.locator('#run-button').click()
                page.wait_for_function("document.querySelector('#progress-card')?.hidden === false && !document.querySelector('#progress-bar-fill')?.hasAttribute('value') && document.querySelector('#progress-status-title')?.textContent.includes('Processing your document')", timeout=20000)
                progress_cases.append({'tool':slug,'processing_text':page.locator('#progress-status-title').text_content(),'bar_has_fabricated_percent':page.locator('#progress-bar-fill').get_attribute('value') is not None,'status_responses_held':status_reads['count']})
                page.wait_for_function("document.querySelector('#result')?.hidden === false",timeout=45000)
                context.close()

            context=browser.new_context(viewport={'width':1366,'height':900},accept_downloads=True)
            page=context.new_page()
            page.on('pageerror',lambda error:errors.append(str(error)))
            page.goto(base+'/ssc-photo-resizer',wait_until='domcontentloaded')
            page.locator('#file-input').set_input_files(str(image))
            page.locator('#run-button').wait_for(state='visible',timeout=10000)
            page.wait_for_function("!document.querySelector('#run-button').disabled",timeout=15000)
            page.evaluate("""() => { const original=processClientSide; processClientSide=async()=>{ await new Promise(r=>setTimeout(r,1800)); return original(); }; }""")
            page.locator('#run-button').click()
            page.wait_for_function("document.querySelector('#progress-card')?.hidden === false && !document.querySelector('#progress-bar-fill')?.hasAttribute('value')",timeout=5000)
            photo_progress={'processing_text':page.locator('#progress-status-title').text_content(),'bar_has_fabricated_percent':page.locator('#progress-bar-fill').get_attribute('value') is not None}
            page.wait_for_function("document.querySelector('#result')?.hidden === false",timeout=30000)
            result={'combobox_measurements':options,'indeterminate_processing':progress_cases,'exam_resizer_processing':photo_progress,'page_errors':errors}
            (OUT/'browser-id38-options-progress.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            assert len(options)==2 and all(x['split_text_fit'] and x['ssc_text_fit'] for x in options)
            assert len(progress_cases)==2 and all('processing' in x['processing_text'].lower() and not x['bar_has_fabricated_percent'] for x in progress_cases)
            assert not photo_progress['bar_has_fabricated_percent'] and not errors
            page.screenshot(path=str(OUT/'id38-exam-resizer-progress.png'))
            context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
