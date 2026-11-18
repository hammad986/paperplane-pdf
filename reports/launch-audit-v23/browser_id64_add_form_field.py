from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
import base64
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id64-') as temp:
    root = Path(temp)
    source = root / 'form-source.pdf'
    with fitz.open() as document:
        document.new_page().insert_text((72, 72), 'ID 64 Add Field control regression')
        document.save(source)
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900})
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/studio', wait_until='domcontentloaded')
                page.locator('#studio-file-input').set_input_files(str(source))
                page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
                page.locator('#btn-more-tools-trigger').click()
                page.locator('#studio-forms-btn').click()
                page.locator('#forms-modal').wait_for(state='visible')
                page.locator('#forms-tab-add').click()
                add_visible = page.locator('#btn-apply-add-field').is_visible()
                fill_hidden = not page.locator('#btn-apply-form-fill').is_visible()
                assert add_visible and fill_hidden
                field_name = f'id64_field_{number}'
                page.locator('#new-field-name').fill(field_name)
                with page.expect_response(lambda response: response.url.endswith('/api/studio/forms/add-field')) as response_event:
                    page.locator('#btn-apply-add-field').click()
                response = response_event.value
                assert response.status == 200, (response.status, response.text())
                page.get_by_text(f'Added text field "{field_name}" to Page 1!', exact=True).wait_for(state='visible', timeout=10000)
                output = root / f'form-field-round{number}.pdf'
                file_state = page.evaluate("""async () => {const file=window.PaperplaneEditor?.editorState?.sourceFile;if(!file)return null;const bytes=new Uint8Array(await file.arrayBuffer());let binary='';for(let i=0;i<bytes.length;i+=0x8000)binary+=String.fromCharCode(...bytes.subarray(i,i+0x8000));return {name:file.name,data:btoa(binary),size:bytes.length}}""")
                assert file_state and file_state['size'] > 0, file_state
                output.write_bytes(base64.b64decode(file_state['data']))
                with fitz.open(output) as result:
                    widgets = [widget.field_name for widget in (result[0].widgets() or [])]
                    page_count = result.page_count
                assert field_name in widgets and page_count == 1, {'widgets': widgets, 'pages': page_count}
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id64-add-field-round{number}.png'))
                rounds.append({'round':number,'add_tab_button_visible':add_visible,'fill_button_hidden':fill_hidden,'response_status':response.status,'field_name':field_name,'output_widget_names':widgets,'output_pages':page_count,'success_notice_visible':True,'page_errors':errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id64-add-form-field.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
