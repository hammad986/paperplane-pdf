from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id344-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
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
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            page_errors, console_errors, auth_responses = [], [], []
            page.on('pageerror', lambda error: page_errors.append(str(error)))
            page.on('console', lambda message: console_errors.append(message.text) if message.type == 'error' else None)
            page.on('response', lambda response: auth_responses.append({'status': response.status, 'url': response.url}) if response.url.endswith('/api/auth/me') else None)
            routes = ['/tool-desk', '/merge-pdf', '/settings', '/faq', '/history']
            badges = []
            for route in routes:
                page.goto(base + route, wait_until='domcontentloaded')
                page.wait_for_function("!document.body.classList.contains('auth-pending')", timeout=10000)
                if route == '/merge-pdf':
                    page.wait_for_function("!document.querySelector('#tool-tier-badge')?.textContent.includes('Checking plan')", timeout=10000)
                    badge = page.locator('#tool-tier-badge')
                    page.evaluate("document.body.classList.add('auth-pending')")
                    pending_visibility = badge.evaluate("el => getComputedStyle(el).visibility")
                    page.evaluate("document.body.classList.remove('auth-pending')")
                    badges.append({'route': route, 'text': badge.text_content(), 'hidden_during_auth_check': pending_visibility == 'hidden'})
                else:
                    badges.append(None)
            result = {
                'routes_checked': routes,
                'guest_auth_statuses': [entry['status'] for entry in auth_responses],
                'guest_plan_badges': badges,
                'auth_401_count': sum(entry['status'] == 401 for entry in auth_responses),
                'page_errors': page_errors,
                'console_errors': console_errors,
            }
            (OUT / 'browser-id344-guest-auth.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, indent=2))
            assert len(auth_responses) >= len(routes)
            assert all(entry['status'] == 200 for entry in auth_responses)
            assert all(badge is None or (not badge['text'].lower().startswith('checking plan') and badge['hidden_during_auth_check']) for badge in badges)
            assert result['auth_401_count'] == 0 and not page_errors and not console_errors
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
