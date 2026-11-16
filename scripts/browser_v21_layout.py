from playwright.sync_api import sync_playwright
from pathlib import Path
import json
import fitz
out=Path('reports/launch-audit-v21/layout');out.mkdir(parents=True,exist_ok=True)
rows=[]
fixture=out/'layout-fixture.pdf'
with fitz.open() as doc:
 doc.new_page().insert_text((72,72),'Layout verification document')
 doc.save(fixture)
with sync_playwright() as p:
 b=p.chromium.launch(channel='chrome',headless=False)
 for width in (390,820,1366,1920):
  page=b.new_page(viewport={'width':width,'height':900})
  for route in ('/settings','/studio','/merge-pdf','/ai','/pricing'):
   page.goto('http://127.0.0.1:8765'+route,wait_until='networkidle')
   page.screenshot(path=str(out/f'after-{route[1:]}-{width}.png'))
   bad=page.evaluate('''() => [...document.querySelectorAll('body *')].filter(e=>{const r=e.getBoundingClientRect();return r.width>0&&r.height>0&&r.right>innerWidth+2&&r.left>=0&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]')}).map(e=>({tag:e.tagName,id:e.id,cls:e.className,right:Math.round(e.getBoundingClientRect().right)})).slice(0,15)''')
   rows.append({'width':width,'route':route,'overflow':bad})
  page.goto('http://127.0.0.1:8765/studio',wait_until='networkidle')
  page.locator('#studio-file-input').set_input_files(str(fixture.resolve()))
  page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '1'")
  page.locator('#btn-more-tools-trigger').click()
  page.locator('#studio-sign-btn').click()
  page.locator('#digital-sign-modal').wait_for(state='visible')
  page.screenshot(path=str(out/f'after-signature-{width}.png'))
  r=page.locator('.sign-modal-card').bounding_box()
  assert r['x']>=0 and r['x']+r['width']<=width, r
  assert page.locator('.sign-modal-card').evaluate("el => Number(getComputedStyle(el.closest('.modal-backdrop')).zIndex) > Number(getComputedStyle(document.querySelector('.toast-notice')).zIndex)")
  page.locator('#modal-close-digital-sign').click()
  page.close()
 b.close()
(out/'after.json').write_text(json.dumps(rows,indent=2))
print(json.dumps(rows,indent=2))
assert all(not row['overflow'] for row in rows)
