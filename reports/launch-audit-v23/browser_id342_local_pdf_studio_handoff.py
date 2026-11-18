from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
import base64
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id342-') as temp:
    root = Path(temp)
    pages = []
    for name, count, prefix in (('first.pdf', 2, 'FIRST LOCAL SOURCE'), ('second.pdf', 2, 'SECOND LOCAL SOURCE')):
        path = root / name
        with fitz.open() as document:
            for number in range(1, count + 1):
                document.new_page().insert_text((72, 72), f'{prefix} PAGE {number}')
            document.save(path)
        pages.append(path)
    cases = [
        {'name': 'merge', 'route': '/merge-pdf', 'files': pages, 'configure': None, 'count': 4},
        {'name': 'rotate', 'route': '/rotate-pdf', 'files': [pages[0]], 'configure': None, 'count': 2},
        {'name': 'split', 'route': '/split-pdf', 'files': [pages[0]], 'configure': 'split', 'count': 1},
        {'name': 'remove', 'route': '/remove-pages-pdf', 'files': [pages[0]], 'configure': 'remove', 'count': 1},
    ]
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
            for round_number in (1, 2):
                for case in cases:
                    context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + case['route'], wait_until='domcontentloaded')
                    assert page.evaluate("localStorage.getItem('paperplane-pdf-processing-mode')") != 'server'
                    page.locator('#file-input').set_input_files([str(path) for path in case['files']])
                    if case['configure'] == 'split':
                        page.locator('#split_mode').select_option('range')
                        page.locator('#pages').fill('1')
                    elif case['configure'] == 'remove':
                        page.locator('#pages').fill('2')
                    page.wait_for_function("!document.querySelector('#run-button').disabled")
                    page.locator('#run-button').click()
                    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                    assert page.locator('#result-view-studio-btn').is_visible(), case['name']
                    with page.expect_download(timeout=30000) as event:
                        page.locator('#result-download-link').click()
                    download = event.value
                    output = root / f"{case['name']}-round{round_number}.pdf"
                    download.save_as(str(output))
                    with fitz.open(output) as result_pdf:
                        result_pages = result_pdf.page_count
                        result_text = '\n'.join(result_page.get_text() for result_page in result_pdf)
                    assert result_pages == case['count'], (case['name'], result_pages)
                    assert any(marker in result_text for marker in ('FIRST LOCAL SOURCE', 'SECOND LOCAL SOURCE'))
                    page.locator('#result-view-studio-btn').click()
                    page.wait_for_function("location.pathname === '/studio' && document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=30000)
                    payload = page.evaluate("""async () => { const file = window.PaperplaneEditor?.editorState?.sourceFile; if (!file) return null; const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return {name: file.name, data: btoa(binary)}; }""")
                    assert payload, case['name']
                    before_reload = root / f"{case['name']}-studio-before-reload.pdf"
                    before_reload.write_bytes(base64.b64decode(payload['data']))
                    with fitz.open(before_reload) as studio_pdf:
                        studio_text = '\n'.join(studio_page.get_text() for studio_page in studio_pdf)
                        assert any(marker in studio_text for marker in ('FIRST LOCAL SOURCE', 'SECOND LOCAL SOURCE'))
                    page.screenshot(path=str(OUT / f'id342-{case["name"]}-round{round_number}.png'))
                    page.reload(wait_until='domcontentloaded')
                    page.wait_for_function("document.body.classList.contains('studio-active') && document.querySelector('#page-total-indicator')?.textContent !== '0'", timeout=30000)
                    page.wait_for_function("window.PaperplaneEditor?.editorState?.sourceFile instanceof File", timeout=30000)
                    restored = page.evaluate("""async () => { const file = window.PaperplaneEditor?.editorState?.sourceFile; if (!file) return null; const bytes = new Uint8Array(await file.arrayBuffer()); let binary = ''; for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000)); return {name: file.name, data: btoa(binary)}; }""")
                    assert restored
                    after_reload = root / f"{case['name']}-studio-after-reload.pdf"
                    after_reload.write_bytes(base64.b64decode(restored['data']))
                    with fitz.open(after_reload) as restored_pdf:
                        restored_text = '\n'.join(restored_page.get_text() for restored_page in restored_pdf)
                        assert any(marker in restored_text for marker in ('FIRST LOCAL SOURCE', 'SECOND LOCAL SOURCE'))
                    assert not errors, errors
                    rounds.append({'round': round_number, 'operation': case['name'], 'download_name': download.suggested_filename, 'download_pages': result_pages, 'source_content_checked': True, 'studio_route': page.url.endswith('/studio'), 'studio_rendered_before_reload': True, 'studio_restored_after_reload': any(marker in restored_text for marker in ('FIRST LOCAL SOURCE', 'SECOND LOCAL SOURCE')), 'page_errors': errors})
                    context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id342-local-pdf-studio-handoff.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
