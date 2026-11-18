from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id326-') as temp:
    root = Path(temp)
    source = root / 'organizer-labels-12-pages.pdf'
    with fitz.open() as document:
        for number in range(1, 13):
            document.new_page().insert_text((72, 72), f'Organizer label source page {number}')
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
                context = browser.new_context(viewport={'width': 1920, 'height': 1080})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/organize-pdf', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(source))
                page.locator('.organizer-order-card').nth(11).wait_for(state='visible', timeout=30000)
                page.wait_for_function("[...document.querySelectorAll('.organizer-order-card strong')].every(label => label.offsetHeight <= 18)")
                metrics = page.locator('.organizer-order-card').evaluate_all("cards => cards.map(card => { const label = card.querySelector('strong'); const controls = card.querySelector('.organizer-order-move-controls'); const labelRect = label.getBoundingClientRect(); const controlRect = controls.getBoundingClientRect(); const cardRect = card.getBoundingClientRect(); return {text: label.textContent, labelHeight: labelRect.height, labelWidth: labelRect.width, labelRight: labelRect.right, controlsLeft: controlRect.left, cardRight: cardRect.right, labelFits: labelRect.right <= controlRect.left && labelRect.right <= cardRect.right}; })")
                assert len(metrics) == 12
                assert all(item['labelFits'] and item['labelHeight'] <= 18 for item in metrics), metrics
                assert metrics[-1]['text'] == 'Page 12'
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id326-labels-round{round_number}.png'), full_page=True)
                rounds.append({'round': round_number, 'viewport': [1920, 1080], 'card_count': len(metrics), 'all_labels_single_line_and_inside_controls': True, 'last_label': metrics[-1], 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id326-organizer-label-width.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
