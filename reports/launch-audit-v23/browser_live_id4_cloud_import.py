from pathlib import Path
import json
from playwright.sync_api import sync_playwright

URL = 'https://paperplane.qd.je'
FIXTURE = 'https://totpdf.com/samples/totpdf-sample-5-pages.pdf'
OUT = Path('reports/launch-audit-v23/browser-live-id4-cloud-import.json')
results = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    for round_no in (1, 2):
        page = browser.new_page(viewport={'width': 1366, 'height': 900})
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        response = page.goto(URL, wait_until='domcontentloaded', timeout=60000)
        assert response and response.status == 200, response.status if response else None
        page.locator('#topbar-cloud-btn').click()
        page.locator('#cloud-url').fill(FIXTURE)
        page.locator('#cloud-submit-btn').click()
        page.locator('.toast-notice').filter(has_text='Imported totpdf-sample-5-pages.pdf').wait_for(timeout=90000)
        toast = page.locator('.toast-notice').inner_text()
        assert '5 pages' in toast, toast
        assert not page.locator('#cloud-error').is_visible(), page.locator('#cloud-error').inner_text()
        assert not errors, errors
        rows = page.locator('#file-list .file-row-card')
        results.append({'round': round_no, 'home_status': response.status, 'toast': toast, 'imported_file_count': rows.count(), 'imported_filename': rows.locator('.file-row-name').first.inner_text() if rows.count() else None, 'page_errors': errors})
        page.close()
    browser.close()
OUT.write_text(json.dumps(results, indent=2), encoding='utf-8')
print(json.dumps(results, indent=2))
