from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id60-') as temp:
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
                email = f'id60-round{number}@example.invalid'
                page.route('**/api/auth/register', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'status':'otp_required','email':email,'purpose':'signup','message':'Verification code sent.'})))
                page.route('**/api/auth/resend-otp', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'status':'success','message':'A new verification code has been sent. Any previous code is now invalid; use the latest code.'})))
                page.goto(base + '/', wait_until='domcontentloaded')
                page.evaluate("window.openAuthModal('', 'register')")
                page.locator('#auth-email').fill(email)
                page.locator('#auth-password').fill('TestingPassword!234')
                page.locator('#auth-confirm-password').fill('TestingPassword!234')
                page.locator('#auth-submit-btn').click()
                page.locator('#auth-otp-pane').wait_for(state='visible')
                page.evaluate('startOtpCountdown(0)')
                page.locator('#btn-resend-otp').wait_for(state='visible', timeout=3000)
                page.locator('#auth-otp-code').fill('123456')
                page.locator('#btn-resend-otp').click()
                page.get_by_text('A new verification code has been sent. Any previous code is now invalid; use the latest code.', exact=True).wait_for(state='visible', timeout=5000)
                assert page.locator('#auth-otp-code').input_value() == ''
                assert page.locator('#auth-otp-pane').is_visible()
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id60-signup-resend-round{number}.png'))
                rounds.append({'round':number,'otp_pane_visible':True,'latest_code_notice_visible':True,'otp_input_cleared':True,'page_errors':errors})
                page.close()
            browser.close()
        result = {'rounds': rounds, 'resend_response_intercepted_for_browser_ui': True}
        (OUT / 'browser-id60-signup-resend-notice.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
