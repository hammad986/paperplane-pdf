from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, hashlib, json, socket, sys, time, zipfile
from docx import Document
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / 'fixtures' / 'deutschebahn-2025-annual-report-excerpt-12p.pdf'
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

source_pdf = fitz.open(FIXTURE)
expected_markers = [
    'At a glance', 'Overview', 'SALE AND LEASEBACK',
    'Development of the economic and', 'The data collection methods',
    'Support funds for rail transport',
]
assert source_pdf.page_count == 12
assert all(marker.casefold() in '\n'.join(page.get_text('text') for page in source_pdf).casefold()
           for marker in expected_markers)
source_pdf.close()

with TemporaryDirectory(prefix='paperplane-id343-deutschebahn-') as td:
    root = Path(td)
    app, base, _identity = helper.start_server(root / 'db')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.2)
        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for round_number in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                response = page.goto(base + '/pdf-to-word', wait_until='domcontentloaded', timeout=20000)
                page.locator('#file-input').set_input_files(str(FIXTURE))
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=120000)
                with page.expect_download(timeout=60000) as event:
                    page.locator('#result-download-link').click()
                output = root / f'deutschebahn-12p-round-{round_number}.docx'
                await_download = event.value
                await_download.save_as(output)
                document = Document(output)
                paragraphs = [paragraph.text for paragraph in document.paragraphs]
                table_data = [[[cell.text for cell in row.cells] for row in table.rows]
                              for table in document.tables]
                merged_text = '\n'.join(paragraphs + [cell for table in table_data for row in table for cell in row])
                with zipfile.ZipFile(output) as archive:
                    xml_names = [name for name in archive.namelist() if name.endswith('.xml')]
                    for name in xml_names:
                        archive.read(name).decode('utf-8')
                    media_files = [name for name in archive.namelist() if name.startswith('word/media/')]
                normalized_text = ' '.join(merged_text.casefold().split())
                marker_hits = [marker for marker in expected_markers
                               if ' '.join(marker.casefold().split()) in normalized_text]
                assert response and response.status == 200
                assert len(marker_hits) >= 4, {'hits': marker_hits, 'expected': expected_markers}
                assert len(paragraphs) >= 40, len(paragraphs)
                assert not errors, errors
                rounds.append({
                    'round': round_number, 'http_status': response.status,
                    'source_page_count': 12, 'download_name': await_download.suggested_filename,
                    'docx_bytes': output.stat().st_size, 'paragraph_count': len(paragraphs),
                    'table_count': len(table_data), 'table_row_count': sum(map(len, table_data)),
                    'media_file_count': len(media_files), 'xml_parts_utf8_readable': len(xml_names),
                    'expected_text_markers': expected_markers, 'matched_text_markers': marker_hits,
                    'page_errors': errors,
                })
                page.close()
            browser.close()
        evidence = {
            'item': 343, 'source': 'Deutsche Bahn Group 2025 Annual Report, official 355-page PDF',
            'source_sha256': hashlib.sha256((OUT / 'fixtures' / 'deutschebahn-2025-annual-report.pdf').read_bytes()).hexdigest(),
            'excerpt_sha256': hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
            'excerpt_pages': 12, 'excerpt_size_bytes': FIXTURE.stat().st_size,
            'rounds': rounds,
        }
        (OUT / 'browser-id343-deutschebahn-real-excerpt.json').write_text(
            json.dumps(evidence, indent=2, ensure_ascii=False), encoding='utf-8')
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
    finally:
        app.terminate()
        app.wait(timeout=10)
