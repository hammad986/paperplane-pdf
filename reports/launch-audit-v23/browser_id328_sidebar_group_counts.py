from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

EXPECTED = {'Organize': ('organize', 7), 'Optimize': ('optimize', 3), 'Convert': ('convert', 12),
            'Edit': ('edit', 8), 'Security': ('security', 6), 'AI': ('ai', 1), 'Photo': ('photo', 4)}

with TemporaryDirectory(prefix='paperplane-id328-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
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
            for width, height in ((1920, 1080),):
                context = browser.new_context(viewport={'width': width, 'height': height})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/tool-desk', wait_until='domcontentloaded')
                page.locator('#tool-desk-tools-catalog .home-cat-section').first.wait_for(state='attached', timeout=30000)
                page.wait_for_function("document.querySelectorAll('.nav-category-tab .nav-cat-badge').length >= 7")
                checks = []
                for label, (directory_category, expected_count) in EXPECTED.items():
                    tab = page.locator(f'.nav-category-tab[data-category="{label}"]')
                    badge = int(tab.locator('.nav-cat-badge').inner_text())
                    assert badge == expected_count, {'label': label, 'badge': badge, 'expected': expected_count}
                    tab.click()
                    if label == 'Photo':
                        page.locator('#tool-desk-directory-filters [data-desk-category="photo"]').wait_for(state='visible')
                    actual_sidebar_count = page.locator('#sidebar-tools-container .sidebar-tool-item').count()
                    assert actual_sidebar_count == expected_count, {'label': label, 'sidebar': actual_sidebar_count}
                    pill = page.locator(f'#tool-desk-directory-filters [data-desk-category="{directory_category}"]')
                    if pill.is_visible():
                        pill.click()
                        page.wait_for_function("document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card').length > 0")
                    directory_count = page.locator(f'#tool-desk-tools-catalog .home-cat-section[data-cat="{directory_category}"] .home-tool-card').count()
                    assert directory_count == expected_count, {'label': label, 'directory': directory_count}
                    checks.append({'label': label, 'badge': badge, 'sidebar_tools': actual_sidebar_count, 'directory_tools': directory_count})
                    print(f"checked {width}px: {label} {badge}", flush=True)
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id328-sidebar-groups-{width}.png'), full_page=True)
                rounds.append({'viewport': [width, height], 'checks': checks, 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id328-sidebar-group-counts.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
