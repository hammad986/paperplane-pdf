from pathlib import Path
from playwright.sync_api import sync_playwright
import json
root=Path.cwd()
with sync_playwright() as p:
 b=p.chromium.launch(headless=True); page=b.new_page(viewport={'width':390,'height':844}); errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8774/ai-intelligence',wait_until='domcontentloaded',timeout=30000);page.wait_for_timeout(300)
 data=page.evaluate("""() => {
   const host=document.createElement('div');
   host.innerHTML=renderMarkdown('Repeated facts **kept accurate** [Page 1] [Page 2] [Page 3]. Another fact [Page 6] [Page 7] [Pages 8-10]. Already ranged [Pages 12-13].');
   return {html:host.innerHTML,text:host.innerText,tags:[...host.querySelectorAll('[data-ai-page]')].map(e=>({text:e.textContent,page:e.dataset.aiPage,role:e.getAttribute('role'),tabindex:e.getAttribute('tabindex'),title:e.title}))};
 }""")
 data.update({'route':page.url,'asset':page.locator('script[src*="app.js"]').get_attribute('src'),'pageErrors':errors})
 assert len(data['tags'])==3,data
 assert [tag['text'] for tag in data['tags']]==['Pages 1–3','Pages 6–10','Pages 12–13'],data
 assert all(tag['role']=='button' and tag['tabindex']=='0' for tag in data['tags']),data
 assert 'Page 1' not in data['text'] and '[Pages' not in data['text'],data
 assert not errors,errors
 page.screenshot(path=str(root/'reports/launch-audit-v24/browser-id252-citation-ranges.png'),full_page=True)
 (root/'reports/launch-audit-v24/browser-id252-citation-ranges.json').write_text(json.dumps(data,indent=2))
 print(json.dumps(data,indent=2));b.close()
