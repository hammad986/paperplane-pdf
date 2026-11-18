from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-274-275-') as temp:
    app, base, identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        runs = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for n in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))

                # Both entry points must expose the same single Cloud Import dialog.
                page.goto(base + '/merge-pdf', wait_until='domcontentloaded')
                page.locator('#topbar-cloud-btn').click()
                page.wait_for_function("!document.querySelector('#cloud-modal').hidden")
                topbar_dialog = page.locator('#cloud-modal').inner_text()
                topbar_controls = page.locator('#cloud-modal input, #cloud-modal button').evaluate_all(
                    "els => els.map(e => [e.tagName, e.id, e.getAttribute('aria-label'), e.textContent.trim()])")
                assert page.locator('#cloud-modal:visible').count() == 1
                page.locator('#close-cloud-modal').click()
                page.locator('#cloud-drop-btn').click()
                page.wait_for_function("!document.querySelector('#cloud-modal').hidden")
                drop_dialog = page.locator('#cloud-modal').inner_text()
                drop_controls = page.locator('#cloud-modal input, #cloud-modal button').evaluate_all(
                    "els => els.map(e => [e.tagName, e.id, e.getAttribute('aria-label'), e.textContent.trim()])")
                assert topbar_dialog == drop_dialog and topbar_controls == drop_controls
                assert page.locator('#cloud-modal:visible').count() == 1
                assert page.locator('#cloud-url').count() == 1 and page.locator('#cloud-submit-btn').count() == 1
                page.locator('#close-cloud-modal').click()

                # One label and one unambiguous checked state across tool and settings surfaces.
                if not page.locator('#client-privacy-toggle').is_checked():
                    page.locator('label:has(#client-privacy-toggle)').click()
                page.wait_for_function("state.clientSideMode === true")
                local = page.evaluate("""() => ({
                    label: document.querySelector('#privacy-mode-label').textContent.trim(),
                    checked: document.querySelector('#client-privacy-toggle').checked,
                    aria: document.querySelector('#client-privacy-toggle').getAttribute('aria-label'),
                    support: document.querySelector('#privacy-mode-support').textContent,
                    engine: document.querySelector('#engine-status-text')?.textContent.trim() || null
                })""")
                assert local['label'] == 'Use browser processing' and local['checked']
                assert 'Browser processing is on' in local['aria'] and 'runs in your browser' in local['support']
                assert local['engine'] in (None, 'Browser processing'), local

                page.locator('label:has(#client-privacy-toggle)').click()
                page.wait_for_function("state.clientSideMode === false")
                server = page.evaluate("""() => ({
                    checked: document.querySelector('#client-privacy-toggle').checked,
                    aria: document.querySelector('#client-privacy-toggle').getAttribute('aria-label'),
                    support: document.querySelector('#privacy-mode-support').textContent,
                    engine: document.querySelector('#engine-status-text')?.textContent.trim() || null
                })""")
                assert not server['checked'] and 'Browser processing is off' in server['aria']
                assert 'temporary server processing' in server['support']
                assert server['engine'] in (None, 'Temporary server processing'), server

                page.locator('#sidebar-settings-gear-btn').click()
                page.wait_for_function("!document.querySelector('#settings-modal').hidden")
                page.locator('#settings-tab-btn-privacy').click()
                settings = page.evaluate("""() => ({
                    heading: document.querySelector('.privacy-settings-card strong').textContent.trim(),
                    checked: document.querySelector('#settings-client-privacy-toggle').checked,
                    aria: document.querySelector('#settings-client-privacy-toggle').getAttribute('aria-label'),
                    support: document.querySelector('#settings-client-privacy-support').textContent
                })""")
                assert settings['heading'] == 'Browser processing' and not settings['checked']
                assert settings['aria'] == 'Prefer browser processing for supported tools'
                assert 'Temporary server processing is preferred' in settings['support']
                if not page.locator('#settings-client-privacy-toggle').is_checked():
                    page.locator('label:has(#settings-client-privacy-toggle)').click()
                page.wait_for_function("localStorage.getItem(PROCESSING_MODE_KEY) === 'local'")
                assert page.locator('#settings-client-privacy-toggle').is_checked()

                page.goto(base + '/merge-pdf', wait_until='domcontentloaded')
                page.wait_for_function("state.clientSideMode === true")
                assert page.locator('#client-privacy-toggle').is_checked()
                assert 'runs in your browser' in page.locator('#privacy-mode-support').inner_text()

                # Photo tools always run in browser; the checked control must say so and be unavailable to turn off.
                page.goto(base + '/compress-photo', wait_until='domcontentloaded')
                page.wait_for_function("state.clientSideMode === true")
                photo = page.evaluate("""() => ({
                    label: document.querySelector('#privacy-mode-label').textContent.trim(),
                    checked: document.querySelector('#client-privacy-toggle').checked,
                    disabled: document.querySelector('#client-privacy-toggle').disabled,
                    support: document.querySelector('#privacy-mode-support').textContent,
                    engine: document.querySelector('#engine-status-text')?.textContent.trim() || null
                })""")
                assert photo['label'] == 'Use browser processing' and photo['checked'] and photo['disabled']
                assert 'runs in your browser' in photo['support'] and photo['engine'] in (None, 'Browser processing')
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id274-275-round{n}.png'))
                runs.append({'round': n, 'cloud': {'topbar': topbar_controls, 'dropzone': drop_controls,
                    'single_visible_dialog': True}, 'browser_mode': local, 'server_mode': server,
                    'settings': settings, 'photo_mode': photo, 'page_errors': errors})
                page.close()
            browser.close()
        result = {'runs': runs}
        (OUT / 'browser-ids274-275.json').write_text(json.dumps(result, indent=2))
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
