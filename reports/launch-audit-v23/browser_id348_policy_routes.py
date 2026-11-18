from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id348-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        routes = {
            '/privacy': ('AI provider configured for this deployment', 'Draft — owner review required'),
            '/terms': ('Cashfree', 'refund'),
            '/refund': ('DRAFT', 'support'),
            '/contact': ('response expectation', 'support@paperplane.qd.je'),
        }
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                results = []
                for route, markers in routes.items():
                    response = page.goto(base + route, wait_until='domcontentloaded')
                    body = page.locator('body').inner_text().lower()
                    assert response.status == 200
                    assert all(marker.lower() in body for marker in markers), (route, markers)
                    results.append({'route': route, 'status': response.status, 'title': page.title(), 'markers_present': list(markers)})
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id348-policy-round{number}.png'), full_page=True)
                rounds.append({'round': number, 'routes': results, 'page_errors': errors})
                page.close()
            browser.close()
        result = {'rounds': rounds, 'owner_review_required': ['confirm AI provider name and data retention/training terms', 'confirm operator identity and refund terms', 'verify support mailbox is monitored and response expectations']}
        (OUT / 'browser-id348-policy-routes.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
