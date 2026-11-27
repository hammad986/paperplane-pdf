import fitz,json
from pathlib import Path
from playwright.sync_api import sync_playwright
from io import BytesIO
pdf=fitz.open()
for marker in ['CLEAR_A','CLEAR_B','CLEAR_C']:
 p=pdf.new_page();p.insert_text((40,60),marker)
buf=pdf.tobytes();pdf.close();errors=[];rounds=[]
with sync_playwright() as p:
 b=p.chromium.launch()
 for n in (1,2):
  page=b.new_page();page.set_default_timeout(10000);page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto('http://127.0.0.1:8767/merge-pdf',wait_until='domcontentloaded');page.locator('#open-studio-btn').click();page.locator('#studio-file-input').set_input_files({'name':f'id69-clear-{n}.pdf','mimeType':'application/pdf','buffer':buf});page.wait_for_function("()=>document.querySelector('#studio-page-count')?.textContent.trim()==='3'")
  page.locator('#studio-clear-pdf-btn').click();dialog=page.locator('dialog.app-confirm-dialog');dialog.wait_for(state='visible');dialog.get_by_role('button',name='Clear Studio PDF').click()
  page.wait_for_function("()=>document.querySelector('#studio-page-count')?.textContent.trim()==='0'")
  immediate=page.locator('#studio-page-count').inner_text().strip();page.reload(wait_until='domcontentloaded');page.locator('#studio-page-count').wait_for();page.wait_for_timeout(700)
  restored=page.locator('#studio-page-count').inner_text().strip();
  rounds.append({'round':n,'cleared_immediately':immediate=='0','page_count_after_reload':restored,'no_stale_restore':restored=='0'})
  page.close()
 b.close()
result={'build':'app.js v191/styles.css v71','rounds':rounds,'browser_errors':errors,'passed':len(rounds)==2 and all(x['cleared_immediately'] and x['no_stale_restore'] for x in rounds) and not errors}
Path('reports/launch-audit-v24/browser-id69-clear-studio.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))