from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id299-') as temp:
    app, base, identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for round_no in (1, 2):
                for scope in ('guest', 'authenticated'):
                    context = browser.new_context(viewport={'width': 1366, 'height': 900})
                    if scope == 'authenticated':
                        context.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base,'httpOnly':True}])
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/pricing', wait_until='domcontentloaded')
                    response = page.evaluate("""async () => {
                      const response = await fetch('/api/billing/status', {credentials:'same-origin'});
                      return {status:response.status, body:await response.json()};
                    }""")
                    serialized = json.dumps(response['body']).lower()
                    assert response['status'] == 200, response
                    assert 'cashfree_order_id' not in serialized and 'order_id' not in serialized, response
                    assert not errors, errors
                    results.append({'round':round_no,'scope':scope,'status':response['status'],'body':response['body'],'order_identifiers_absent':True,'page_errors':errors})
                    context.close()
            browser.close()
        result = {'checks':results}
        (OUT/'browser-id299-billing-status-disclosure.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
