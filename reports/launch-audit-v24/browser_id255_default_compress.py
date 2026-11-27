from pathlib import Path
from PIL import Image
import random, json
from playwright.sync_api import sync_playwright
root=Path.cwd(); source=root/'reports/launch-audit-v24/id255-noisy-source.jpg'; output=root/'reports/launch-audit-v24/id255-default-compressed.jpg'
rng=random.Random(255); image=Image.new('RGB',(1200,800)); image.putdata([(rng.randrange(256),rng.randrange(256),rng.randrange(256)) for _ in range(1200*800)]); image.save(source,quality=96)
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':390,'height':844},accept_downloads=True); errors=[]; page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8774/compress-image-online',wait_until='domcontentloaded',timeout=30000); page.wait_for_timeout(1000)
 default=page.locator('#target_kb').input_value(); page.locator('#file-input').set_input_files(str(source)); page.wait_for_timeout(400); page.locator('#run-button').click()
 page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=60000)
 with page.expect_download(timeout=30000) as pending: page.locator('#result-download-link').click()
 pending.value.save_as(output)
 with Image.open(output) as compressed:
  result={'route':page.url,'default_target_kb':int(default),'source_bytes':source.stat().st_size,'output_bytes':output.stat().st_size,'output_dimensions':list(compressed.size),'under_default_target':output.stat().st_size <= int(default)*1024,'warning':page.locator('#result-meta').inner_text(),'errors':errors}
 page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id255-default-compress.png'),full_page=True); (root/'reports/launch-audit-v24/browser-id255-default-compress.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2));b.close()
