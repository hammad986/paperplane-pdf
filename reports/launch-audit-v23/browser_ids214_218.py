from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-ids214-218-') as temp:
    temp_path = Path(temp)
    pdf = temp_path / 'ai-restore.pdf'
    with fitz.open() as doc:
        for i in range(10):
            page = doc.new_page()
            page.insert_text((72, 72), f'ID 218 restore marker page {i + 1}')
        doc.save(pdf)
    app, base, _ = helper.start_server(temp_path / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2): break
            except OSError: time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            results = []
            for round_no in (1, 2):
                context = browser.new_context(viewport={'width': 390, 'height': 844})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda err: errors.append(str(err)))
                page.goto(base + '/tool-desk', wait_until='domcontentloaded')
                page.keyboard.press('Control+k')
                page.locator('#command-modal').wait_for(state='visible')
                palette = page.evaluate("""() => ({items:[...document.querySelectorAll('.command-item')].map(x=>({text:x.innerText,html:x.innerHTML})), count:document.querySelectorAll('.command-item').length})""")
                page.locator('#command-input').fill('api')
                no_api = page.locator('#command-results').inner_text()
                page.keyboard.press('Escape')
                page.goto(base + '/organize-pdf', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(pdf))
                page.wait_for_function("document.querySelectorAll('#organizer-order-grid .organizer-order-card').length===10", timeout=20000)
                organizer = page.evaluate("""() => [...document.querySelectorAll('#organizer-order-grid .organizer-order-card')].map(card=>{const label=card.querySelector('strong'), controls=card.querySelector('.organizer-order-move-controls'), a=label.getBoundingClientRect(),b=controls.getBoundingClientRect();return {label:label.textContent, labelRect:{x:a.x,y:a.y,w:a.width,h:a.height}, controlsRect:{x:b.x,y:b.y,w:b.width,h:b.height}, labelFits:label.scrollWidth<=label.clientWidth, overlaps:!(a.right<=b.left||a.left>=b.right||a.bottom<=b.top||a.top>=b.bottom)}})""")
                assert all(item['labelFits'] and not item['overlaps'] for item in organizer), organizer
                page.screenshot(path=str(OUT / f'id214-218-round{round_no}.png'), full_page=True)
                page.evaluate("sessionStorage.setItem('paperplane-last-local-document:guest', 'ai-restore.pdf')")
                page.reload(wait_until='domcontentloaded')
                page.wait_for_function("!document.body.classList.contains('auth-pending')",timeout=15000)
                page.wait_for_function("[...document.querySelectorAll('.toast-notice')].some(el=>el.innerText.includes('ai-restore.pdf was temporary and could not be restored'))",timeout=10000)
                reload_notice=page.locator('.toast-notice').all_inner_texts()
                result = {'round':round_no,'palette_count':palette['count'],'palette_has_api_badge':any('api' in item['html'].lower() for item in palette['items']),'api_search':no_api,'organizer':organizer,'reload_notice':reload_notice,'page_errors':errors}
                assert not result['palette_has_api_badge'] and 'No matching tools found' in no_api and not errors, result
                results.append(result)
                context.close()
            browser.close()
        output = {'rounds':results}
        (OUT / 'browser-ids214-218.json').write_text(json.dumps(output, indent=2), encoding='utf-8')
        print(json.dumps(output, indent=2))
    finally:
        app.terminate(); app.wait(timeout=5)
