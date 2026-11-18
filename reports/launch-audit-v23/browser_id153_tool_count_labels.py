from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'reports'/'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id153-') as temp:
    app,base,_=helper.start_server(Path(temp)/'data')
    try:
        port=int(base.rsplit(':',1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1',port),timeout=.2): break
            except OSError: time.sleep(.15)
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for n in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page();errors=[]
                page.on('pageerror',lambda error:errors.append(str(error)))
                response=page.goto(base+'/tool-desk',wait_until='domcontentloaded')
                assert response and response.status==200
                page.wait_for_function("document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card').length === 41 && document.querySelector('#tool-desk-search-meta')?.textContent.includes('44')",timeout=15000)
                result=page.evaluate("""() => ({
                  totalLabel:document.querySelector('#view-tool-desk-directory .tool-category-badge')?.textContent.trim(),
                  searchMeta:document.querySelector('#tool-desk-search-meta')?.textContent.trim(),
                  cards:document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card').length,
                  categories:[...document.querySelectorAll('#tool-desk-tools-catalog .home-cat-section')].map(s=>({name:s.dataset.cat,count:s.querySelectorAll('.home-tool-card').length,label:s.querySelector('.home-cat-count')?.textContent.trim()})),
                  categoryTotals:[...document.querySelectorAll('#tool-desk-tools-catalog .home-cat-section')].map(s=>Number(s.querySelector('.home-cat-count')?.textContent.match(/\\d+/)?.[0]||0)),
                  aiWorkspaceNote:document.querySelector('#tool-desk-tools-catalog .tool-desk-ai-workspace-note')?.innerText,
                  allLabel:document.querySelector('#tool-desk-directory-filters [data-desk-category="all"]')?.textContent.trim(),
                  sidebarCounts:[...document.querySelectorAll('#category-nav .nav-category-tab')].map(b=>({category:b.dataset.category,count:Number(b.querySelector('.nav-cat-badge')?.textContent||0),label:b.innerText.trim()}))
                })""")
                assert result['totalLabel']=='44 PDF TOOLS' and result['searchMeta']=='44 tools available',result
                assert result['cards']==41 and result['categoryTotals']==[7,3,12,8,6,4,4],result
                assert result['allLabel']=='All 44 Tools' and sum(x['count'] for x in result['sidebarCounts'])==44,result
                assert 'Smart Metadata' in result['aiWorkspaceNote'] and 'Executive Brief' in result['aiWorkspaceNote'],result
                page.locator('#tool-desk-directory-filters [data-desk-category="ai"]').click()
                ai_category=page.evaluate("""() => ({meta:document.querySelector('#tool-desk-search-meta')?.textContent.trim(),count:document.querySelector('#tool-desk-tools-catalog .home-cat-count')?.textContent.trim(),cards:document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card').length,note:document.querySelector('#tool-desk-tools-catalog .tool-desk-ai-workspace-note')?.innerText})""")
                assert ai_category['meta']=='4 tools available' and ai_category['count']=='4 tools' and ai_category['cards']==1,ai_category
                page.locator('#tool-desk-search').fill('Smart Metadata')
                page.wait_for_function("document.querySelector('#tool-desk-search-meta')?.textContent.includes('1 tool found')",timeout=5000)
                ai_search=page.evaluate("""() => ({meta:document.querySelector('#tool-desk-search-meta')?.textContent.trim(),cards:document.querySelectorAll('#tool-desk-tools-catalog .home-tool-card').length,note:document.querySelector('#tool-desk-tools-catalog .tool-desk-ai-workspace-note')?.innerText})""")
                assert ai_search['meta']=='1 tool found for “Smart Metadata”' and ai_search['cards']==0 and 'Open AI Intelligence' in ai_search['note'],ai_search
                assert not errors,(result,errors)
                rounds.append({'round':n,'toolDesk':result,'aiCategory':ai_category,'aiSearch':ai_search,'pageErrors':errors})
                context.close()
            browser.close()
        evidence={'rounds':rounds}
        (OUT/'browser-id153-tool-count-labels.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
        print(json.dumps(evidence,indent=2))
    finally:
        app.terminate();app.wait(timeout=5)
