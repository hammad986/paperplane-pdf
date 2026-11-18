from pathlib import Path
import json
from playwright.sync_api import sync_playwright
BASE='http://127.0.0.1:8501'
OUT=Path(__file__).resolve().parent
errors=[]
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=True)
 page=b.new_page(viewport={'width':1366,'height':900})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto(BASE+'/rotate-pdf',wait_until='domcontentloaded')
 page.locator('#seo-page-heading').wait_for(state='visible',timeout=15000)
 page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'rotate'",timeout=15000)
 rotate={"url":page.url,"heading":page.locator('#seo-page-heading').inner_text(),"intro":page.locator('.seo-lede').inner_text(),"instructions":[x.inner_text() for x in page.locator('.seo-howto-step h3').all()],"body_text":page.locator('body').inner_text()}
 page.get_by_role('link',name='Page Organizer').click()
 page.wait_for_function("document.querySelector('.seo-content')?.dataset.operation === 'organize'",timeout=15000)
 organizer={"url":page.url,"heading":page.locator('#seo-page-heading').inner_text(),"intro":page.locator('.seo-lede').inner_text()}
 result={"rotate":rotate,"organizer":organizer,"page_errors":errors}
 out=OUT/'browser-id173-rotate-copy.json';out.write_text(json.dumps(result,indent=2),encoding='utf-8')
 page.screenshot(path=str(OUT/'id173-rotate-copy.png'),full_page=True)
 b.close()
 print(json.dumps(result,indent=2))
 assert rotate['heading']=='Rotate the entire PDF document'
 assert 'every page' in rotate['intro'].lower() and 'Page Organizer' in rotate['intro']
 assert 'page-by-page rotation workflow' not in rotate['body_text'].lower()
 assert organizer['heading']=='Reorder PDF pages by page number'
 assert not errors
