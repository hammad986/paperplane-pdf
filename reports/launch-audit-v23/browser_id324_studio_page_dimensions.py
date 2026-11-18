from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id324-') as temp:
    root = Path(temp)
    source = root / 'letter-and-cropbox.pdf'
    with fitz.open() as document:
        letter = document.new_page(width=612, height=792)
        letter.insert_text((48, 60), 'US Letter media box page')
        cropped = document.new_page(width=612, height=792)
        cropped.insert_text((48, 60), 'Cropped page with a 540 by 720 point CropBox')
        cropped.set_cropbox(fitz.Rect(36, 36, 576, 756))
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
            for round_number in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/studio', wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(source))
                page.wait_for_function("document.querySelectorAll('#studio-page-stack .studio-page-sheet[data-pdf-page-width-pt]').length === 2", timeout=30000)
                page.wait_for_function("[...document.querySelectorAll('#studio-page-stack .studio-page-sheet')].every(slot => slot.querySelector('canvas')?.dataset.rendered === 'true')", timeout=30000)
                sizes = page.locator('#studio-page-stack .studio-page-sheet').evaluate_all("slots => slots.map(slot => ({page: Number(slot.dataset.page), width: Number(slot.dataset.pdfPageWidthPt), height: Number(slot.dataset.pdfPageHeightPt), label: slot.getAttribute('aria-label'), title: slot.title}))")
                assert sizes == [
                    {'page': 1, 'width': 612, 'height': 792, 'label': 'Page 1, 612 × 792 pt', 'title': '612 × 792 pt'},
                    {'page': 2, 'width': 540, 'height': 720, 'label': 'Page 2, 540 × 720 pt', 'title': '540 × 720 pt'},
                ], sizes
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id324-studio-dimensions-round{round_number}.png'))
                rounds.append({'round': round_number, 'sizes': sizes, 'correct_media_and_crop_boxes': True, 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id324-studio-page-dimensions.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
