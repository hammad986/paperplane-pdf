from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id99-') as temp:
    root = Path(temp)
    pdf_path = root / 'items-table.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), 'Quarterly review')
        page.insert_text((72, 110), 'Item A value: 100')
        page.insert_text((72, 140), 'Item B value: 200')
        page.insert_text((72, 170), 'Item C value: 300')
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
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context()
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/ai-intelligence', wait_until='domcontentloaded')
                page.locator('#ai-file-input').set_input_files(str(pdf_path))
                page.locator('#chat-input').fill('What is the value for Item B?')
                page.locator('#chat-send-btn').click()
                page.wait_for_function("document.querySelector('.ai-stream-bubble .ai-stage-line span:last-child')?.textContent === 'Complete'", timeout=20000)
                response = page.locator('.ai-stream-bubble').evaluate("node => ({text:node.querySelector('.ai-stream-text').textContent, html:node.querySelector('.ai-stream-text').innerHTML, citations:[...node.querySelectorAll('.chat-citation-tags [data-ai-page]')].map(el=>Number(el.dataset.aiPage)), mode:node.querySelector('.ai-response-mode')?.textContent || ''})")
                assert '200' in response['text'], response
                assert response['citations'] == [1], response
                assert 'Local document extract' in response['mode'], response
                assert not errors, errors
                rounds.append({'round': number, 'question': 'What is the value for Item B?', 'response': response, 'page_errors': errors})
                context.close()
            browser.close()

        result = {'rounds': rounds}
        (OUT / 'browser-id99-neutral-question-attached-pdf.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
