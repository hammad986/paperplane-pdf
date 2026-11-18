from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id54-') as temp:
    app, base, _ = helper.start_server(Path(temp) / 'data')
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
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                observed = []
                for path, expected in (('/tools/merge', '/merge-pdf'), ('/plans', '/pricing'), ('/pricing', '/pricing')):
                    response = page.goto(base + path, wait_until='domcontentloaded')
                    page.wait_for_timeout(100)
                    final_path = page.evaluate('location.pathname')
                    title = page.title()
                    assert response and response.status == 200, (path, response.status if response else None)
                    assert final_path == expected, (path, final_path)
                    observed.append({'path': path, 'status': response.status, 'final_path': final_path, 'title': title})
                    if path == '/pricing':
                        page.wait_for_function("document.querySelectorAll('.pricing-tier-card[data-plan-tier]').length === 4")
                        cards = page.locator('.pricing-tier-card[data-plan-tier]').count()
                        assert cards == 4, cards
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id54-pricing-round{number}.png'))
                rounds.append({'round': number, 'routes': observed, 'pricing_cards': 4, 'page_errors': errors})
                page.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id54-legacy-routes.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
