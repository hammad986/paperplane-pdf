from pathlib import Path
from PIL import Image
from playwright.sync_api import sync_playwright
import fitz, json
root=Path.cwd(); img=root/'reports/launch-audit-v24/id253-2400x1800.png'
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':1366,'height':900},accept_downloads=True); errors=[]
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8774/scan-to-pdf',wait_until='domcontentloaded',timeout=30000)
 page.wait_for_timeout(1000); page.locator('#page_size').select_option('original'); page.locator('#file-input').set_input_files(str(img)); page.wait_for_timeout(500)
 page.locator('#run-button').click(); page.wait_for_function("!document.querySelector('#result').hidden && !document.querySelector('#result-download-link').hidden",timeout=60000)
 with page.expect_download(timeout=30000) as pending: page.locator('#result-download-link').click()
 download=pending.value; out=root/'reports/launch-audit-v24/id253-browser-output.pdf'; download.save_as(out)
 with fitz.open(out) as pdf:
  result={'route':page.url,'file':download.suggested_filename,'pages':pdf.page_count,'page_size_pt':[round(pdf[0].rect.width,2),round(pdf[0].rect.height,2)],'expected_200dpi_pt':[864,648],'embedded_image_px':list(pdf[0].get_images(full=True)[0][2:4]),'errors':errors,'result_text':page.locator('#result-meta').inner_text()}
 page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id253-original-size.png'),full_page=True)
 (root/'reports/launch-audit-v24/browser-id253-original-size.json').write_text(json.dumps(result,indent=2))
 print(json.dumps(result,indent=2)); b.close()
