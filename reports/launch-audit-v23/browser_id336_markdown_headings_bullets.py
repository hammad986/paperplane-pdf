from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id336-') as temp:
    root = Path(temp)
    source = root / 'heading-and-table-bullet.pdf'
    with fitz.open() as document:
        page = document.new_page()
        page.insert_text((60, 70), 'Quarterly Results', fontsize=22)
        page.insert_text((60, 104), 'Revenue grew by 12 percent.', fontsize=10)
        page.insert_text((60, 134), '- - Operating costs remained stable.', fontsize=10)
        page.insert_text((60, 164), 'Next Steps', fontsize=18)
        page.insert_text((60, 194), 'Review the updated forecast.', fontsize=10)
        for point, text in (((70, 250), 'Metric'), ((220, 250), 'Result'),
                            ((70, 280), 'Revenue'), ((220, 280), '12%')):
            page.insert_text(point, text, fontsize=10)
        shape = page.new_shape()
        for start, end in (((60, 230), (320, 230)), ((60, 260), (320, 260)),
                           ((60, 290), (320, 290)), ((60, 230), (60, 290)),
                           ((190, 230), (190, 290)), ((320, 230), (320, 290))):
            shape.draw_line(start, end)
        shape.finish(color=(0, 0, 0), width=1)
        shape.commit()
        document.save(source)
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
            for number in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                context.add_init_script("localStorage.setItem('paperplane-pdf-processing-mode', 'server')")
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/pdf-to-markdown', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(source))
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                with page.expect_download(timeout=30000) as event:
                    page.locator('#result-download-link').click()
                download = event.value
                result = root / f'round{number}.md'
                download.save_as(str(result))
                markdown = result.read_text(encoding='utf-8')
                print(f"round {number} downloaded {download.suggested_filename}:\n{markdown}", flush=True)
                assert '# Quarterly Results' in markdown and '# Next Steps' in markdown
                assert '- Operating costs remained stable.' in markdown and '- - Operating costs' not in markdown
                assert '| Metric | Result |' in markdown and '| Revenue | 12% |' in markdown
                assert 'Review the updated forecast.' in markdown and not errors, (markdown, errors)
                page.screenshot(path=str(OUT / f'id336-markdown-round{number}.png'))
                rounds.append({'round': number, 'download_name': download.suggested_filename, 'heading_levels': {'Quarterly Results': 1, 'Next Steps': 1}, 'normalized_bullet': True, 'paragraph_preserved': True, 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id336-markdown-headings-bullets.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
