from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id320-') as temp:
    root = Path(temp)
    pdf = root / 'clear-studio.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), 'Studio clear storage regression fixture.')
        doc.save(pdf)
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
            context = browser.new_context(viewport={'width': 1366, 'height': 900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/studio', wait_until='domcontentloaded')
            page.locator('#studio-file-input').set_input_files(str(pdf))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=20000)
            page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=15000)
            page.evaluate("window.confirmAction = async () => true")
            page.locator('#studio-clear-pdf-btn').click()
            page.get_by_text('Studio PDF cleared from this browser.', exact=True).wait_for(timeout=10000)
            assert page.locator('#studio-canvas-area .studio-empty-state').is_visible()
            assert not page.get_by_text('Close other Paperplane tabs and try again', exact=True).count()
            page.screenshot(path=str(OUT / 'id320-clear-studio.png'))
            result = {
                'clear_with_no_other_tab_succeeded': True,
                'other_tab_message_absent': True,
                'page_errors': errors,
            }
            (OUT / 'browser-id320-clear-studio.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, indent=2))
            assert result['clear_with_no_other_tab_succeeded'] and result['other_tab_message_absent'] and not errors
            context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
