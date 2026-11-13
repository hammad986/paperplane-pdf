import json
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:8501'
PDF = Path('reports/launch-audit-v8/test-files/notes-69page.pdf').resolve()


def stored_state(page):
    return page.evaluate('''async () => {
      const db = await new Promise((resolve, reject) => {
        const request = indexedDB.open('paperplane-local-work', 1);
        request.onsuccess = () => resolve(request.result);
        request.onerror = () => reject(request.error);
      });
      const store = db.transaction('work', 'readonly').objectStore('work');
      const [keys, record] = await Promise.all([
        new Promise((resolve, reject) => { const r=store.getAllKeys(); r.onsuccess=()=>resolve(r.result.map(String)); r.onerror=()=>reject(r.error); }),
        new Promise((resolve, reject) => { const r=store.get('guest:studio-pdf'); r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error); })
      ]);
      const size = record?.blob?.size ?? null;
      const pagePosition = (() => { try { return JSON.parse(sessionStorage.getItem('paperplane-studio-position:guest') || 'null')?.page ?? null; } catch { return null; } })();
      db.close();
      return {keys, hasStudioRecord:!!record, blobBytes:size, savedPagePosition:pagePosition};
    }''')


def delete_page(page, page_number, expected_count):
    page.evaluate('(n) => { window.PaperplanePageOrganizer.deletePages([n]); return true; }', page_number)
    page.locator('dialog.app-confirm-dialog[open]').wait_for(timeout=15000)
    with page.expect_response(lambda response: response.url.endswith('/api/studio/page/delete') and response.request.method == 'POST', timeout=30000) as response_info:
        page.locator('dialog.app-confirm-dialog button').filter(has_text='Delete pages').click()
    page.wait_for_timeout(2500)
    observed_count = int(page.locator('#page-total-indicator').inner_text() or 0)
    return {
        'expected_count': expected_count,
        'observed_count': observed_count,
        'delete_http_status': response_info.value.status,
        'undo_visible': page.locator('#studio-undo-banner .work-clear-btn').is_visible(),
        'storage': stored_state(page),
    }


result = {'scope': 'isolated local synthetic PDF only', 'stages': [], 'page_errors': 0}
errors = []
with sync_playwright() as playwright:
    browser = playwright.chromium.launch(headless=True)
    context = browser.new_context(viewport={'width': 1920, 'height': 1080})
    page = context.new_page()
    page.on('pageerror', lambda error: errors.append(type(error).__name__))
    page.route('**/*', lambda route: route.continue_() if route.request.url.startswith(BASE) else route.abort())
    page.goto(BASE, wait_until='domcontentloaded', timeout=30000)
    page.locator('#tab-studio-view').click()
    page.locator('#studio-file-input').set_input_files(str(PDF))
    page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '69'", timeout=90000)
    page.wait_for_function("document.querySelector('#studio-page-stack .pdf-page-canvas[data-rendered=\\\"true\\\"]')", timeout=30000)
    page.wait_for_timeout(500)
    result['stages'].append({'stage': 'loaded_69', 'count': 69, 'storage': stored_state(page)})

    first_delete = delete_page(page, 69, 68)
    result['stages'].append({'stage': 'first_delete_before_reload', **first_delete})
    page.reload(wait_until='domcontentloaded')
    page.locator('#tab-studio-view').click()
    try:
        page.wait_for_function("Number(document.querySelector('#page-total-indicator')?.textContent) > 0", timeout=60000)
    except Exception:
        pass
    count_after_first_reload = int(page.locator('#page-total-indicator').inner_text())
    result['stages'].append({'stage': 'first_reload', 'count': count_after_first_reload, 'storage': stored_state(page)})

    if count_after_first_reload > 1:
        second_delete = delete_page(page, count_after_first_reload, count_after_first_reload - 1)
        result['stages'].append({'stage': 'second_delete_before_reload', **second_delete})
        page.reload(wait_until='domcontentloaded')
        page.locator('#tab-studio-view').click()
        try:
            page.wait_for_function("Number(document.querySelector('#page-total-indicator')?.textContent) > 0", timeout=60000)
        except Exception:
            pass
        result['stages'].append({'stage': 'second_reload_after_restore_wait', 'count': int(page.locator('#page-total-indicator').inner_text() or 0), 'storage': stored_state(page)})
    result['page_errors'] = len(errors)
    context.close()
    browser.close()

Path('reports/launch-audit-v10/outputs/studio-retention-diagnostic.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
print(json.dumps(result, indent=2))
