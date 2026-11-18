from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix='paperplane-id2-provider-failure-') as temp:
    root = Path(temp)
    fixture = root / 'controlled-69-page-brief.pdf'
    with fitz.open() as pdf:
        for page_number in range(1, 70):
            page = pdf.new_page()
            page.insert_text((72, 72), f'Operations review source page {page_number}, with extractable content for a complete brief.')
            if page_number == 24:
                page.insert_text((72, 112), 'Chunk 24 decision: preserve every supporting record for the final audit.')
            if page_number == 69:
                page.insert_text((72, 112), 'Final page condition: keep all 69 records available for independent review.')
        pdf.save(fixture)
    app, base, identity = helper.start_server(root / 'data')
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
            for round_number in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900})
                context.add_cookies([{'name':'paperplane_token','value':identity['accounts'][0][1],'url':base,'httpOnly':True}])
                context.route('**/api/ai/capabilities', lambda route: route.fulfill(status=200, content_type='application/json', body=json.dumps({'executive_brief_available':True,'reason':None})))
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/ai-intelligence', wait_until='domcontentloaded')
                page.locator('#ai-file-input').set_input_files(str(fixture))
                page.locator('#ai-active-doc-bar').wait_for(state='visible', timeout=20000)
                with page.expect_response(lambda response: '/api/ai/summarize' in response.url, timeout=60000) as response_wait:
                    page.locator('#trigger-summary-btn').click()
                response = response_wait.value
                body = response.json()
                page.wait_for_function("document.querySelector('#summary-display')?.innerText.includes('Offline Analysis')", timeout=15000)
                visible_summary = page.locator('#summary-display').inner_text()
                evidence = {
                    'round':round_number,
                    'http_status':response.status,
                    'summary_mode':body.get('summary_mode'),
                    'citations_count':len(body.get('citations',[])),
                    'citation_min':min(body['citations']) if body.get('citations') else None,
                    'citation_max':max(body['citations']) if body.get('citations') else None,
                    'page_24_decision_preserved':'Chunk 24 decision: preserve every supporting record for the final audit.' in body.get('summary',''),
                    'page_69_condition_preserved':'Final page condition: keep all 69 records available for independent review.' in body.get('summary',''),
                    'offline_badge':page.locator('#summary-mode-badge').inner_text(),
                    'ui_contains_final_condition':'Final page condition' in visible_summary,
                    'page_errors':errors,
                }
                assert evidence['http_status']==200 and evidence['summary_mode']=='offline_extractive', evidence
                assert evidence['citation_min']==1 and evidence['citation_max']==69 and evidence['citations_count']==69, evidence
                assert evidence['page_24_decision_preserved'] and evidence['page_69_condition_preserved'] and evidence['ui_contains_final_condition'], evidence
                assert evidence['offline_badge']=='Offline Analysis' and not errors, evidence
                page.screenshot(path=str(OUT/f'id2-provider-fallback-round{round_number}.png'), full_page=True)
                rounds.append(evidence)
                context.close()
            browser.close()
        result={'rounds':rounds,'provider':'unconfigured local test environment; expected deterministic fallback'}
        (OUT/'browser-id2-69page-provider-failure-fallback.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
