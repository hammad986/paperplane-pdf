from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-id40-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            page=browser.new_page(viewport={'width':1366,'height':900})
            errors=[]
            page.on('pageerror',lambda error:errors.append(str(error)))
            expected = ['Free', 'Exam Pass', 'Student & Educator', 'All-In-One Pro & Developer']
            rounds=[]
            for round_number in (1, 2):
                page.goto(base+'/pricing',wait_until='domcontentloaded')
                page.wait_for_selector('#view-pricing:not([hidden])')
                page.wait_for_function("document.querySelectorAll('.pricing-tier-card .tier-title').length >= 4")
                names=[name.strip() for name in page.locator('.pricing-tier-card .tier-title').all_text_contents()]
                rounds.append({'round': round_number, 'plan_names': names, 'all_names_match_catalog': names == expected})
                page.screenshot(path=str(OUT/f'id40-pricing-plan-names-round{round_number}.png'))
            result={'expected_catalog_names': expected, 'rounds': rounds,
                    'plan_names': rounds[-1]['plan_names'],
                    'student_educator_canonical': 'Student & Educator' in rounds[-1]['plan_names'],
                    'student_pro_variant_absent': 'Student Pro' not in rounds[-1]['plan_names'],
                    'page_errors':errors}
            (OUT/'browser-id40-plan-names.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
            print(json.dumps(result,indent=2))
            assert all(item['all_names_match_catalog'] for item in rounds)
            assert result['student_educator_canonical'] and result['student_pro_variant_absent'] and not errors
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
