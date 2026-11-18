from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id276-') as temp:
    results = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel='chrome', headless=True)
        for n in (1, 2):
            app, base, identity = helper.start_server(Path(temp) / f'db{n}')
            try:
                port = int(base.rsplit(':', 1)[1])
                for _ in range(100):
                    try:
                        with socket.create_connection(('127.0.0.1', port), timeout=.2): break
                    except OSError: time.sleep(.15)
                email, token = identity['accounts'][0]
                context = browser.new_context(viewport={'width': 1366, 'height': 900})
                context.add_cookies([{'name': 'paperplane_token', 'value': token, 'url': base, 'httpOnly': True}])
                page = context.new_page(); errors=[]
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(base + '/tool-desk', wait_until='domcontentloaded')
                page.wait_for_function('window.state?.user?.user_id')
                page.locator('#sidebar-settings-gear-btn').click()
                page.wait_for_function("!document.querySelector('#settings-modal').hidden")
                data = page.evaluate("""() => ({
                    authenticated: !!state.user?.user_id,
                    name: document.querySelector('#settings-user-email').textContent.trim(),
                    badge: document.querySelector('#settings-user-badge').textContent.trim(),
                    guestActionsHidden: document.querySelector('#settings-guest-actions').hidden,
                    userActionsVisible: !document.querySelector('#settings-user-actions').hidden,
                    guestCopy: document.querySelector('#settings-guest-actions').textContent.trim(),
                    pageErrors: []
                })""")
                assert data['authenticated'] and data['name'] == email
                assert data['guestActionsHidden'] and data['userActionsVisible']
                assert 'Guest Explorer' not in data['name'] and 'Sign in or create an account' not in data['guestCopy']
                assert not errors, errors
                data['pageErrors']=errors
                page.locator('#settings-signout-btn').click()
                page.wait_for_function('!window.state?.user?.user_id')
                page.locator('#sidebar-settings-gear-btn').click()
                page.wait_for_function("!document.querySelector('#settings-modal').hidden")
                restored=page.evaluate("""() => ({guestVisible:!document.querySelector('#settings-guest-actions').hidden,
                    guestCopy:document.querySelector('#settings-guest-actions').textContent,
                    signIn:!!document.querySelector('#settings-signin-btn'),register:!!document.querySelector('#settings-register-btn')})""")
                assert restored['guestVisible'] and 'Guest Explorer' not in restored['guestCopy']
                assert restored['signIn'] and restored['register'],restored
                data['signedOutGuestActions']=restored
                page.screenshot(path=str(OUT / f'id276-settings-round{n}.png'))
                results.append(data)
                context.close()
            finally:
                app.terminate(); app.wait(timeout=5)
        browser.close()
    out={'rounds': results}
    (OUT / 'browser-id276-guest-block.json').write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))
