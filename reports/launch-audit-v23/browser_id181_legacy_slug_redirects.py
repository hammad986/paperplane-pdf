from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

EXPECTED = {
    '/metadata': ('/pdf-metadata', '/pdf-metadata'),
    '/photo-compress': ('/compress-image-online', '/compress-image-online'),
    '/compress-photos': ('/compress-image-online', '/compress-image-online'),
    '/ai-chat': ('/ai-pdf-chat', '/ai-intelligence'),
    '/chat-pdf': ('/ai-pdf-chat', '/ai-intelligence'),
    '/pdf-chat': ('/ai-pdf-chat', '/ai-intelligence'),
}

with TemporaryDirectory(prefix='paperplane-id181-') as temp:
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
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                checks = []
                for old, (redirect_target, final_path) in EXPECTED.items():
                    hop = context.request.get(base + old, max_redirects=0)
                    assert hop.status == 301, (old, hop.status)
                    assert hop.headers.get('location') == redirect_target, (old, hop.headers.get('location'), redirect_target)
                    response = page.goto(base + old, wait_until='domcontentloaded')
                    assert response and response.status == 200, (old, response.status if response else None)
                    assert page.url == base + final_path, (old, page.url, final_path)
                    assert page.locator('body').inner_text().strip(), old
                    checks.append({'old': old, 'redirect_status': hop.status, 'location': hop.headers['location'], 'final_status': response.status, 'final_url': page.url})
                assert not errors, errors
                rounds.append({'round': number, 'checks': checks, 'page_errors': errors})
                context.close()
            browser.close()

        result = {'rounds': rounds}
        (OUT / 'browser-id181-legacy-slug-redirects.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
