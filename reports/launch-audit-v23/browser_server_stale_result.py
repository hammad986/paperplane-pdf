"""Changing a file during a server job must not show its old result."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-server-stale-') as temp:
    root = Path(temp)
    files = [root / 'first.pdf', root / 'second.pdf']
    for path, marker in zip(files, ('FIRST-SERVER-MARKER', 'SECOND-SERVER-MARKER')):
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), marker)
            document.save(path)
    base = os.environ.get('PAPERPLANE_SERVER_STALE_BASE')
    server = None
    if not base:
        server, base, _ = helper.start_server(root / 'data')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError('server did not start')
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/rotate-pdf', wait_until='domcontentloaded')
                toggle = page.locator('#client-privacy-toggle')
                if toggle.is_checked(): page.locator('label.toggle-switch-sm').filter(has=toggle).click()
                page.locator('#file-input').set_input_files(str(files[0]))
                page.wait_for_function("!document.querySelector('#run-button').disabled")
                page.evaluate('''() => {
                  window.__originalServerSubmit = submitJobWithUploadProgress;
                  window.__originalWaitForJob = waitForJob;
                  submitJobWithUploadProgress = async () => ({status_url:'/controlled-status', download_url:'/controlled-download'});
                  waitForJob = async () => { await new Promise(resolve => {window.__finishServer=resolve});
                    return {status:'completed',output_name:'old-result.pdf',output_size:123}; };
                }''')
                page.locator('#run-button').click()
                page.wait_for_function('typeof window.__finishServer === "function"', timeout=30000)
                page.locator('#file-input').set_input_files(str(files[1]))
                page.evaluate('window.__finishServer()')
                page.wait_for_timeout(700)
                assert page.locator('#result').is_hidden(), 'old server result appeared for replacement file'
                assert page.locator('#progress-card').is_hidden(), 'old server progress remained visible'
                assert page.locator('#run-button').is_enabled(), 'replacement file cannot run'
                page.evaluate('''() => {
                  submitJobWithUploadProgress = window.__originalServerSubmit;
                  waitForJob = window.__originalWaitForJob;
                }''')
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=60000)
                with page.expect_download(timeout=30000) as event:
                    page.locator('#result-download-link').click()
                output = root / f'replacement-{number}.pdf'
                event.value.save_as(output)
                with fitz.open(output) as doc:
                    assert len(doc) == 1 and 'SECOND-SERVER-MARKER' in doc[0].get_text()
                    assert 'FIRST-SERVER-MARKER' not in doc[0].get_text()
                assert not errors, errors
                rounds.append({'round': number, 'stale_result_hidden': True, 'progress_hidden': True,
                               'replacement_ready': True, 'replacement_download_content_checked': True,
                               'page_errors': errors})
                context.close()
            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)
report = {'base': base, 'rounds': rounds, 'result': 'PASS'}
filename = 'browser-server-stale-result-docker.json' if os.environ.get('PAPERPLANE_SERVER_STALE_BASE') else 'browser-server-stale-result.json'
(OUT / filename).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
