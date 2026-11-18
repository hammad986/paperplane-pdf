"""Re-run ID 161's 100 KB browser compression against the supplied 69-page notes.pdf."""
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, hashlib, json, socket, sys, time
from PIL import Image, ImageChops, ImageStat
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = Path('C:/Users/mdham/Downloads/notes.pdf')
if not FIXTURE.is_file():
    raise FileNotFoundError(FIXTURE)
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with fitz.open(FIXTURE) as source:
    assert source.page_count == 69
    source_text = [page.get_text() for page in source]
    source_chars = sum(map(len, source_text))
    source_marker = next((line.strip() for line in source_text[0].splitlines() if line.strip()), '')
    source_visuals = [page.get_pixmap(matrix=fitz.Matrix(.35, .35), alpha=False) for page in source]
    image_refs = {image[0] for page in source for image in page.get_images(full=True)}
    font_refs = {font[0] for page in source for font in page.get_fonts(full=True)}
    image_payload_bytes = 0
    for xref in image_refs:
        try:
            image_payload_bytes += len(source.extract_image(xref)['image'])
        except Exception:
            pass
    font_program_bytes = 0
    for xref in font_refs:
        try:
            font_program_bytes += len(source.extract_font(xref)[3])
        except Exception:
            pass
assert source_marker

with TemporaryDirectory(prefix='paperplane-id161-owner-notes-') as td:
    root = Path(td)
    app, base, identities = helper.start_server(root / 'db')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            identity = identities['accounts'][0]
            for round_no in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                context.add_cookies([{'name':'paperplane_token','value':identity[1], 'url':base, 'httpOnly':True}])
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                response = page.goto(base + '/compress-pdf', wait_until='domcontentloaded', timeout=20000)
                assert response and response.status == 200
                page.wait_for_function("state.operation==='compress' && document.querySelector('#preset')")
                page.locator('#preset').select_option('100kb')
                page.locator('#file-input').set_input_files(str(FIXTURE))
                page.wait_for_function('!document.querySelector(\'#run-button\').disabled', timeout=30000)
                page.locator('#run-button').click()
                page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden", timeout=180000)
                with page.expect_download(timeout=45000) as event:
                    page.locator('#result-download-link').click()
                output = root / f'notes-round{round_no}.pdf'
                download = event.value
                download.save_as(output)
                with fitz.open(output) as compressed:
                    texts = [pdf_page.get_text() for pdf_page in compressed]
                    output_pages = compressed.page_count
                    output_chars = sum(map(len, texts))
                    assert output_pages == 69, output_pages
                    assert source_marker in texts[0], {'expected':source_marker,'actual':texts[0][:300]}
                    nonempty_pages = sum(bool(text.strip()) for text in texts)
                    visual_diffs = []
                    for source_pixmap, output_page in zip(source_visuals, compressed):
                        output_pixmap = output_page.get_pixmap(matrix=fitz.Matrix(.35, .35), alpha=False)
                        source_image = Image.frombytes('RGB', (source_pixmap.width, source_pixmap.height), source_pixmap.samples)
                        output_image = Image.frombytes('RGB', (output_pixmap.width, output_pixmap.height), output_pixmap.samples)
                        assert source_image.size == output_image.size
                        visual_diffs.append(sum(ImageStat.Stat(ImageChops.difference(source_image, output_image)).mean) / 3)
                    mean_visual_diff = sum(visual_diffs) / len(visual_diffs)
                output_bytes = output.stat().st_size
                result_meta = page.locator('#result-meta').inner_text()
                missed_target_warning = 'requested target could not be reached' in result_meta.lower()
                assert output_bytes < 100_000 or missed_target_warning, {'output_bytes':output_bytes,'meta':result_meta}
                assert nonempty_pages == 69 and not errors, {'nonempty_pages':nonempty_pages,'errors':errors}
                rounds.append({'round':round_no,'http_status':response.status,
                               'source_bytes':FIXTURE.stat().st_size,'source_pages':69,
                               'source_sha256':hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
                               'source_text_chars':source_chars,'source_first_page_marker':source_marker,
                               'output_bytes':output_bytes,'output_pages':output_pages,
                               'output_text_chars':output_chars,'all_pages_have_text':nonempty_pages==69,
                               'mean_rendered_rgb_difference_0_255':mean_visual_diff,
                               'max_page_rendered_rgb_difference_0_255':max(visual_diffs),
                               'first_page_marker_preserved':True,'target_100000_bytes_reached':output_bytes<100_000,
                               'missed_target_warning_visible':missed_target_warning,
                               'result_meta':result_meta,'download_name':download.suggested_filename,
                               'page_errors':errors})
                page.close()
                context.close()
            browser.close()
        evidence={'item':161,'fixture':str(FIXTURE),
                  'source_profile':{'unique_image_refs':len(image_refs),
                                    'embedded_image_bytes':image_payload_bytes,
                                    'embedded_font_refs':len(font_refs),
                                    'embedded_font_program_bytes':font_program_bytes},
                  'rounds':rounds}
        (OUT/'browser-id161-download-notes-compress.json').write_text(
            json.dumps(evidence,indent=2,ensure_ascii=False),encoding='utf-8')
        print(json.dumps(evidence,indent=2,ensure_ascii=False))
    finally:
        app.terminate()
        app.wait(timeout=10)
