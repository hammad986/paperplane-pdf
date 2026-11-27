"""Compare camera EXIF orientation in local and server scan downloads."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import os
import socket
import sys
import time

import fitz
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

rounds = []
with TemporaryDirectory(prefix='paperplane-scan-exif-') as temp:
    directory = Path(temp)
    source = directory / 'camera-rotated.jpg'
    image = Image.new('RGB', (240, 120), 'blue')
    ImageDraw.Draw(image).rectangle((0, 0, 119, 119), fill='red')
    exif = image.getexif()
    exif[274] = 6
    image.save(source, quality=95, exif=exif)
    base = os.environ.get('PAPERPLANE_EXIF_TEST_BASE')
    server = None
    if not base:
        server, base, _ = helper.start_server(directory / 'data')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=.2):
                    break
            except OSError:
                time.sleep(.2)
        else:
            raise RuntimeError('local server did not start')
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                for local in (True, False):
                    context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/scan-to-pdf', wait_until='domcontentloaded')
                    toggle = page.locator('#client-privacy-toggle')
                    if toggle.is_checked() != local:
                        page.locator('label.toggle-switch-sm').filter(has=toggle).click()
                    page.locator('#file-input').set_input_files(str(source))
                    page.locator('#page_size').select_option('original')
                    page.locator('#run-button').click()
                    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=60000)
                    with page.expect_download(timeout=30000) as event:
                        page.locator('#result-download-link').click()
                    output = directory / f'{number}-{local}.pdf'
                    event.value.save_as(output)
                    with fitz.open(output) as doc:
                        assert len(doc) == 1
                        rect = doc[0].rect
                        pix = doc[0].get_pixmap(matrix=fitz.Matrix(3, 3), alpha=False)
                        top = pix.pixel(pix.width // 2, pix.height // 4)
                        bottom = pix.pixel(pix.width // 2, 3 * pix.height // 4)
                        result = {'round': number, 'mode': 'local' if local else 'server',
                                  'page_points': [rect.width, rect.height], 'top_rgb': top,
                                  'bottom_rgb': bottom, 'page_errors': errors}
                        rounds.append(result)
                    assert abs(rect.width - 43.2) < .2 and abs(rect.height - 86.4) < .2, result
                    assert top[0] > top[2] + 80 and bottom[2] > bottom[0] + 80, result
                    assert not errors, errors
                    context.close()
            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)
report = {'base': base, 'rounds': rounds, 'result': 'PASS'}
filename = 'browser-scan-exif-orientation-docker.json' if os.environ.get('PAPERPLANE_EXIF_TEST_BASE') else 'browser-scan-exif-orientation.json'
(OUT / filename).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
