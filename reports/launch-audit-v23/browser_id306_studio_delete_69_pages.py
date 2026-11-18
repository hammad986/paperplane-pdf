from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper


def create_pdf(path):
    with fitz.open() as doc:
        for number in range(1, 70):
            page = doc.new_page()
            page.insert_text((72, 72), f'Page marker {number:02d} — Studio delete latency audit.')
        doc.save(path)


with TemporaryDirectory(prefix='paperplane-id306-') as temp:
    root = Path(temp)
    fixture = root / 'studio-delete-69-pages.pdf'
    create_pdf(fixture)
    app, base, _identity = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for round_no in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/studio', wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=30000)
                page.evaluate('window.confirmAction = async () => true')
                started = time.monotonic()
                page.locator('#editor-delete-page-btn').click()
                toast = page.locator('.toast-notice')
                toast.wait_for(state='visible', timeout=3000)
                progress_text = toast.inner_text()
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '68'", timeout=30000)
                elapsed = round(time.monotonic() - started, 3)
                final_state = page.locator('#page-total-indicator').inner_text()
                assert final_state == '68', final_state
                assert 'Deleting 1 page(s)' in progress_text, progress_text
                assert not errors, errors
                results.append({
                    'round': round_no,
                    'input_pages': 69,
                    'output_pages': int(final_state),
                    'delete_and_reload_seconds': elapsed,
                    'progress_toast_text': progress_text,
                    'page_errors': errors,
                })
                page.screenshot(path=str(OUT / f'id306-delete-69-round{round_no}.png'))
                page.close()
            browser.close()
        (OUT / 'browser-id306-studio-delete-69-pages.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
