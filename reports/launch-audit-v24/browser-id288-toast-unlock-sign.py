"""Content-checked toast click-through checks for Unlock and Sign output actions."""
from __future__ import annotations
import json, socket, sys, time
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

def overlap(a,b):
    return bool(a and b and a['x'] < b['x']+b['width'] and a['x']+a['width'] > b['x'] and a['y'] < b['y']+b['height'] and a['y']+a['height'] > b['y'])

def within_viewport(box,height):
    return bool(box and box['y'] >= 0 and box['y']+box['height'] <= height)

def rect(locator):
    if not locator.count(): return None
    return locator.evaluate("e=>{const r=e.getBoundingClientRect();return r.width&&r.height?{x:r.x,y:r.y,width:r.width,height:r.height}:null}")

def fixed_mobile_bounds(page):
    return rect(page.locator('#run-button')), rect(page.locator('.mobile-workspace-bar'))

def main():
    viewport_width=int(os.environ.get('PAPERPLANE_TOAST_VIEWPORT','390'))
    viewport_height=int(os.environ.get('PAPERPLANE_TOAST_VIEWPORT_HEIGHT','844'))
    evidence={'rounds':[],'page_errors':[],'console_errors':[]}
    with TemporaryDirectory(prefix='paperplane-v24-toast-unlock-sign-') as tmp:
        tmp=Path(tmp)
        source=tmp/'toast-source.pdf'
        with fitz.open() as pdf:
            page=pdf.new_page(); page.insert_text((72,90),'TOAST CLICK THROUGH CONTENT CHECK')
            pdf.save(source)
        protected=tmp/'toast-protected.pdf'
        with fitz.open(source) as pdf:
            pdf.save(protected,encryption=fitz.PDF_ENCRYPT_AES_256,user_pw='Toast-Click-Password!24',owner_pw='Toast-Click-Owner!24')
        photo_paths=[]
        for idx, color in enumerate(('#d6336c','#1864ab'),start=1):
            photo=Image.new('RGB',(320,240),color)
            ImageDraw.Draw(photo).text((24,30),f'PHOTO MARKER {idx}',fill='white')
            photo_path=tmp/f'photo-{idx}.png'; photo.save(photo_path); photo_paths.append(photo_path)
        app,base,_=helper.start_server(tmp/'data')
        try:
            port=int(base.rsplit(':',1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(('127.0.0.1',port),timeout=.2): break
                except OSError: time.sleep(.2)
            else: raise RuntimeError('server failed to start')
            with sync_playwright() as p:
                browser=p.chromium.launch(channel='chrome',headless=True)
                page=browser.new_page(viewport={'width':viewport_width,'height':viewport_height},accept_downloads=True)
                page.on('pageerror',lambda err:evidence['page_errors'].append(str(err)))
                page.on('console',lambda msg:evidence['console_errors'].append(msg.text) if msg.type=='error' else None)
                for operation,path,file,field,value in (
                    ('unlock','/unlock-pdf',protected,'#password','Toast-Click-Password!24'),
                    ('sign','/sign-pdf',source,'#signature','Toast QA'),
                ):
                    response=page.goto(base+path,wait_until='domcontentloaded')
                    page.locator('#file-input').set_input_files(str(file))
                    page.locator(field).fill(value)
                    page.locator('#run-button').click()
                    page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000)
                    link=page.locator('#result-download-link')
                    button_box=rect(link)
                    page.evaluate("showToast('Download complete!', 'success', 10000)")
                    toast=page.locator('.toast-notice').filter(has_text='Download complete!')
                    toast.wait_for(state='visible')
                    toast_box=toast.bounding_box()
                    run_box,nav_box=fixed_mobile_bounds(page)
                    with page.expect_download(timeout=30000) as pending: link.click()
                    download=pending.value; output=tmp/download.suggested_filename
                    download.save_as(output)
                    with fitz.open(output) as result:
                        valid=result.is_pdf and result.page_count==1
                        if operation=='unlock':
                            valid=valid and not result.needs_pass and 'TOAST CLICK THROUGH CONTENT CHECK' in result[0].get_text()
                        else:
                            valid=valid and 'Toast QA' in result[0].get_text()
                    evidence['rounds'].append({'operation':operation,'viewport':viewport_width,'viewport_height':viewport_height,'route_status':response.status if response else None,
                        'download':download.suggested_filename,'content_checked':valid,'download_button':button_box,'toast':toast_box,
                        'download_button_inside_viewport':within_viewport(button_box,viewport_height),
                        'run_button':run_box,'bottom_navigation':nav_box,
                        'toast_intersects_run_button':overlap(toast_box,run_box),
                        'toast_intersects_bottom_navigation':overlap(toast_box,nav_box),
                        'toast_intersects_button':overlap(button_box,toast_box),'toast_pointer_events':toast.evaluate('e=>getComputedStyle(e).pointerEvents')})
                response=page.goto(base+'/merge-photos-online',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files([str(path) for path in photo_paths])
                page.wait_for_function("state.files?.length === 2")
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000)
                link=page.locator('#result-download-link'); button_box=rect(link)
                page.evaluate("showToast('Download complete!', 'success', 10000)")
                toast=page.locator('.toast-notice').filter(has_text='Download complete!'); toast.wait_for(state='visible')
                toast_box=toast.bounding_box()
                run_box,nav_box=fixed_mobile_bounds(page)
                with page.expect_download(timeout=30000) as pending: link.click()
                download=pending.value; output=tmp/download.suggested_filename; download.save_as(output)
                with Image.open(output) as merged_image:
                    merged_rgb=merged_image.convert('RGB')
                    pixels=merged_rgb.resize((min(160,merged_rgb.width),min(160,merged_rgb.height))).get_flattened_data()
                    has_first_color=any(r>170 and g<110 and b>60 for r,g,b in pixels)
                    has_second_color=any(r<80 and g>45 and b>110 for r,g,b in pixels)
                    image_size=merged_image.size
                    content_checked=(merged_image.format=='JPEG' and image_size[0]>0 and image_size[1]>0
                                     and has_first_color and has_second_color)
                evidence['rounds'].append({'operation':'photo_merge','viewport':viewport_width,'viewport_height':viewport_height,'route_status':response.status if response else None,
                    'download':download.suggested_filename,'content_checked':content_checked,'image_format':'JPEG',
                    'image_dimensions':image_size,'first_source_color_present':has_first_color,
                    'second_source_color_present':has_second_color,'download_button':button_box,'toast':toast_box,
                    'download_button_inside_viewport':within_viewport(button_box,viewport_height),
                    'run_button':run_box,'bottom_navigation':nav_box,
                    'toast_intersects_run_button':overlap(toast_box,run_box),
                    'toast_intersects_bottom_navigation':overlap(toast_box,nav_box),
                    'toast_intersects_button':overlap(button_box,toast_box),
                    'toast_pointer_events':toast.evaluate('e=>getComputedStyle(e).pointerEvents')})
                response=page.goto(base+'/annotate-pdf',wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(source))
                page.wait_for_function("state.files?.length === 1")
                page.locator('#annot_type').select_option('highlight')
                page.locator('#text').fill('TOAST CLICK THROUGH CONTENT CHECK')
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(timeout=60000)
                link=page.locator('#result-download-link'); button_box=rect(link)
                page.evaluate("showToast('Download complete!', 'success', 10000)")
                toast=page.locator('.toast-notice').filter(has_text='Download complete!'); toast.wait_for(state='visible')
                toast_box=toast.bounding_box()
                run_box,nav_box=fixed_mobile_bounds(page)
                layout_state=page.evaluate("""() => ({scrollY, viewportHeight:innerHeight,
                    runPosition:getComputedStyle(document.querySelector('#run-button')).position,
                    runDisplay:getComputedStyle(document.querySelector('#run-button')).display,
                    runRect:(()=>{const r=document.querySelector('#run-button').getBoundingClientRect();return{x:r.x,y:r.y,width:r.width,height:r.height}})(),
                    documentHeight:document.documentElement.scrollHeight})""")
                evidence['short_viewport_layout']=layout_state if viewport_height<700 else None
                if viewport_height<700:
                    page.screenshot(path=str(Path(__file__).parent/f'browser-id288-annotate-short-{viewport_width}x{viewport_height}.png'))
                with page.expect_download(timeout=30000) as pending: link.click()
                download=pending.value; output=tmp/download.suggested_filename; download.save_as(output)
                with fitz.open(output) as result:
                    annotation_count=len(list(result[0].annots() or [])) if result.page_count else 0
                    content_checked=result.is_pdf and result.page_count==1 and annotation_count>=1
                evidence['rounds'].append({'operation':'annotate','viewport':viewport_width,'viewport_height':viewport_height,'route_status':response.status if response else None,
                    'download':download.suggested_filename,'content_checked':content_checked,'annotation_count':annotation_count,
                    'download_button':button_box,'download_button_inside_viewport':within_viewport(button_box,viewport_height),
                    'toast':toast_box,'toast_intersects_button':overlap(button_box,toast_box),
                    'run_button':run_box,'bottom_navigation':nav_box,
                    'toast_intersects_run_button':overlap(toast_box,run_box),
                    'toast_intersects_bottom_navigation':overlap(toast_box,nav_box),
                    'toast_pointer_events':toast.evaluate('e=>getComputedStyle(e).pointerEvents')})
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=5)
    evidence['result']=len(evidence['rounds'])==4 and not evidence['page_errors'] and not evidence['console_errors'] and all(
        r['route_status']==200 and r['content_checked'] and r['toast_pointer_events']=='none'
        and r['download_button_inside_viewport'] and not r['toast_intersects_button'] and not r['toast_intersects_run_button']
        and not r['toast_intersects_bottom_navigation'] for r in evidence['rounds'])
    suffix='' if viewport_width==390 and viewport_height==844 else f'-{viewport_width}x{viewport_height}'
    (Path(__file__).parent/f'browser-id288-toast-unlock-sign{suffix}.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
    print(json.dumps(evidence,indent=2))
    if not evidence['result']: raise SystemExit(1)
if __name__=='__main__': main()
