from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id116-') as temp:
    root = Path(temp)
    source = root / 'private-metadata.pdf'
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 100), 'SANITIZE FEEDBACK CONTENT CHECK')
        doc.set_metadata({'title':'Sensitive QA title','author':'ID116 Test Author','subject':'private metadata','keywords':'sanitize regression'})
        doc.save(source)

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
                context = browser.new_context(accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/studio', wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(source))
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
                page.locator('#btn-more-tools-trigger').click()
                page.locator('#studio-security-btn').click()
                page.locator('#security-modal:not([hidden])').wait_for(state='visible')
                page.locator('#sec-tab-audit').click()
                page.locator('#btn-apply-sanitize').click()
                report = page.locator('#sec-sanitize-report')
                report.wait_for(state='visible', timeout=20000)
                report_text = report.inner_text()
                assert 'Sanitization complete' in report_text, report_text
                with page.expect_download(timeout=15000) as download_info:
                    page.get_by_role('button', name='Download sanitized PDF').click()
                download = download_info.value
                output = root / f'sanitized-{number}.pdf'
                download.save_as(output)
                with fitz.open(output) as result:
                    content = result[0].get_text()
                    metadata = result.metadata
                    assert result.page_count == 1 and 'SANITIZE FEEDBACK CONTENT CHECK' in content, content
                    assert not metadata.get('author') and not metadata.get('title') and not metadata.get('subject'), metadata
                assert not errors, errors
                rounds.append({'round':number,'report':report_text,'download':download.suggested_filename,'bytes':output.stat().st_size,'pageCount':1,'content':content,'metadata':metadata,'pageErrors':errors})
                context.close()
            browser.close()

        evidence = {'sourceBytes':source.stat().st_size,'rounds':rounds}
        (OUT / 'browser-id116-sanitize-feedback.json').write_text(json.dumps(evidence, indent=2, default=str), encoding='utf-8')
        print(json.dumps(evidence, indent=2, default=str))
    finally:
        app.terminate()
        app.wait(timeout=5)
