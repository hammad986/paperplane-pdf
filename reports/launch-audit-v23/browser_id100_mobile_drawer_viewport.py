from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id100-') as temp:
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
            for n in (1, 2):
                page = browser.new_page(viewport={'width': 390, 'height': 500}, is_mobile=True, has_touch=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/', wait_until='domcontentloaded')
                page.locator('#mobile-menu-btn').click()
                sidebar = page.locator('#sidebar')
                page.wait_for_function("document.querySelector('#sidebar')?.classList.contains('mobile-open')")
                page.evaluate("document.querySelector('#sidebar').scrollTop=document.querySelector('#sidebar').scrollHeight")
                profile = page.locator('#sidebar-profile-card')
                gear = page.locator('#sidebar-settings-gear-btn')
                profile_box, gear_box = profile.bounding_box(), gear.bounding_box()
                assert profile.is_visible() and gear.is_visible() and profile_box and gear_box
                assert profile_box['y'] + profile_box['height'] <= 500 and gear_box['y'] + gear_box['height'] <= 500, {'profile': profile_box, 'gear': gear_box}
                gear.click()
                page.locator('#settings-modal:not([hidden])').wait_for(state='visible')
                assert not errors, errors
                rounds.append({'round': n, 'viewport': [390, 500], 'profile': profile_box, 'settings_gear': gear_box, 'settings_opened': True, 'page_errors': errors})
                page.close()
            browser.close()
        (OUT / 'browser-id100-mobile-drawer-viewport.json').write_text(json.dumps(rounds, indent=2), encoding='utf-8')
        print(json.dumps(rounds, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
