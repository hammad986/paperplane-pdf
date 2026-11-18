from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id57-59-') as temp:
    root = Path(temp)
    pdf_path = root / 'pages.pdf'
    with fitz.open() as doc:
        for number in range(1, 4):
            doc.new_page().insert_text((72, 72), f'ID 57–59 page {number}')
        doc.save(pdf_path)
    app, base, _ = helper.start_server(root / 'data')
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
            for round_number in (1, 2):
                for width in (1366, 1104, 820, 390):
                    height = 900 if width != 390 else 844
                    context = browser.new_context(viewport={'width': width, 'height': height})
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/studio', wait_until='domcontentloaded')
                    page.locator('#studio-file-input').set_input_files(str(pdf_path))
                    page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
                    page.locator('#btn-more-tools-trigger').click()
                    page.locator('#studio-more-dropdown').wait_for(state='visible')
                    menu = page.locator('#studio-more-dropdown').bounding_box()
                    assert menu and menu['x'] >= 0 and menu['x'] + menu['width'] <= width, (width, menu)
                    assert page.locator('#studio-more-dropdown .studio-dropdown-item:visible').count() >= 5
                    menu_state = {'visible': True, 'rect': menu, 'item_count': page.locator('#studio-more-dropdown .studio-dropdown-item:visible').count()}
                    page.keyboard.press('Escape')
                    page.wait_for_function("document.querySelector('#studio-more-dropdown')?.hidden === true")
                    if width > 900:
                        panel = page.locator('#studio-thumbnails-bar')
                        before = panel.bounding_box()
                        page.locator('#studio-pages-toggle-btn').click()
                        collapsed = page.locator('#studio-pages-toggle-btn').get_attribute('aria-expanded') == 'false'
                        page.locator('#studio-pages-toggle-btn').click()
                        after = panel.bounding_box()
                        assert collapsed and page.locator('#studio-pages-toggle-btn').get_attribute('aria-expanded') == 'true'
                        sidebar = {'before': before, 'collapsed': collapsed, 'restored': after}
                    else:
                        page.locator('#studio-mobile-pages-btn').click()
                        opened = page.locator('#app-shell').evaluate("e => e.classList.contains('studio-pages-open')")
                        panel = page.locator('#studio-thumbnails-bar').bounding_box()
                        page.locator('#studio-mobile-pages-btn').click()
                        closed = not page.locator('#app-shell').evaluate("e => e.classList.contains('studio-pages-open')")
                        assert opened and closed
                        sidebar = {'tablet_or_phone_drawer_opened': opened, 'panel_rect': panel, 'closed': closed}
                    assert not errors, errors
                    page.screenshot(path=str(OUT / f'id57-59-studio-{width}-round{round_number}.png'))
                    rounds.append({'round': round_number, 'viewport': width, 'more_tools_menu': menu_state, 'pages_panel': sidebar, 'page_errors': errors})
                    context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id57-58-59-studio-navigation.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
