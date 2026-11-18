"""Content-checked browser downloads against the isolated production Docker image."""
from pathlib import Path
import json
import re
from zipfile import ZipFile

import fitz
from playwright.sync_api import sync_playwright

BASE = 'http://127.0.0.1:18501'
ROOT = Path(__file__).resolve().parent
FIXTURE = ROOT / 'fixtures' / 'totpdf-sample-5-pages.pdf'
OCR_FIXTURE = ROOT / 'ocr-golden-source.pdf'
results = []
errors = []

with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
    page.on('pageerror', lambda error: errors.append(str(error)))

    page.goto(BASE + '/merge-pdf', wait_until='domcontentloaded')
    page.locator('#tool-title').wait_for(state='visible')
    if page.locator('#client-privacy-toggle').is_checked():
        page.locator('#client-privacy-toggle').evaluate('el => el.click()')
    page.locator('#file-input').set_input_files(str(FIXTURE))
    assert page.locator('#file-list .file-row-name').inner_text() == FIXTURE.name
    page.locator('#run-button').click()
    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=90000)
    with page.expect_download(timeout=30000) as event:
        page.locator('#result-download-link').click()
    merge_path = ROOT / 'docker-merge-5-pages.pdf'
    event.value.save_as(merge_path)
    with fitz.open(merge_path) as doc:
        texts = [p.get_text() for p in doc]
        assert len(doc) == 5 and all(f'page {n} of 5' in texts[n - 1].lower() for n in range(1, 6)), texts
    results.append({'operation': 'merge', 'pages': 5, 'download_bytes': merge_path.stat().st_size, 'page_content_checked': True})

    page.goto(BASE + '/split-pdf', wait_until='domcontentloaded')
    page.locator('#tool-title').wait_for(state='visible')
    if page.locator('#client-privacy-toggle').is_checked():
        page.locator('#client-privacy-toggle').evaluate('el => el.click()')
    page.locator('#file-input').set_input_files(str(FIXTURE))
    page.locator('#split_mode').wait_for(state='visible')
    page.locator('#split_mode').select_option('all_pages')
    page.locator('#run-button').click()
    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=90000)
    with page.expect_download(timeout=30000) as event:
        page.locator('#result-download-link').click()
    split_path = ROOT / 'docker-split-5-pages.zip'
    event.value.save_as(split_path)
    with ZipFile(split_path) as archive:
        names = archive.namelist()
        assert len(names) == 5, names
        markers = []
        for name in names:
            with fitz.open(stream=archive.read(name), filetype='pdf') as doc:
                assert len(doc) == 1
                text = doc[0].get_text()
                match = re.search(r'page\s+(\d+)\s+of\s+5', text, re.I)
                assert match, text
                markers.append(int(match.group(1)))
        assert markers == [1, 2, 3, 4, 5], markers
    results.append({'operation': 'split-all-pages', 'output_files': 5, 'page_markers': markers, 'download_bytes': split_path.stat().st_size})

    page.goto(BASE + '/pdf-to-pdfa', wait_until='domcontentloaded')
    page.locator('#tool-title').wait_for(state='visible')
    if page.locator('#client-privacy-toggle').is_checked():
        page.locator('#client-privacy-toggle').evaluate('el => el.click()')
    page.locator('#file-input').set_input_files(str(FIXTURE))
    page.locator('#run-button').click()
    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=90000)
    with page.expect_download(timeout=30000) as event:
        page.locator('#result-download-link').click()
    pdfa_path = ROOT / 'docker-pdfa-5-pages.pdf'
    event.value.save_as(pdfa_path)
    with fitz.open(pdfa_path) as doc:
        assert len(doc) == 5
        xmp = doc.get_xml_metadata()
        kind, intents = doc.xref_get_key(doc.pdf_catalog(), 'OutputIntents')
        intent_ref = re.search(r'(\d+)\s+0\s+R', intents)
        intent_object = doc.xref_object(int(intent_ref.group(1)), compressed=False) if intent_ref else ''
        assert 'pdfaid:part=' in xmp and kind == 'array' and '/GTS_PDFA1' in intent_object, {'xmp': xmp, 'intent': intent_object}
        assert 'TotPDF sample - page 1 of 5' in doc[0].get_text()
    results.append({'operation': 'pdf-to-pdfa', 'pages': 5, 'pdfa_identification': True, 'output_intent': 'GTS_PDFA1', 'content_checked': True, 'download_bytes': pdfa_path.stat().st_size})

    page.goto(BASE + '/ocr-pdf', wait_until='domcontentloaded')
    page.locator('#tool-title').wait_for(state='visible')
    if page.locator('#client-privacy-toggle').is_checked():
        page.locator('#client-privacy-toggle').evaluate('el => el.click()')
    page.locator('#file-input').set_input_files(str(OCR_FIXTURE))
    page.locator('#run-button').click()
    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=90000)
    with page.expect_download(timeout=30000) as event:
        page.locator('#result-download-link').click()
    ocr_path = ROOT / 'docker-ocr-golden.pdf'
    event.value.save_as(ocr_path)
    with fitz.open(ocr_path) as doc:
        recognized = re.sub(r'\s+', ' ', doc[0].get_text())
        expected = ['PAPERPLANE OCR GOLDEN CHECK', 'Invoice 54821', 'Total: $124.50']
        assert all(phrase in recognized for phrase in expected), recognized
    results.append({'operation': 'ocr', 'pages': 1, 'recognized_phrases': expected, 'content_checked': True, 'download_bytes': ocr_path.stat().st_size})
    browser.close()

assert not errors, errors
report = {'base': BASE, 'fixture': FIXTURE.name, 'results': results, 'page_errors': errors}
(ROOT / 'browser-docker-runtime-smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
