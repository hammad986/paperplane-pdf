from pathlib import Path
from tempfile import TemporaryDirectory
import base64, fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper


def make_fixture(path):
    with fitz.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 48), 'Provided proper attribution is provided, Google hereby grants permission to use this paper.', fontsize=9)
        page.insert_text((105, 170), 'Attention Is All You Need', fontsize=26)
        page.insert_text((72, 230), 'Ashish Vaswani and Noam Shazeer', fontsize=14)
        page.insert_text((72, 280), 'We propose a new simple network architecture, the Transformer.', fontsize=11)
        pdf.save(path)


with TemporaryDirectory(prefix='paperplane-id305-') as temp:
    root = Path(temp)
    fixture = root / 'attention-is-all-you-need.pdf'
    make_fixture(fixture)
    app, base, _identity = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/ai-intelligence', wait_until='domcontentloaded')
            page.locator('#ai-file-input').set_input_files(str(fixture))
            page.locator('#ai-active-doc-bar').wait_for(state='visible', timeout=20000)
            with page.expect_response(lambda response: '/api/ai/extract' in response.url, timeout=30000) as extract_wait:
                page.locator('#trigger-extract-btn').click()
            extract_response = extract_wait.value
            extract = extract_response.json()
            metadata_title = extract.get('data', {}).get('general_data', {}).get('title')
            encoded = base64.b64encode(fixture.read_bytes()).decode()
            chat = page.evaluate("""async ({encoded, filename}) => {
              const bytes = Uint8Array.from(atob(encoded), c => c.charCodeAt(0));
              const form = new FormData();
              form.append('file', new File([bytes], filename, {type: 'application/pdf'}));
              form.append('question', 'What is the title of this document?');
              const response = await fetch('/api/ai/chat/stream', {method: 'POST', body: form, credentials: 'same-origin'});
              return {status: response.status, body: await response.text()};
            }""", {'encoded': encoded, 'filename': fixture.name})
            events = []
            for frame in chat['body'].split('\n\n'):
                name = next((line[7:].strip() for line in frame.splitlines() if line.startswith('event: ')), None)
                raw = next((line[6:] for line in frame.splitlines() if line.startswith('data: ')), None)
                if raw:
                    events.append({'event': name, **json.loads(raw)})
            answer = next((event.get('text', '') for event in events if event.get('event') == 'replace'), '')
            evidence = {
                'route': base + '/ai-intelligence',
                'metadata_http_status': extract_response.status,
                'metadata_title': metadata_title,
                'chat_http_status': chat['status'],
                'chat_title_answer': answer,
                'same_document': True,
                'page_errors': errors,
            }
            (OUT / 'browser-id305-chat-metadata-consistency.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
            page.screenshot(path=str(OUT / 'id305-chat-metadata-consistency.png'), full_page=True)
            browser.close()
        print(json.dumps(evidence, indent=2))
        assert evidence['metadata_http_status'] == 200 and evidence['chat_http_status'] == 200, evidence
        assert metadata_title == 'Attention Is All You Need' and metadata_title in answer, evidence
        assert 'No relevant information found' not in answer and not errors, evidence
    finally:
        app.terminate()
        app.wait(timeout=5)
