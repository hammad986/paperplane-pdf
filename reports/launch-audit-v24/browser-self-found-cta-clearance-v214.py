import json
from pathlib import Path
from playwright.sync_api import sync_playwright

base = Path('reports/launch-audit-v24')
results = []
errors = []
with sync_playwright() as p:
    browser = p.chromium.launch(channel='chrome', headless=True)
    for width, height in [(820, 900), (390, 844), (1366, 900)]:
        context = browser.new_context(viewport={'width': width, 'height': height}, device_scale_factor=1)
        page = context.new_page()
        page.on('pageerror', lambda exc: errors.append(str(exc)))
        page.goto('http://127.0.0.1:8765/merge-pdf', wait_until='networkidle', timeout=60000)
        page.wait_for_timeout(1500)
        measurements = page.evaluate('''() => {
          const rect = (sel) => { const e=document.querySelector(sel); if(!e) return null; const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,w:r.width,h:r.height,bottom:r.bottom,top:r.top}; };
          const main=document.querySelector('.main-area');
          const work=document.querySelector('.dynamic-workspace');
          const btn=rect('#run-button');
          const nav=rect('.mobile-workspace-bar');
          const fields=[...document.querySelectorAll('#options input, #options select, #options textarea, #options button, #options label')].filter(e=>e.getClientRects().length).map(e=>{const r=e.getBoundingClientRect(); return {tag:e.tagName,type:e.type||null,text:(e.labels?.[0]?.innerText||e.innerText||e.getAttribute('aria-label')||'').trim().slice(0,70),top:r.top,bottom:r.bottom};});
          const overlapping=fields.filter(x=>btn && x.bottom>btn.top && x.top<btn.bottom);
          const before={button:btn,nav,fields,overlapping,windowScrollY:scrollY,documentHeight:document.documentElement.scrollHeight};
          document.querySelector('#run-button')?.scrollIntoView({block:'end'});
          const buttonAfter=rect('#run-button');
          const navAfter=rect('.mobile-workspace-bar');
          return {viewport:{width:innerWidth,height:innerHeight},title:document.title,css:document.querySelector('link[href*="styles.css"]')?.getAttribute('href'),tool:document.querySelector('#tool-title')?.innerText||document.querySelector('h1')?.innerText||null,before,afterScroll:{button:buttonAfter,nav:navAfter,windowScrollY:scrollY,buttonAboveNav:!navAfter||buttonAfter.bottom<=navAfter.top},mainScroll:main?{scrollHeight:main.scrollHeight,clientHeight:main.clientHeight,scrollTop:main.scrollTop,paddingBottom:getComputedStyle(main).paddingBottom}:null,workspacePadding:work?getComputedStyle(work).paddingBottom:null,pageWidth:document.documentElement.scrollWidth};
        }''')
        results.append(measurements)
        page.screenshot(path=str(base / f'browser-self-found-cta-clearance-v214-{width}.png'), full_page=True)
        context.close()
    browser.close()
(base / 'browser-self-found-cta-clearance-v214.json').write_text(json.dumps({'results':results,'page_errors':errors},indent=2),encoding='utf-8')
print(json.dumps({'results':results,'page_errors':errors},indent=2))
