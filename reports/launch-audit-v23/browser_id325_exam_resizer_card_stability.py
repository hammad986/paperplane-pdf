from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id325-') as temp:
    root = Path(temp)
    image_path = root / 'exam-photo-source.png'
    image = Image.new('RGB', (800, 800))
    pixels = image.load()
    for y in range(image.height):
        for x in range(image.width):
            pixels[x, y] = ((x * 13 + y * 3) % 256, (x * 5 + y * 11) % 256, (x * 7 + y * 17) % 256)
    ImageDraw.Draw(image).text((70, 70), 'EXAM PHOTO FIXTURE', fill='white')
    image.save(image_path)
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
                page.goto(base + '/ssc-photo-resizer', wait_until='domcontentloaded')
                page.locator('#file-input').set_input_files(str(image_path))
                page.wait_for_function("!document.querySelector('#run-button').disabled")
                page.locator('#run-button').click()
                page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                page.wait_for_timeout(1800)
                assert page.locator('#result').is_visible()
                assert page.locator('#cloud-modal').evaluate('modal => modal.hidden')
                meta = page.locator('#result-meta').inner_text()
                assert '350' in meta and '450' in meta, meta
                with page.expect_download(timeout=30000) as event:
                    page.locator('#result-download-link').click()
                download = event.value
                output = root / f'exam-photo-round{number}.jpg'
                download.save_as(str(output))
                with Image.open(output) as result_image:
                    result_image.load()
                    dimensions = list(result_image.size)
                    format_name = result_image.format
                assert dimensions == [350, 450] and format_name == 'JPEG'
                assert 20_000 <= output.stat().st_size <= 50_000
                assert page.locator('#result').is_visible() and not errors, errors
                page.screenshot(path=str(OUT / f'id325-exam-resizer-round{number}.png'))
                rounds.append({'round': number, 'result_card_still_visible_after_idle': True, 'cloud_modal_hidden': True, 'result_meta': meta, 'output_size': output.stat().st_size, 'format': format_name, 'dimensions': dimensions, 'page_errors': errors})
                context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id325-exam-resizer-stability.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
