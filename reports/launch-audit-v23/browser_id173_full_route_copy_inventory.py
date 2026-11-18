from pathlib import Path
from tempfile import TemporaryDirectory
import ast, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as h

tree = ast.parse((ROOT / 'server.py').read_text(encoding='utf-8'))
slugs = next(ast.literal_eval(n.value) for n in tree.body if isinstance(n, ast.Assign)
             and any(isinstance(t, ast.Name) and t.id == 'OPERATION_SLUGS' for t in n.targets))
results = []
with TemporaryDirectory(prefix='paperplane-id173-copy-inventory-') as td:
    app, base, _ = h.start_server(Path(td) / 'db')
    try:
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                routes = []
                for operation, slug in slugs.items():
                    response = page.goto(base + '/' + slug, wait_until='domcontentloaded', timeout=15000)
                    page.wait_for_function("document.querySelectorAll('.seo-content .seo-howto-step').length===3", timeout=10000)
                    data = page.evaluate("""() => ({
                      route: location.pathname, title: document.querySelector('#seo-page-heading')?.innerText.trim(),
                      meta_description: document.querySelector('meta[name="description"]')?.content || '',
                      intro: document.querySelector('.seo-lede')?.innerText.trim() || '',
                      faqs: [...document.querySelectorAll('.seo-faq-item')].map(x => ({
                        question: x.querySelector('summary')?.textContent.trim() || '',
                        answer: x.querySelector('p')?.textContent.trim() || ''
                      })),
                      steps: [...document.querySelectorAll('.seo-content .seo-howto-step')].map(x => ({
                        heading: x.querySelector('h3')?.innerText.trim() || '', body: x.querySelector('p')?.innerText.trim() || ''
                      })),
                      controls: [...document.querySelectorAll('input, select, textarea')]
                        .filter(x => { const r=x.getBoundingClientRect(),s=getComputedStyle(x); return r.width>0&&r.height>0&&s.visibility!=='hidden'&&!x.disabled; })
                        .map(x => ({tag:x.tagName,type:x.type||'',label:x.getAttribute('aria-label')||x.labels?.[0]?.innerText?.trim()||x.innerText?.trim()||x.placeholder||x.id||''})).slice(0,40)
                    })""")
                    assert response.status == 200 and len(data['steps']) == 3 and all(s['heading'] and s['body'] for s in data['steps']), (operation, data)
                    if operation == 'word_to_pdf':
                        assert data['steps'][1]['heading'] == 'Convert with the available document renderer'
                        assert 'no OCR or page-layout controls' in data['steps'][1]['body']
                    elif operation == 'powerpoint_to_pdf':
                        assert data['steps'][1]['heading'] == 'Convert the slides with the available renderer'
                        assert 'no orientation or output-options controls' in data['steps'][1]['body']
                    elif operation == 'annotate':
                        assert 'freehand' not in data['meta_description'].lower()
                        assert 'draw shapes' not in data['meta_description'].lower()
                        assert 'rectangle' in data['meta_description'].lower()
                    elif operation == 'html_to_pdf':
                        assert 'controlled page sizing' not in data['meta_description'].lower()
                        assert 'does not offer separate page-size controls' in data['steps'][1]['body']
                    elif operation == 'rotate':
                        assert 'entire PDF' in data['title']
                        assert 'selected pages independently' in data['intro']
                        assert all('page-by-page' not in (s['heading'] + s['body']).lower() for s in data['steps'])
                    elif operation == 'pdf_to_text':
                        assert 'full document' in data['steps'][1]['heading'].lower()
                        assert 'page-range' not in json.dumps(data).lower()
                    elif operation == 'pdf_to_markdown':
                        assert 'full document' in data['steps'][1]['heading'].lower()
                        assert 'page chooser' not in json.dumps(data).lower()
                    elif operation == 'pdf_to_jpg':
                        faq = {item['question']: item['answer'] for item in data['faqs']}
                        assert 'every page' in data['steps'][1]['body'].lower()
                        assert 'every page' in faq['Can I convert only selected PDF pages?'].lower()
                    elif operation == 'translate':
                        assert 'visible selector' in data['steps'][1]['heading']
                        assert 'available before upload' in data['steps'][1]['body']
                    elif operation == 'compare':
                        assert 'plain-text' in data['steps'][2]['heading'].lower()
                        assert 'highlighted differences' not in json.dumps(data).lower()
                    elif operation == 'watermark':
                        assert 'built-in layout' in data['steps'][1]['body'].lower()
                        assert 'built-in placement' in data['meta_description'].lower()
                        assert 'adjustable placement' not in data['meta_description'].lower()
                        assert 'rotation' not in data['meta_description'].lower()
                    elif operation == 'protect':
                        assert 'separate owner-password or permission controls' in data['steps'][1]['body']
                        assert 'configurable permissions' not in data['meta_description'].lower()
                        assert 'owner controls' not in data['intro'].lower()
                        faq = {item['question']: item['answer'] for item in data['faqs']}
                        assert 'does not offer permission controls' in faq['Can I prevent copying or printing?'].lower()
                    elif operation == 'crop':
                        assert 'every PDF page' in data['meta_description']
                        assert 'same top, bottom, left, and right margins' in data['meta_description']
                        assert 'every page' in data['steps'][1]['heading'].lower()
                        assert 'preview' not in data['steps'][2]['heading'].lower()
                        faq = {item['question']: item['answer'] for item in data['faqs']}
                        assert 'same top, bottom, left, and right margins to every page' in faq['Can I crop all pages with the same margins?']
                    elif operation == 'metadata':
                        assert 'title, author, and subject' in data['meta_description'].lower()
                        assert 'keywords' not in data['meta_description'].lower()
                    elif operation == 'word_to_pdf':
                        assert 'no OCR or page-layout controls' in data['steps'][1]['body']
                    elif operation == 'powerpoint_to_pdf':
                        assert 'no orientation or output-options controls' in data['steps'][1]['body']
                    elif operation == 'excel_to_pdf':
                        assert 'no sheet selector is shown' in data['steps'][1]['body']
                    elif operation == 'pdf_to_excel':
                        assert 'does not show table-region previews' in data['steps'][1]['body']
                    elif operation == 'ocr':
                        assert 'no quality setting is shown' in data['steps'][1]['body']
                    elif operation == 'annotate':
                        assert 'freehand' not in data['meta_description'].lower()
                        assert 'draw shapes' not in data['meta_description'].lower()
                        faq_text = json.dumps(data['faqs']).lower()
                        assert 'visual drawing' not in faq_text
                    routes.append({'operation': operation, 'status': response.status, **data})
                assert not errors, errors
                results.append({'round': round_no, 'routes': routes, 'page_errors': errors})
                context.close()
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)

assert all(len(r['routes']) == len(slugs) for r in results)
(OUT / 'browser-id173-full-route-copy-inventory.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps({'rounds': len(results), 'routes_each': len(slugs), 'status_failures': [x for r in results for x in r['routes'] if x['status'] != 200], 'browser_errors': [r['page_errors'] for r in results]}, indent=2))
