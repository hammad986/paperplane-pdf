from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id346-') as temp:
    root = Path(temp)
    source = root / 'colored-searchable-source.pdf'
    with fitz.open() as document:
        page = document.new_page(width=612, height=792)
        page.draw_rect(fitz.Rect(40, 40, 570, 750), color=(0.75, 0.12, 0.04), fill=(0.95, 0.45, 0.1))
        page.insert_text((72, 110), 'RASTERIZATION SEARCHABILITY MARKER', fontsize=18, color=(0.05, 0.1, 0.8))
        document.save(source)
    app, base, _identity = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'server')")
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/convert-pdf-to-grayscale', wait_until='domcontentloaded')
                warning = page.locator('#options').inner_text().lower()
                assert 'rendered as images' in warning and 'text may lose searchability' in warning
                assert page.locator('#options a[href="/ocr-pdf"]').inner_text() == 'run OCR PDF'
                assert 'larger' in warning and 'compress pdf' in warning
                page.locator('#file-input').set_input_files(str(source))
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                with page.expect_download(timeout=30000) as event:
                    page.locator('#result-download-link').click()
                download = event.value
                output = root / f'grayscale-{number}.pdf'
                download.save_as(str(output))
                with fitz.open(output) as result:
                    assert result.page_count == 1
                    searchable_text = result[0].get_text().strip()
                    pixmap = result[0].get_pixmap(matrix=fitz.Matrix(.2, .2), alpha=False)
                    samples = pixmap.samples
                    grayscale_pixels = all(samples[index] == samples[index + 1] == samples[index + 2] for index in range(0, len(samples), 3))
                assert not searchable_text and grayscale_pixels
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id346-grayscale-round{number}.png'))
                rounds.append({'round': number, 'download_name': download.suggested_filename, 'page_count': 1, 'searchable_text_after_rasterization': bool(searchable_text), 'rendered_pixels_are_grayscale': grayscale_pixels, 'warning_visible_before_run': True, 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id346-grayscale-searchability-warning.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
