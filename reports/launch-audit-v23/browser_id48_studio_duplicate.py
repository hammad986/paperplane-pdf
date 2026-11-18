from pathlib import Path
from tempfile import TemporaryDirectory
import base64, fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / 'reports' / 'launch-audit-v23'
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id48-') as tmp:
    root = Path(tmp)
    source = root / 'duplicate.pdf'
    with fitz.open() as doc:
        doc.new_page().insert_text((72, 72), 'ID48 ORIGINAL PAGE CONTENT')
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
            for n in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900})
                errors = []
                page.on('pageerror', lambda e: errors.append(str(e)))
                page.goto(base + '/studio', wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(source))
                page.wait_for_function("window.PaperplaneEditor?.editorState?.sourceFile && document.querySelector('#pdf-canvas')?.dataset.rendered==='true'", timeout=30000)
                button = page.locator('#editor-dup-page-btn')
                button.wait_for(state='visible')
                button.click()
                page.wait_for_function("window.PaperplanePageOrganizer?.state.totalCount===2", timeout=30000)
                page.wait_for_timeout(300)
                payload = page.evaluate("""async()=>{const f=window.PaperplaneEditor.editorState.sourceFile;const a=new Uint8Array(await f.arrayBuffer());let b='';for(let i=0;i<a.length;i+=8192)b+=String.fromCharCode(...a.subarray(i,i+8192));return btoa(b)}""")
                output = OUT / f'id48-duplicate-round{n}.pdf'
                output.write_bytes(base64.b64decode(payload))
                with fitz.open(output) as doc:
                    pages = [p.get_text() for p in doc]
                assert len(pages) == 2 and all('ID48 ORIGINAL PAGE CONTENT' in text for text in pages), pages
                assert not errors, errors
                rounds.append({'round': n, 'pages': len(pages), 'page_text': pages, 'page_errors': errors})
                page.close()
            browser.close()
        (OUT / 'browser-id48-studio-duplicate.json').write_text(json.dumps(rounds, indent=2), encoding='utf-8')
        print(json.dumps(rounds, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
