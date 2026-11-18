from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id43-') as temp:
    root = Path(temp)
    pdf = root / 'slow-delete-69-pages.pdf'
    with fitz.open() as doc:
        for page_number in range(1, 11):
            page = doc.new_page()
            page.insert_text((72, 72), f'Undo delay fixture page {page_number} with unique content marker {page_number}.')
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
            page_errors = []
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            delayed_seconds = 12
            page.goto(base + '/studio', wait_until='domcontentloaded')
            page.locator('#studio-file-input').set_input_files(str(pdf))
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=20000)
            page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
            page.evaluate("""(delayMs) => {
              const organizer = window.PaperplanePageOrganizer;
              const original = organizer._sendPageMutation.bind(organizer);
              organizer._sendPageMutation = async (endpoint, fields) => {
                const file = await original(endpoint, fields);
                if (endpoint === '/api/studio/page/delete') await new Promise(resolve => setTimeout(resolve, delayMs));
                return file;
              };
            }""", delayed_seconds * 1000)
            page.evaluate('window.confirmAction = async () => true')
            started = time.monotonic()
            page.locator('#editor-delete-page-btn').click()
            page.get_by_text('Deleting 1 page(s)…', exact=True).wait_for(timeout=5000)
            page.locator('#studio-undo-banner').wait_for(state='hidden', timeout=2000)
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '9'", timeout=60000)
            mutation_elapsed = time.monotonic() - started
            banner = page.locator('#studio-undo-banner')
            page.wait_for_function("document.querySelector('#studio-undo-banner')?.hidden === false && document.querySelector('#studio-undo-banner button')?.disabled === false", timeout=10000)
            time.sleep(12)
            undo_still_available = banner.is_visible() and banner.locator('button').is_enabled()
            banner_text = banner.text_content()
            page.screenshot(path=str(OUT / 'id43-slow-delete-undo.png'))
            banner.locator('button').click()
            page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=20000)
            undo_restored_pages = int(page.locator('#page-total-indicator').text_content())
            result = {
                'input_pages': 10,
                'output_pages': 9,
                'controlled_response_delay_seconds': delayed_seconds,
                'mutation_elapsed_seconds': round(mutation_elapsed, 2),
                'undo_visible_and_enabled_after_additional_12_seconds': undo_still_available,
                'undo_banner_text': banner_text,
                'undo_restored_original_page_count': undo_restored_pages,
                'page_errors': page_errors,
            }
            (OUT / 'browser-id43-slow-delete-undo.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, indent=2))
            assert result['output_pages'] == 9 and mutation_elapsed >= delayed_seconds
            assert undo_still_available and mutation_elapsed >= delayed_seconds
            assert undo_restored_pages == 10 and not page_errors
            context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
