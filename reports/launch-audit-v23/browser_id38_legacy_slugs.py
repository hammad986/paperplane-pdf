from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper
OUT = Path(__file__).resolve().parent
ALIASES = {
    '/resize-photo': '/resize-image-dimensions',
    '/photo-resize': '/resize-image-dimensions',
    '/compress-photo': '/compress-image-online',
    '/add-page-numbers': '/add-page-numbers-to-pdf',
}

with TemporaryDirectory(prefix='paperplane-id38-slugs-') as temp:
    app, base, _identity = helper.start_server(Path(temp) / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        errors=[]
        rounds=[]
        with sync_playwright() as p:
            browser=p.chromium.launch(channel='chrome',headless=True)
            for run in (1,2):
                context=browser.new_context(viewport={'width':1366,'height':900})
                page=context.new_page()
                page.on('pageerror',lambda error:errors.append(str(error)))
                aliases=[]
                for source,canonical in ALIASES.items():
                    response=page.goto(base+source,wait_until='domcontentloaded')
                    page.wait_for_function('(expectedPath) => window.location.pathname === expectedPath',arg=canonical,timeout=10000)
                    aliases.append({'source':source,'http_status':response.status,'canonical_path':page.url.removeprefix(base),'page_title':page.title()})
                    assert response.status==200 and page.url.removeprefix(base)==canonical
                page.goto(base+'/tool-desk',wait_until='domcontentloaded')
                page.wait_for_function("document.querySelector('#tool-desk-tools-catalog')?.children.length > 0")
                internal_hrefs=page.locator('#tool-desk-tools-catalog a[href]').evaluate_all("els=>els.map(el=>new URL(el.href).pathname)")
                stale_internal_links=sorted(set(internal_hrefs).intersection(ALIASES))
                assert not stale_internal_links
                rounds.append({'round':run,'aliases':aliases,'stale_internal_links':stale_internal_links})
                context.close()
            browser.close()
        result={'rounds':rounds,'page_errors':errors}
        (OUT/'browser-id38-legacy-slugs.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print(json.dumps(result,indent=2))
        assert len(rounds)==2 and all(len(r['aliases'])==4 and not r['stale_internal_links'] for r in rounds) and not errors
    finally:
        app.terminate()
        app.wait(timeout=5)
