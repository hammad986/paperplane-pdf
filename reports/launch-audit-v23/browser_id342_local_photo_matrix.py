from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

def make_image(path, size, color, label):
    image = Image.new('RGB', size, color)
    ImageDraw.Draw(image).text((10, 10), label, fill='white')
    image.save(path)

with TemporaryDirectory(prefix='paperplane-id342-photos-') as temp:
    root = Path(temp)
    first = root / 'red-photo.png'
    second = root / 'blue-photo.png'
    make_image(first, (320, 160), (185, 35, 25), 'FIRST PHOTO')
    make_image(second, (240, 120), (25, 45, 190), 'SECOND PHOTO')
    cases = [
        {'name': 'resize', 'route': '/resize-image-dimensions', 'files': [first], 'configure': 'resize', 'dimensions': [100, 100]},
        {'name': 'compress', 'route': '/compress-image-online', 'files': [first], 'configure': None, 'dimensions': [320, 160]},
        {'name': 'exam-resizer', 'route': '/ssc-photo-resizer', 'files': [first], 'configure': None, 'dimensions': [350, 450]},
        {'name': 'photo-merge', 'route': '/merge-photos-online', 'files': [first, second], 'configure': None, 'dimensions': [320, 280]},
    ]
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
            for round_number in (1, 2):
                for case in cases:
                    context = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
                    page = context.new_page()
                    errors, server_jobs = [], []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.on('request', lambda request: server_jobs.append(request.url) if request.method == 'POST' and '/api/jobs' in request.url else None)
                    page.goto(base + case['route'], wait_until='domcontentloaded')
                    page.locator('#file-input').set_input_files([str(path) for path in case['files']])
                    if case['configure'] == 'resize':
                        page.locator('#width').fill('100')
                        page.locator('#height').fill('100')
                    page.wait_for_function("!document.querySelector('#run-button').disabled")
                    page.locator('#run-button').click()
                    page.locator('#result-download-link:not([hidden])').wait_for(state='visible', timeout=30000)
                    with page.expect_download(timeout=30000) as event:
                        page.locator('#result-download-link').click()
                    download = event.value
                    output = root / f"{case['name']}-round{round_number}.jpg"
                    download.save_as(str(output))
                    with Image.open(output) as result:
                        result.load()
                        dimensions = list(result.size)
                        image_format = result.format
                        rgb = result.convert('RGB')
                        if case['name'] == 'photo-merge':
                            upper = rgb.getpixel((160, 60))
                            lower = rgb.getpixel((120, 220))
                        elif case['name'] == 'resize':
                            upper = rgb.getpixel((50, 5))
                            lower = rgb.getpixel((50, 50))
                        else:
                            upper = rgb.getpixel((20, 20))
                            lower = rgb.getpixel((20, 20))
                    assert dimensions == case['dimensions'], (case['name'], dimensions)
                    assert image_format == 'JPEG'
                    assert not server_jobs, {'operation': case['name'], 'server_jobs': server_jobs}
                    if case['name'] == 'photo-merge':
                        assert upper[0] > upper[2] and lower[2] > lower[0], (upper, lower)
                    assert not errors, errors
                    page.screenshot(path=str(OUT / f"id342-photo-{case['name']}-round{round_number}.png"))
                    page.goto(base + '/tool-desk', wait_until='domcontentloaded')
                    page.wait_for_function("document.querySelector('#view-tool-desk-directory')?.hidden === false", timeout=15000)
                    page.reload(wait_until='domcontentloaded')
                    assert not errors, errors
                    rounds.append({'round': round_number, 'operation': case['name'], 'download_name': download.suggested_filename, 'dimensions': dimensions, 'jpeg_content_decoded': True, 'server_job_requests': len(server_jobs), 'route_change_and_reload_completed': True, 'page_errors': errors})
                    context.close()
            browser.close()
        result = {'rounds': rounds}
        (OUT / 'browser-id342-local-photo-matrix.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
