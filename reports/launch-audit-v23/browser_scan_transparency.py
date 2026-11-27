"""Verify transparent camera images become white paper in both scan modes."""
from pathlib import Path
from tempfile import TemporaryDirectory
import json, os, socket, sys, time
import fitz
from PIL import Image
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports/launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-scan-alpha-') as temp:
    root = Path(temp)
    rgba = root / 'alpha.png'
    palette = root / 'palette.png'
    image = Image.new('RGBA', (100, 100), (0, 0, 0, 0))
    image.paste((255, 0, 0, 255), (25, 25, 75, 75))
    image.save(rgba)
    image.quantize(colors=2).save(palette, transparency=0)
    # Ensure the palette fixture's corner really is transparent and its center opaque.
    with Image.open(palette) as check:
        assert check.convert('RGBA').getpixel((0, 0))[3] == 0
        assert check.convert('RGBA').getpixel((50, 50))[3] == 255
    base = os.environ.get('PAPERPLANE_SCAN_ALPHA_BASE')
    server = None
    if not base:
        server, base, _ = helper.start_server(root / 'data')
    try:
        for _ in range(150):
            try:
                with socket.create_connection(('127.0.0.1', int(base.rsplit(':', 1)[1])), timeout=.2): break
            except OSError: time.sleep(.2)
        else: raise RuntimeError('local server did not start')
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                for local in (True, False):
                    for source in (rgba, palette):
                        context = browser.new_context(accept_downloads=True)
                        page = context.new_page()
                        errors = []
                        page.on('pageerror', lambda error: errors.append(str(error)))
                        page.goto(base + '/scan-to-pdf', wait_until='domcontentloaded')
                        toggle = page.locator('#client-privacy-toggle')
                        if toggle.is_checked() != local:
                            page.locator('label.toggle-switch-sm').filter(has=toggle).click()
                        page.locator('#file-input').set_input_files(str(source))
                        page.locator('#page_size').select_option('original')
                        page.wait_for_function("!document.querySelector('#run-button').disabled")
                        page.locator('#run-button').click()
                        page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=60000)
                        with page.expect_download(timeout=30000) as event:
                            page.locator('#result-download-link').click()
                        output = root / f'{number}-{local}-{source.name}.pdf'
                        event.value.save_as(output)
                        with fitz.open(output) as document:
                            assert len(document) == 1
                            pix = document[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=False)
                            corner = pix.pixel(5, 5)
                            center = pix.pixel(pix.width // 2, pix.height // 2)
                        assert min(corner) > 235 and center[0] > 200 and center[1] < 60 and center[2] < 60, (corner, center)
                        assert not errors, errors
                        rounds.append({'round': number, 'mode': 'local' if local else 'server',
                                       'input': source.name, 'corner_rgb': corner, 'center_rgb': center,
                                       'page_errors': errors})
                        context.close()
            browser.close()
    finally:
        if server:
            server.terminate()
            server.wait(timeout=15)
report = {'base': base, 'rounds': rounds, 'result': 'PASS'}
filename = 'browser-scan-transparency-docker.json' if os.environ.get('PAPERPLANE_SCAN_ALPHA_BASE') else 'browser-scan-transparency.json'
(OUT / filename).write_text(json.dumps(report, indent=2), encoding='utf-8')
print(json.dumps(report, indent=2))
