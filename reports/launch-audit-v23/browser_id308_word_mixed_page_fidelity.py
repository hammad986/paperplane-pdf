from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time, zipfile
from PIL import Image, ImageDraw
from docx import Document
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper


with TemporaryDirectory(prefix='paperplane-id308-') as temp:
    root = Path(temp)
    image_path = root / 'source-photo.png'
    image = Image.new('RGB', (180, 120), 'white')
    draw = ImageDraw.Draw(image)
    draw.rectangle((8, 8, 171, 111), fill='#356b8c')
    draw.ellipse((58, 20, 122, 84), fill='#f2c14e')
    image.save(image_path)
    fixture = root / 'mixed-content.pdf'
    with fitz.open() as pdf:
        page = pdf.new_page(width=612, height=792)
        page.insert_text((72, 72), 'Mixed-page editable report title', fontsize=18)
        page.insert_text((72, 104), 'Editable paragraph retained beside the image and table.', fontsize=11)
        page.insert_image(fitz.Rect(72, 140, 252, 260), filename=str(image_path))
        xs = [300, 390, 475, 555]
        ys = [150, 180, 210, 240]
        for x in xs:
            page.draw_line((x, ys[0]), (x, ys[-1]), color=(0, 0, 0), width=1)
        for y in ys:
            page.draw_line((xs[0], y), (xs[-1], y), color=(0, 0, 0), width=1)
        cells = [
            ['Item', 'Quantity', 'Price'],
            ['Pencils', '4', '$2'],
            ['Notebooks', '3', '$9'],
        ]
        for row, values in enumerate(cells):
            for col, value in enumerate(values):
                page.insert_text((xs[col] + 5, ys[row] + 20), value, fontsize=10)
        pdf.save(fixture)
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
        with sync_playwright() as p:
            browser = p.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                page = browser.new_page(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/pdf-to-word', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(fixture))
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                with page.expect_download(timeout=30000) as download_wait:
                    page.locator('#result-download-link').click()
                download = download_wait.value
                output = root / f'mixed-content-round-{number}.docx'
                download.save_as(output)
                document = Document(output)
                paragraphs = '\n'.join(p.text for p in document.paragraphs)
                table_data = [[[cell.text for cell in row.cells] for row in table.rows] for table in document.tables]
                with zipfile.ZipFile(output) as archive:
                    media = [name for name in archive.namelist() if name.startswith('word/media/')]
                assert 'Mixed-page editable report title' in paragraphs and 'Editable paragraph retained' in paragraphs, paragraphs
                assert any('Pencils' in str(table) and 'Notebooks' in str(table) for table in table_data), table_data
                assert media, media
                assert not errors, errors
                rounds.append({'round': number, 'docx_bytes': output.stat().st_size, 'paragraphs': paragraphs, 'tables': table_data, 'media_files': media, 'page_errors': errors})
                page.screenshot(path=str(OUT / f'id308-word-mixed-page-round{number}.png'))
                page.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id308-word-mixed-page-fidelity.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
