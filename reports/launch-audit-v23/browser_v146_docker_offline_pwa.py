"""Verify the v146 production shell, CSS and organizer load offline in Chromium."""
from __future__ import annotations
import json, os, re
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=os.environ.get('PAPERPLANE_DOCKER_BASE','http://127.0.0.1:18516')
IMAGE_ID=os.environ.get('PAPERPLANE_DOCKER_IMAGE_ID','not-supplied')
index=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
worker=(ROOT/'web'/'assets'/'service-worker.js').read_text(encoding='utf-8')
app_asset=re.search(r'/assets/app\.js\?v=\d+',index).group(0)
css_asset=re.search(r'/assets/styles\.css\?v=\d+',index).group(0)
organizer_asset=re.search(r'/assets/page_organizer\.js\?v=\d+',index).group(0)
cache_name=re.search(r"const CACHE_NAME = '([^']+)'",worker).group(1)
for asset in (app_asset,css_asset,organizer_asset):
    if f"'{asset}'" not in worker: raise AssertionError(f'{asset} missing from worker precache manifest')
rounds=[]
with sync_playwright() as p:
    browser=p.chromium.launch(channel='chrome',headless=True)
    for n in (1,2):
        context=browser.new_context(service_workers='allow',viewport={'width':390,'height':844},is_mobile=True,has_touch=True)
        page=context.new_page(); errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        response=page.goto(BASE+'/studio',wait_until='domcontentloaded',timeout=30000)
        assert response and response.status==200
        page.wait_for_function('navigator.serviceWorker.controller!==null',timeout=20000)
        page.wait_for_timeout(1200)
        cached=page.evaluate('''async name=>{const c=await caches.open(name);return {names:await caches.keys(),assets:(await c.keys()).map(r=>new URL(r.url).pathname+new URL(r.url).search)}}''',cache_name)
        assert cache_name in cached['names'] and all(a in cached['assets'] for a in (app_asset,css_asset,organizer_asset)),cached
        context.set_offline(True)
        offline=page.goto(BASE+'/',wait_until='domcontentloaded',timeout=20000)
        loaded=page.evaluate('''()=>({controller:!!navigator.serviceWorker.controller,title:document.title,
          app:document.querySelector('script[src*="app.js"]')?.getAttribute('src'),
          css:document.querySelector('link[rel="stylesheet"]')?.getAttribute('href'),
          organizer:[...document.scripts].some(s=>s.src.includes('page_organizer.js')),
          documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,
          viewportWidth:innerWidth,background:getComputedStyle(document.body).backgroundColor})''')
        result={'round':n,'cached':cached,'offline_status':offline.status if offline else None,'loaded':loaded,'page_errors':errors}
        rounds.append(result)
        assert offline and offline.status==200,result
        assert loaded['controller'] and loaded['app']==app_asset and loaded['css']==css_asset and loaded['organizer'],result
        assert loaded['documentWidth']<=392 and loaded['bodyWidth']<=392 and not errors,result
        context.close()
    browser.close()
report={'runtime':'current production-mode Docker image','image_id':IMAGE_ID,'cache_name':cache_name,
        'assets':{'app':app_asset,'css':css_asset,'organizer':organizer_asset},'offline_rounds':rounds}
(OUT/'browser-v146-docker-offline-pwa.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
