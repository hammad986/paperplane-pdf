"""Verify v160's offline shell and a real browser-local PDF merge in Chromium."""
from __future__ import annotations
import json, os, re
from pathlib import Path
from tempfile import TemporaryDirectory
import fitz
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
BASE=os.environ.get('PAPERPLANE_DOCKER_BASE','http://127.0.0.1:18524')
IMAGE_ID=os.environ.get('PAPERPLANE_DOCKER_IMAGE_ID','not-supplied')
SOURCE=Path('C:/Users/mdham/Downloads/notes.pdf')
assert SOURCE.exists(), SOURCE
index=(ROOT/'web'/'index.html').read_text(encoding='utf-8')
worker=(ROOT/'web'/'assets'/'service-worker.js').read_text(encoding='utf-8')
app_asset=re.search(r'/assets/app\.js\?v=\d+',index).group(0)
css_asset=re.search(r'/assets/styles\.css\?v=\d+',index).group(0)
organizer_asset=re.search(r'/assets/page_organizer\.js\?v=\d+',index).group(0)
runtime_asset=re.search(r'/assets/pdf_runtime\.js\?v=\d+',index).group(0)
render_worker_asset=re.search(r'/assets/studio_render_worker\.js\?v=\d+',worker).group(0)
cache_name=re.search(r"const CACHE_NAME = '([^']+)'",worker).group(1)
pdf_assets=('/assets/pdf.min.js','/assets/pdf.worker.min.js','/assets/pdf-lib.min.js','/assets/local_pdf_worker.js?v=26')
for asset in (app_asset,css_asset,organizer_asset,runtime_asset,render_worker_asset,*pdf_assets):
    if f"'{asset}'" not in worker: raise AssertionError(f'{asset} missing from worker precache manifest')
rounds=[]
with TemporaryDirectory(prefix='paperplane-v160-offline-pdf-') as temp:
    temp=Path(temp)
    sources=[]
    for filename,marker in (('offline-a.pdf','OFFLINE-LOCAL-A'),('offline-b.pdf','OFFLINE-LOCAL-B')):
        source=temp/filename
        with fitz.open() as document:
            document.new_page().insert_text((72,72),marker)
            document.save(source)
        sources.append(source)
    with sync_playwright() as p:
        browser=p.chromium.launch(channel='chrome',headless=True)
        for n in (1,2):
            context=browser.new_context(service_workers='allow',viewport={'width':390,'height':844},is_mobile=True,
                                        has_touch=True,accept_downloads=True)
            page=context.new_page(); errors=[]
            page.on('pageerror',lambda e:errors.append(str(e)))
            response=page.goto(BASE+'/studio',wait_until='domcontentloaded',timeout=30000)
            assert response and response.status==200
            page.wait_for_function('navigator.serviceWorker.controller!==null',timeout=20000)
            page.wait_for_timeout(1200)
            cached=page.evaluate('''async name=>{const c=await caches.open(name);return {names:await caches.keys(),assets:(await c.keys()).map(r=>new URL(r.url).pathname+new URL(r.url).search)}}''',cache_name)
            assert cache_name in cached['names'] and all(a in cached['assets'] for a in (app_asset,css_asset,organizer_asset,runtime_asset,render_worker_asset,*pdf_assets)),cached
            context.set_offline(True)
            offline=page.goto(BASE+'/',wait_until='domcontentloaded',timeout=20000)
            loaded=page.evaluate('''()=>({controller:!!navigator.serviceWorker.controller,title:document.title,
              app:document.querySelector('script[src*="app.js"]')?.getAttribute('src'),
              css:document.querySelector('link[rel="stylesheet"]')?.getAttribute('href'),
              organizer:[...document.scripts].some(s=>s.src.includes('page_organizer.js')),
              documentWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,
              viewportWidth:innerWidth,background:getComputedStyle(document.body).backgroundColor})''')
            assert offline and offline.status==200, {'round':n,'offline_status':offline.status if offline else None}
            assert loaded['controller'] and loaded['app']==app_asset and loaded['css']==css_asset and loaded['organizer'],loaded
            assert loaded['documentWidth']<=392 and loaded['bodyWidth']<=392,loaded

            merge_route=page.goto(BASE+'/merge-pdf',wait_until='domcontentloaded',timeout=20000)
            assert merge_route and merge_route.status==200
            assert page.locator('#client-privacy-toggle').is_checked()
            page.locator('#file-input').set_input_files([str(path) for path in sources])
            page.wait_for_function("!document.querySelector('#run-button').disabled",timeout=20000)
            page.locator('#run-button').click()
            page.locator('#result-download-link:not([hidden])').wait_for(state='visible',timeout=30000)
            with page.expect_download(timeout=15000) as download:
                page.locator('#result-download-link').click()
            output=temp/f'round-{n}-merged.pdf'
            download.value.save_as(output)
            with fitz.open(output) as merged:
                text=[pdf_page.get_text() for pdf_page in merged]
                assert len(merged)==2 and 'OFFLINE-LOCAL-A' in text[0] and 'OFFLINE-LOCAL-B' in text[1],text
            job_posts=page.evaluate("performance.getEntriesByType('resource').filter(entry=>entry.name.includes('/api/jobs')).length")
            assert job_posts==0 and not errors,{'job_posts':job_posts,'page_errors':errors}
            studio_route=page.goto(BASE+'/studio',wait_until='domcontentloaded',timeout=20000)
            assert studio_route and studio_route.status==200
            page.locator('#studio-file-input').set_input_files(str(output))
            page.wait_for_function("""() => document.querySelector('#page-total-indicator')?.textContent.trim()==='2'
              && !!state.studio.renderSession && !state.studio.renderWorkerDisabled""",timeout=45000)
            page.wait_for_function("document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'",timeout=30000)
            studio_state=page.evaluate("""() => ({pages:document.querySelector('#page-total-indicator')?.textContent.trim(),
              workerActive:!!state.studio.renderSession,workerDisabled:state.studio.renderWorkerDisabled,
              width:document.documentElement.scrollWidth,viewport:innerWidth})""")
            assert studio_state['pages']=='2' and studio_state['workerActive'] and not studio_state['workerDisabled'],studio_state
            assert studio_state['width']<=392 and not errors,{'studio':studio_state,'page_errors':errors}
            large_studio_route=page.goto(BASE+'/studio',wait_until='domcontentloaded',timeout=20000)
            assert large_studio_route and large_studio_route.status==200
            page.locator('#studio-file-input').set_input_files(str(SOURCE))
            page.wait_for_function("""() => document.querySelector('#page-total-indicator')?.textContent.trim()==='69'
              && document.querySelector('.studio-page-sheet[data-page=\"1\"] .pdf-page-canvas')?.dataset.rendered==='true'
              && !!state.studio.renderSession && !state.studio.renderWorkerDisabled""",timeout=90000)
            page.locator('.studio-page-sheet[data-page="40"]').scroll_into_view_if_needed()
            page.wait_for_function("""() => state.studio.currentPage>=39 && state.studio.currentPage<=41
              && document.querySelector('.studio-page-sheet[data-page=\"40\"] .pdf-page-canvas')?.dataset.rendered==='true'""",timeout=45000)
            large_studio=page.evaluate("""() => ({pages:document.querySelector('#page-total-indicator')?.textContent.trim(),
              workerActive:!!state.studio.renderSession,workerDisabled:state.studio.renderWorkerDisabled,
              currentPage:state.studio.currentPage,width:document.documentElement.scrollWidth,viewport:innerWidth})""")
            assert large_studio['pages']=='69' and large_studio['workerActive'] and not large_studio['workerDisabled'],large_studio
            assert large_studio['currentPage'] in (39,40,41) and large_studio['width']<=392,large_studio
            assert not errors,errors
            rounds.append({'round':n,'offline_shell_status':offline.status,'merge_route_status':merge_route.status,
                           'worker_cache_entries':len(cached['assets']),'offline_merge_bytes':output.stat().st_size,
                           'pages':2,'text_order_preserved':True,'server_job_posts':job_posts,
                           'offline_studio_route_status':studio_route.status,'offline_studio_worker':studio_state,
                           'offline_studio_large_pdf':large_studio,'offline_page40_rendered':True,
                           'page_errors':errors})
            context.close()
        browser.close()
report={'runtime':'current production-mode Docker image','image_id':IMAGE_ID,'cache_name':cache_name,
        'assets':{'app':app_asset,'css':css_asset,'organizer':organizer_asset,'pdf_runtime':runtime_asset,
                  'studio_render_worker':render_worker_asset,'pdf_dependencies':list(pdf_assets)},
        'offline_rounds':rounds,'cold_offline_local_merge_passed':len(rounds)==2 and all(row['text_order_preserved'] for row in rounds),
        'offline_studio_worker_passed':len(rounds)==2 and all(row['offline_studio_worker']['workerActive'] and not row['offline_studio_worker']['workerDisabled'] for row in rounds),
        'offline_large_pdf_studio_passed':len(rounds)==2 and all(row['offline_studio_large_pdf']['pages']=='69' and row['offline_page40_rendered'] for row in rounds)}
(OUT/'browser-v160-docker-offline-pwa.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
