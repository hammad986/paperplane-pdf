from pathlib import Path
import json
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = 'http://127.0.0.1:18501'

results = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    for round_no in (1, 2):
        context = browser.new_context(viewport={'width': 1366, 'height': 900})
        page = context.new_page()
        errors = []
        checkout_posts = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('request', lambda request: checkout_posts.append(request.url) if request.method == 'POST' and '/api/billing/checkout-session' in request.url else None)
        page.goto(BASE + '/', wait_until='networkidle', timeout=15000)
        page.locator('#topbar-upgrade-btn').click()
        page.locator('#student-cashfree-checkout-btn').wait_for(state='visible')
        page.locator('#student-cashfree-checkout-btn').click()
        page.wait_for_timeout(250)
        auth = page.locator('#auth-modal, .auth-modal, [role="dialog"]').filter(has_text='sign in or create an account').first
        auth_visible = auth.is_visible() if auth.count() else False
        auth_copy = auth.inner_text() if auth_visible else ''
        assert auth_visible, 'Guest checkout did not open account gate'
        assert 'sign in or create an account' in auth_copy.lower(), auth_copy
        assert not checkout_posts, f'Guest triggered checkout API: {checkout_posts}'
        assert not errors, errors
        results.append({'round': round_no, 'auth_gate_visible': auth_visible,
                        'account_required_copy': auth_copy, 'checkout_posts': checkout_posts,
                        'page_errors': errors})
        context.close()
    browser.close()

(OUT / 'browser-id29-guest-checkout-gate.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
