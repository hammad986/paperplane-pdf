from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id337-') as temp:
    root = Path(temp)
    source = root / 'wide-photo.png'
    image = Image.new('RGB', (400, 200), (220, 35, 25))
    ImageDraw.Draw(image).rectangle((5, 5, 394, 194), outline=(255, 255, 0), width=8)
    image.save(source)
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
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for number in (1, 2):
                context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base + '/resize-image-dimensions', wait_until='domcontentloaded')
                page.locator('#width').fill('100')
                page.locator('#height').fill('100')
                assert 'centered on a white canvas' in page.locator('#options').inner_text()
                page.locator('#file-input').set_input_files(str(source))
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                assert '100 × 100 px' in page.locator('#result-meta').inner_text()
                with page.expect_download(timeout=30000) as event:
                    page.locator('#result-download-link').click()
                download = event.value
                output = root / f'resized-{number}.jpg'
                download.save_as(str(output))
                with Image.open(output) as result:
                    result.load()
                    top = result.convert('RGB').getpixel((50, 5))
                    center = result.convert('RGB').getpixel((50, 50))
                    bottom = result.convert('RGB').getpixel((50, 95))
                    dimensions = list(result.size)
                assert dimensions == [100, 100]
                assert min(top) > 230 and min(bottom) > 230, (top, bottom)
                assert center[0] > center[1] * 3 and center[0] > center[2] * 2, center
                assert not errors, errors
                page.screenshot(path=str(OUT / f'id337-resize-fit-round{number}.png'))
                rounds.append({'round': number, 'dimensions': dimensions, 'top_pixel': top, 'center_pixel': center, 'bottom_pixel': bottom, 'white_letterbox_detected': True, 'source_content_retained': True, 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id337-photo-resize-aspect-ratio.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
