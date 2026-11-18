from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROUTES = [item['route'] for item in json.loads((OUT / 'route-layout-matrix.json').read_text(encoding='utf-8'))['copy_routes']]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id171-') as temp:
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
            context = browser.new_context(viewport={'width':1366,'height':900})
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            for number in (1,2):
                checks=[]
                for route in ROUTES:
                    response=page.goto(base+route,wait_until='domcontentloaded',timeout=20000)
                    assert response and response.status==200,(route,response.status if response else None)
                    footer=page.locator('footer.app-global-footer')
                    footer.wait_for(state='attached',timeout=5000)
                    footer.evaluate("e=>e.scrollIntoView({block:'end'})")
                    page.wait_for_function("document.documentElement.classList.contains('footer-revealed')",timeout=5000)
                    details=footer.evaluate("e=>({display:getComputedStyle(e).display,visibility:getComputedStyle(e).visibility,year:e.textContent.includes('2026'),links:e.querySelectorAll('a,button').length,text:e.textContent.trim().slice(0,160)})")
                    assert details['display']!='none' and details['visibility']=='visible' and details['year'] and details['links']>=12,(route,details)
                    assert footer.is_visible(),route
                    checks.append({'route':route,'status':response.status,**details})
                assert not errors,errors
                rounds.append({'round':number,'routes':len(checks),'checks':checks,'pageErrors':errors[:]})
            browser.close()
        result={'routeCount':len(ROUTES),'rounds':rounds}
        (OUT/'browser-id171-footer-all-routes.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps({'routeCount':len(ROUTES),'rounds':[{k:v for k,v in r.items() if k!='checks'} for r in rounds]},indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
