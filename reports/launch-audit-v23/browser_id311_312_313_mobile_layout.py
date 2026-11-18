from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix='paperplane-mobile-r12-') as temp:
    root = Path(temp)
    fixture = root / 'mobile-layout.pdf'
    with fitz.open() as pdf:
        pdf.new_page().insert_text((72, 72), 'Mobile layout regression fixture')
        pdf.save(fixture)
    app, base, _identity = helper.start_server(root / 'data')
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
            for number in (1, 2):
                page = browser.new_page(viewport={'width': 820, 'height': 900}, is_mobile=True, has_touch=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/', wait_until='domcontentloaded')
                page.evaluate("openSettingsModal('account')")
                settings = page.evaluate("""() => {
                  const modal = document.querySelector('.settings-modal-card');
                  const rect = modal.getBoundingClientRect();
                  return {left: rect.left, right: rect.right, width: rect.width, viewport: innerWidth, docWidth: document.documentElement.scrollWidth};
                }""")
                assert settings['left'] >= 0 and settings['right'] <= 821 and settings['docWidth'] <= 821, settings
                page.evaluate("document.querySelector('#settings-modal')?.classList.remove('open'); document.querySelector('#settings-modal').hidden = true")
                page.set_viewport_size({'width': 820, 'height': 1180})
                page.goto(base + '/studio', wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(fixture))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=20000)
                studio = page.evaluate("""() => {
                  const c = document.querySelector('#pdf-canvas').getBoundingClientRect();
                  const t = document.querySelector('.studio-toolbar').getBoundingClientRect();
                  return {canvasTop:c.top, canvasBottom:c.bottom, toolbarBottom:t.bottom, docWidth:document.documentElement.scrollWidth, viewport:innerWidth, canvasVisible:c.bottom>0 && c.top<innerHeight};
                }""")
                assert studio['canvasVisible'] and studio['docWidth'] <= 821, studio
                page.set_viewport_size({'width': 390, 'height': 844})
                page.locator('#btn-more-tools-trigger').click()
                page.locator('#studio-sign-btn').click()
                page.locator('#digital-sign-modal').wait_for(state='visible')
                signature = page.evaluate("""() => {
                  const modal = document.querySelector('#digital-sign-modal');
                  const card = modal.querySelector('.modal-card, .digital-sign-modal-card, [class*=card]') || modal.firstElementChild;
                  const r = card.getBoundingClientRect();
                  return {left:r.left,right:r.right,width:r.width,viewport:innerWidth,docWidth:document.documentElement.scrollWidth,visible:!!(r.width&&r.height)};
                }""")
                assert signature['visible'] and signature['left'] >= 0 and signature['right'] <= 391 and signature['docWidth'] <= 391, signature
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id311-313-mobile-layout-round{number}.png'))
                rounds.append({'round':number,'settings_820':settings,'studio_820':studio,'signature_390':signature,'page_errors':errors})
                page.close()
            browser.close()
        result={'rounds':rounds}
        (OUT/'browser-id311-312-313-mobile-layout.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
