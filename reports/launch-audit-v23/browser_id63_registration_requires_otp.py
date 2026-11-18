from pathlib import Path
from tempfile import TemporaryDirectory
import json, secrets, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id63-') as temp:
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
                email = f'id63-{number}-{secrets.token_hex(4)}@example.invalid'
                page.route('**/api/auth/register', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'status':'otp_required','email':email,'purpose':'signup','message':'Verification code sent.'})))
                page.goto(base + '/', wait_until='domcontentloaded')
                page.evaluate("window.openAuthModal('', 'register')")
                page.locator('#auth-email').fill(email)
                page.locator('#auth-password').fill('TestingPassword!234')
                page.locator('#auth-confirm-password').fill('TestingPassword!234')
                with page.expect_response(lambda response: response.url.endswith('/api/auth/register')) as response_event:
                    page.locator('#auth-submit-btn').click()
                response = response_event.value
                body = response.json()
                assert response.status == 200 and body.get('status') == 'otp_required', (response.status, body)
                assert 'token' not in body, body
                page.locator('#auth-otp-pane').wait_for(state='visible')
                auth_state = page.evaluate("""body => ({
                  otpPaneVisible: !document.querySelector('#auth-otp-pane').hidden,
                  tokenInResponse: Object.hasOwn(body, 'token'),
                  storedToken: localStorage.getItem('paperplane_token'),
                  authCookie: document.cookie.split(';').map(x=>x.trim()).some(x=>x.startsWith('paperplane_token=')),
                  confirmationEmail: document.querySelector('#auth-otp-email-display').textContent
                })""", body)
                assert auth_state['storedToken'] is None and not auth_state['authCookie']
                assert auth_state['confirmationEmail'] == email
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id63-register-otp-round{number}.png'))
                rounds.append({'round':number,'http_status':response.status,'response_status':body['status'],'auth_state':auth_state,'page_errors':errors})
                page.close()
            browser.close()
        result = {'rounds':rounds}
        (OUT / 'browser-id63-registration-requires-otp.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
