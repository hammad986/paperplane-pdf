from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id44-46-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2): break
            except OSError: time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            results = []
            for width in (390, 1366):
                page = browser.new_page(viewport={'width': width, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/ai-intelligence', wait_until='domcontentloaded')
                page.wait_for_selector('#view-ai-studio:not([hidden])')
                ai_text = page.locator('#view-ai-studio').inner_text()
                obsolete_ai_banner = 'Your AI PDF and full chat history save in this browser' in ai_text
                page.goto(base + '/tool-desk', wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('#quota-text')?.textContent.trim() !== 'Checking usage…'")
                sidebar_quota = page.locator('#quota-container').inner_text()
                page.goto(base + '/settings', wait_until='domcontentloaded')
                page.wait_for_selector('#settings-quota-description', state='attached')
                page.evaluate("document.querySelector('#settings-modal')?.classList.add('open')")
                page.wait_for_function("!document.querySelector('#settings-quota-description').textContent.includes('%%')")
                settings_quota = page.locator('#settings-quota-description').inner_text()
                results.append({
                    'width': width,
                    'obsolete_ai_banner_visible': obsolete_ai_banner,
                    'ai_workspace_has_no_obsolete_banner': not obsolete_ai_banner,
                    'sidebar_quota_text': sidebar_quota,
                    'settings_quota_description': settings_quota,
                    'quota_copy_is_not_contradictory': 'Unlimited · 500 MB · 100 files' not in sidebar_quota + settings_quota,
                    'page_errors': errors,
                })
                page.screenshot(path=str(OUT / f'id44-46-{width}.png'))
                assert not obsolete_ai_banner
                assert results[-1]['quota_copy_is_not_contradictory']
                assert 'operations per day' in settings_quota and 'files up to' in settings_quota
                assert not errors
                page.close()
            result = {'rounds': results}
            (OUT / 'browser-id44-46-ai-quota-copy.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, indent=2))
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
