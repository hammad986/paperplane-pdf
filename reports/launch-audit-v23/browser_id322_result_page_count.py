from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id322-') as temp:
    root = Path(temp)
    sources = []
    for name, count, marker in (('first.pdf', 2, 'FIRST PAGE COUNT MARKER'),
                                ('second.pdf', 3, 'SECOND PAGE COUNT MARKER')):
        source = root / name
        with fitz.open() as document:
            for index in range(1, count + 1):
                page = document.new_page()
                page.insert_text((72, 72), f'{marker} {index}')
            document.save(source)
        sources.append(source)

    app, base, _identity = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for mode in ('local', 'server'):
                for number in (1, 2):
                    context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                    if mode == 'server':
                        context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'server')")
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/merge-pdf', wait_until='domcontentloaded')
                    page.locator('#file-input').set_input_files([str(source) for source in sources])
                    page.wait_for_function("!document.querySelector('#run-button').disabled")
                    page.locator('#run-button').click()
                    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                    page.wait_for_function("document.querySelector('#result-meta')?.dataset.pageCountState !== 'loading'", timeout=30000)
                    meta = page.locator('#result-meta').inner_text()
                    assert '5 pages' in meta, {'mode': mode, 'meta': meta}
                    with page.expect_download(timeout=30000) as event:
                        page.locator('#result-download-link').click()
                    download = event.value
                    path = root / f'{mode}-round{number}.pdf'
                    download.save_as(str(path))
                    with fitz.open(path) as output:
                        text = '\n'.join(pdf_page.get_text() for pdf_page in output)
                        page_count = output.page_count
                    assert page_count == 5
                    assert all(marker in text for marker in ('FIRST PAGE COUNT MARKER', 'SECOND PAGE COUNT MARKER'))
                    assert not errors, errors
                    page.screenshot(path=str(OUT / f'id322-{mode}-round{number}.png'))
                    rounds.append({
                        'mode': mode, 'round': number, 'result_meta': meta,
                        'download_name': download.suggested_filename, 'output_pages': page_count,
                        'source_markers_present': True, 'page_errors': errors,
                    })
                    context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id322-result-page-count.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
