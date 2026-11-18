from pathlib import Path
from tempfile import TemporaryDirectory
import json, re, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent
SOURCE = ROOT / 'reports' / 'launch-audit-v8' / 'test-files' / 'notes-69page.pdf'

with TemporaryDirectory(prefix='paperplane-id41-') as temp:
    root = Path(temp)
    app, base, _identity = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        outcomes = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for round_number in (1, 2):
                context = browser.new_context(accept_downloads=True, viewport={'width': 1366, 'height': 900})
                page = context.new_page()
                page_errors = []
                page.on('pageerror', lambda error: page_errors.append(str(error)))
                page.goto(base + '/pdf-to-markdown', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(SOURCE))
                page.locator('#run-button').wait_for(state='visible', timeout=10000)
                page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=30000)
                started = time.monotonic()
                with page.expect_response(lambda response: '/api/jobs' in response.url and response.request.method == 'POST', timeout=30000) as job_wait:
                    page.locator('#run-button').click()
                job_response = job_wait.value
                page.wait_for_function("document.querySelector('#result')?.hidden === false", timeout=180000)
                with page.expect_download(timeout=30000) as download_wait:
                    page.locator('#result-download-link').click()
                download = download_wait.value
                output = root / f'notes-69page-round{round_number}.md'
                download.save_as(str(output))
                markdown = output.read_text(encoding='utf-8')
                elapsed = round(time.monotonic() - started, 2)
                page_count = len(re.findall(r'^## Page \d+$', markdown, flags=re.MULTILINE))
                job_id = job_response.json().get('job_id', '')
                content_checks = {
                    'page_sections': page_count,
                    'contains_page_1': '## Page 1' in markdown,
                    'contains_page_69': '## Page 69' in markdown,
                    'contains_expected_first_page_content': 'Machine learning is the study of computer algorithms' in markdown,
                    'contains_expected_last_page_content': 'Section 69.' in markdown,
                    'leaks_job_identifier': bool(job_id and job_id in markdown),
                }
                outcome = {
                    'round': round_number,
                    'source_bytes': SOURCE.stat().st_size,
                    'http_status': job_response.status,
                    'elapsed_seconds': elapsed,
                    'download_name': download.suggested_filename,
                    'download_bytes': output.stat().st_size,
                    'markdown_content': content_checks,
                    'page_errors': page_errors,
                }
                outcomes.append(outcome)
                page.screenshot(path=str(OUT / f'id41-markdown-round{round_number}.png'))
                assert job_response.status == 202
                assert page_count == 69 and content_checks['contains_page_1'] and content_checks['contains_page_69']
                assert content_checks['contains_expected_first_page_content'] and content_checks['contains_expected_last_page_content']
                assert not content_checks['leaks_job_identifier']
                assert not page_errors
                context.close()
            browser.close()
        result = {'source': str(SOURCE), 'rounds': outcomes}
        (OUT / 'browser-id41-markdown-69page.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
