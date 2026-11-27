"""A completed local worker must not publish against a changed file or tool."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, socket, sys, time
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-stale-local-') as temp:
    root = Path(temp)
    files = [root / 'first.pdf', root / 'second.pdf']
    for path, marker in zip(files, ('FIRST-MARKER', 'SECOND-MARKER')):
        with fitz.open() as document:
            document.new_page().insert_text((72, 72), marker)
            document.save(path)
    photos = [root / 'first.png', root / 'second.png']
    Image.new('RGB', (100, 60), 'red').save(photos[0])
    Image.new('RGB', (100, 60), 'blue').save(photos[1])
    base = os.environ.get('PAPERPLANE_STALE_TEST_BASE')
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
                for switch in ('file', 'tool'):
                    context = browser.new_context(accept_downloads=True)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/rotate-pdf', wait_until='domcontentloaded')
                    page.locator('#file-input').set_input_files(str(files[0]))
                    page.evaluate('''() => {
                      const runtime = window.PaperplanePdfRuntime;
                      window.__originalLocalRuntime = runtime;
                      window.__releaseLocal = null;
                      Object.defineProperty(window, 'PaperplanePdfRuntime', {configurable:true, value:{...runtime,
                        transformLocalPdf: async (...args) => {
                          const output = await runtime.transformLocalPdf(...args);
                          await new Promise(resolve => { window.__releaseLocal = resolve; });
                          return output;
                        }} });
                    }''')
                    page.locator('#run-button').click()
                    page.wait_for_function('typeof window.__releaseLocal === "function"', timeout=30000)
                    if switch == 'file':
                        page.locator('#file-input').set_input_files(str(files[1]))
                        assert page.locator('#progress-card').is_hidden(), 'old processing progress remains after changing file'
                    else:
                        page.evaluate("selectOperation('merge')")
                    page.evaluate('window.__releaseLocal()')
                    page.wait_for_timeout(500)
                    assert page.locator('#result').is_hidden(), (number, switch, page.locator('#result').inner_text())
                    assert not errors, errors
                    row = {'round': number, 'change': switch, 'stale_result_hidden': True, 'page_errors': errors}
                    if switch == 'file':
                        page.evaluate("Object.defineProperty(window, 'PaperplanePdfRuntime', {configurable:true, value:window.__originalLocalRuntime})")
                        assert page.locator('#run-button').is_enabled(), 'new file cannot be processed after stale completion'
                        page.locator('#run-button').click()
                        page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                        with page.expect_download(timeout=30000) as event:
                            page.locator('#result-download-link').click()
                        output = root / f'new-file-{number}.pdf'
                        event.value.save_as(output)
                        with fitz.open(output) as doc:
                            assert len(doc) == 1 and 'SECOND-MARKER' in doc[0].get_text()
                            assert 'FIRST-MARKER' not in doc[0].get_text()
                        row['new_file_download_content_checked'] = True
                    rounds.append(row)
                    context.close()
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/resize-image-dimensions', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(photos[0]))
                page.locator('#preset').select_option('passport')
                page.evaluate('''() => {
                  const original = loadImageFromFile;
                  window.__releasePhoto = null;
                  loadImageFromFile = async file => {
                    const image = await original(file);
                    await new Promise(resolve => { window.__releasePhoto = resolve; });
                    return image;
                  };
                }''')
                page.locator('#run-button').click()
                page.wait_for_function('typeof window.__releasePhoto === "function"', timeout=30000)
                page.locator('#file-input').set_input_files(str(photos[1]))
                page.evaluate('window.__releasePhoto()')
                page.wait_for_timeout(500)
                assert page.locator('#result').is_hidden() and not errors, errors
                rounds.append({'round': number, 'change': 'photo file', 'stale_result_hidden': True, 'page_errors': errors})
                context.close()
            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)
report = {'base': base, 'rounds': rounds, 'result': 'PASS'}
filename = 'browser-local-stale-result-docker.json' if os.environ.get('PAPERPLANE_STALE_TEST_BASE') else 'browser-local-stale-result.json'
(OUT / filename).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
