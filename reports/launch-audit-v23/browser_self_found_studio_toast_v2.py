from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-studio-toast-') as temp:
    root = Path(temp)
    pdf_path = root / 'toast-layout.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=612, height=792)
        page.insert_text((72, 100), 'Toast placement must not cover this page content.')
        doc.save(pdf_path)
    compact_pdf_path = root / 'toast-compact-layout.pdf'
    with fitz.open() as doc:
        page = doc.new_page(width=792, height=612)
        page.insert_text((72, 100), 'A shorter landscape page leaves room for visible feedback.')
        doc.save(compact_pdf_path)
    app, base, _ = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for round_number in (1, 2):
                for width, height in ((390, 844), (320, 740)):
                    context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=True, has_touch=True)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/studio', wait_until='domcontentloaded')
                    page.locator('#studio-file-input').set_input_files(str(pdf_path))
                    page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
                    page.wait_for_selector('.toast-notice[role="status"]', timeout=5000)
                    page.wait_for_function("getComputedStyle(document.querySelector('.toast-notice')).top !== 'auto'")
                    measurements = page.evaluate("""() => {
                      const rect = s => { const e=document.querySelector(s); if(!e) return null; const r=e.getBoundingClientRect(); return {top:r.top,bottom:r.bottom,left:r.left,right:r.right,width:r.width,height:r.height}; };
                      const toast=document.querySelector('.toast-notice');
                      return {viewport:{width:innerWidth,height:innerHeight}, toast:rect('.toast-notice'), canvas:rect('#pdf-canvas'), sheet:rect('.studio-page-sheet'), dock:rect('#studio-mobile-dock'), role:toast.getAttribute('role'), live:toast.getAttribute('aria-live'), atomic:toast.getAttribute('aria-atomic'), visuallyHidden:toast.classList.contains('toast-visually-hidden'), text:toast.innerText};
                    }""")
                    toast, canvas, sheet, dock = measurements['toast'], measurements['canvas'], measurements['sheet'], measurements['dock']
                    available_gap = dock['top'] - sheet['bottom']
                    enough_gap = not measurements['visuallyHidden'] and toast['height'] + 12 <= available_gap
                    if not measurements['visuallyHidden']:
                        assert toast['top'] >= sheet['bottom'] + 7, measurements
                        assert toast['bottom'] <= dock['top'] - 7, measurements
                    else:
                        assert toast['width'] <= 1 and toast['height'] <= 1, measurements
                    assert measurements['role'] == 'status' and measurements['live'] == 'polite' and measurements['atomic'] == 'true', measurements
                    page.screenshot(path=str(OUT / f'self-found-studio-toast-v2-{width}-round{round_number}.png'), full_page=True)
                    page.evaluate("showToast('Controlled error announcement', 'error', 1000)")
                    error_announcement = page.locator('.toast-notice[role="alert"][aria-live="assertive"]').inner_text()
                    assert 'Controlled error announcement' in error_announcement
                    page.wait_for_timeout(100)
                    error_state = page.evaluate("""() => {
                      const r=s=>{const e=document.querySelector(s);const b=e.getBoundingClientRect();return {top:b.top,bottom:b.bottom,width:b.width,height:b.height}};
                      const t=document.querySelector('.toast-notice');return {toast:r('.toast-notice'),sheet:r('.studio-page-sheet'),dock:r('#studio-mobile-dock'),hidden:t.classList.contains('toast-visually-hidden'),role:t.getAttribute('role'),live:t.getAttribute('aria-live')};
                    }""")
                    if error_state['dock']['top'] - error_state['sheet']['bottom'] < error_state['toast']['height'] + 20:
                        assert error_state['hidden'] and error_state['toast']['width'] <= 1, error_state
                    else:
                        assert not error_state['hidden'], error_state
                        assert error_state['toast']['top'] >= error_state['sheet']['bottom'] + 7, error_state
                        assert error_state['toast']['bottom'] <= error_state['dock']['top'] - 7, error_state
                    assert error_state['role'] == 'alert' and error_state['live'] == 'assertive', error_state
                    assert not errors, errors
                    page.screenshot(path=str(OUT / f'self-found-studio-toast-v2-error-{width}-round{round_number}.png'), full_page=True)
                    results.append({'round': round_number, **measurements, 'available_gap_px': round(available_gap, 1), 'enough_gap': enough_gap, 'error_announcement': error_announcement, 'error_layout': error_state, 'page_errors': errors})
                    context.close()
                    compact_context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=True, has_touch=True)
                    compact_page = compact_context.new_page()
                    compact_errors = []
                    compact_page.on('pageerror', lambda error: compact_errors.append(str(error)))
                    compact_page.goto(base + '/studio', wait_until='domcontentloaded')
                    compact_page.locator('#studio-file-input').set_input_files(str(compact_pdf_path))
                    compact_page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
                    compact_page.wait_for_selector('.toast-notice[role="status"]', timeout=5000)
                    compact_page.wait_for_timeout(100)
                    compact = compact_page.evaluate("""() => {
                      const rect=s=>{const e=document.querySelector(s);const r=e.getBoundingClientRect();return {top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
                      const t=document.querySelector('.toast-notice');return {toast:rect('.toast-notice'),canvas:rect('#pdf-canvas'),sheet:rect('.studio-page-sheet'),dock:rect('#studio-mobile-dock'),hidden:t.classList.contains('toast-visually-hidden'),role:t.getAttribute('role')};
                    }""")
                    assert not compact['hidden'] and compact['role'] == 'status', compact
                    assert compact['toast']['top'] >= compact['sheet']['bottom'] + 3, compact
                    assert compact['toast']['bottom'] <= compact['dock']['top'] - 7, compact
                    compact_page.evaluate("showToast('Landscape error announcement', 'error', 1000)")
                    compact_page.wait_for_timeout(100)
                    compact_error = compact_page.evaluate("""() => {const r=s=>{const b=document.querySelector(s).getBoundingClientRect();return {top:b.top,bottom:b.bottom,width:b.width,height:b.height}};const t=document.querySelector('.toast-notice');return {toast:r('.toast-notice'),sheet:r('.studio-page-sheet'),dock:r('#studio-mobile-dock'),hidden:t.classList.contains('toast-visually-hidden'),role:t.getAttribute('role'),live:t.getAttribute('aria-live')}}""")
                    assert not compact_error['hidden'] and compact_error['role'] == 'alert' and compact_error['live'] == 'assertive', compact_error
                    assert compact_error['toast']['top'] >= compact_error['sheet']['bottom'] + 7, compact_error
                    assert compact_error['toast']['bottom'] <= compact_error['dock']['top'] - 7, compact_error
                    assert not compact_errors, compact_errors
                    compact_page.screenshot(path=str(OUT / f'self-found-studio-toast-v2-landscape-{width}-round{round_number}.png'), full_page=True)
                    results.append({'round': round_number, 'viewport': {'width': width, 'height': height}, 'landscape': compact, 'landscape_error': compact_error, 'page_errors': compact_errors})
                    compact_context.close()
            browser.close()
        output = {'rounds': results}
        (OUT / 'browser-self-found-studio-toast-v2.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
        print(json.dumps(output, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=10)
