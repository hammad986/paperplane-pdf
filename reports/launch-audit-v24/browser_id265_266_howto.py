from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path.cwd(); results=[]
with sync_playwright() as p:
 b=p.chromium.launch(headless=True)
 for path,slug,title,phrases in [
  ('/ai-intelligence','ai','How AI Intelligence works',['Choose a task','Add a document when needed','Review the response']),
  ('/download','download','How the native apps waitlist works',['Use Paperplane in your browser','join this waitlist']),
 ]:
  for width,height in [(320,740),(390,844),(1366,900)]:
   page=b.new_page(viewport={'width':width,'height':height}); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
   page.goto('http://127.0.0.1:8774'+path,wait_until='domcontentloaded',timeout=30000);page.wait_for_timeout(250)
   heading=page.get_by_role('heading',name=title); heading.scroll_into_view_if_needed(); box=heading.bounding_box();body=page.locator('body').inner_text()
   row={'view':slug,'route':page.url,'viewport':width,'heading_visible':page.get_by_role('heading',name=title).is_visible(),'phrases_present':[text for text in phrases if text.lower() in body.lower()],'section_box':box,'document_overflow':page.evaluate('document.documentElement.scrollWidth > innerWidth'),'errors':errors,'styles_asset':page.locator('link[href*="styles.css"]').get_attribute('href')}
   results.append(row)
   if slug=='ai' and width==390:page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id265-ai-howto-390.png'),full_page=True)
   if slug=='download' and width==390:page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id266-download-howto-390.png'),full_page=True)
   assert row['heading_visible'] and len(row['phrases_present'])==len(phrases) and not row['document_overflow'] and not errors,row
   page.close()
 b.close()
(root/'reports/launch-audit-v24/browser-id265-266-howto.json').write_text(json.dumps(results,indent=2));print(json.dumps(results,indent=2))

