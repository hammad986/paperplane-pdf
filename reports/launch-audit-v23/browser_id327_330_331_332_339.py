from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent

with TemporaryDirectory(prefix='paperplane-static-audit-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            page = browser.new_page(viewport={'width': 1366, 'height': 900})
            errors = []
            page.on('pageerror', lambda error: errors.append(str(error)))
            page.goto(base + '/faq', wait_until='domcontentloaded')
            page.wait_for_selector('#view-faq:not([hidden])')
            faq_count = page.locator('#view-faq details').count()
            assert faq_count >= 8
            page.goto(base + '/pdf-to-jpg', wait_until='domcontentloaded')
            page.wait_for_selector('#view-tool-desk:not([hidden])')
            page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'pdf_to_jpg'")
            selected_pages_faq = page.locator('.seo-content .seo-faq-item').filter(has_text='Can I convert only selected PDF pages?').evaluate('(el) => el.textContent')
            assert 'currently exports every page' in selected_pages_faq
            page.goto(base + '/settings', wait_until='domcontentloaded')
            await_settings = page.locator('#theme-light-btn')
            await_settings.wait_for(state='attached')
            page.evaluate("document.querySelector('#settings-modal')?.classList.add('open')")
            page.wait_for_function("document.querySelector('#theme-light-btn')?.classList.contains('active') && document.querySelector('#theme-light-btn strong')?.textContent.includes('(Default)')")
            light_default = page.locator('#theme-light-btn strong').inner_text()
            page.goto(base + '/tool-desk', wait_until='domcontentloaded')
            page.wait_for_function("document.querySelector('#tool-desk-tools-catalog')?.children.length > 0")
            temp_results = page.locator('.app-global-footer a[href="/history"]').text_content().strip()
            page.goto(base + '/history', wait_until='domcontentloaded')
            page.wait_for_selector('#view-history:not([hidden])')
            history_text = page.locator('#view-history').text_content()
            history_title = page.title()
            page.goto(base + '/developers', wait_until='domcontentloaded')
            page.wait_for_timeout(300)
            developer_title = page.title()
            developer_copy = page.locator('.api-docs-hero-box p').text_content()
            copy_button = page.locator('#btn-copy-full-api-code').text_content().strip()
            result = {
                'faq_question_count': faq_count,
                'pdf_to_jpg_subset_faq_honest': 'currently exports every page' in selected_pages_faq,
                'default_theme_label': light_default,
                'history_footer_label': temp_results,
                'history_discloses_no_saved_list': 'does not keep a job or download history list' in history_text,
                'history_title_matches_heading': history_title.startswith('Temporary results'),
                'developers_document_title': developer_title,
                'developers_intro_copy': developer_copy,
                'developers_copy_button': copy_button,
                'developers_duplicate_copy_word': copy_button.lower().count('copy') > 1,
                'page_errors': errors,
            }
            (OUT / 'browser-id327-330-331-332-339.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, indent=2))
            assert result['pdf_to_jpg_subset_faq_honest'] and '(Default)' in light_default and temp_results == 'Temporary results'
            assert result['history_discloses_no_saved_list'] and result['history_title_matches_heading']
            assert 'keys (' in developer_copy and 'keys(' not in developer_copy
            assert 'Copy Snippet' in copy_button and not result['developers_duplicate_copy_word']
            assert 'developer rest api' in developer_title.lower() and not errors
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=5)
