from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports' / 'launch-audit-v14'))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix='paperplane-id312-') as temp:
    root = Path(temp)
    pdf_path = root / 'tablet-layout.pdf'
    with fitz.open() as doc:
        for number in range(1, 6):
            page = doc.new_page(width=612, height=792)
            page.insert_text((72, 100), f'ID 312 tablet layout page {number}')
        doc.save(pdf_path)
    app, base, _ = helper.start_server(root / 'data')
    try:
        port = int(base.rsplit(':', 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel='chrome', headless=True)
            for round_number in (1, 2):
                for width, height in ((820, 1180), (390, 844), (360, 800), (320, 740)):
                    context = browser.new_context(viewport={'width': width, 'height': height}, is_mobile=width <= 900, has_touch=width <= 900)
                    page = context.new_page()
                    errors = []
                    page.on('pageerror', lambda error: errors.append(str(error)))
                    page.goto(base + '/studio', wait_until='domcontentloaded')
                    page.locator('#studio-file-input').set_input_files(str(pdf_path))
                    page.wait_for_function("document.querySelector('#pdf-canvas')?.dataset.rendered === 'true'", timeout=20000)
                    metrics = page.evaluate("""() => {
                      const rect = s => { const e = document.querySelector(s); if (!e) return null; const r = e.getBoundingClientRect(); const c = getComputedStyle(e); return {x:Math.round(r.x),y:Math.round(r.y),width:Math.round(r.width),height:Math.round(r.height),display:c.display,visible:r.width>0&&r.height>0}; };
                      const canvas=rect('#pdf-canvas'), toolbar=rect('#studio-toolbar'), thumbs=rect('#studio-thumbnails-bar');
                      const bottom=rect('.mobile-workspace-bar');
                      const ribbons=[...document.querySelectorAll('#studio-toolbar .studio-primary-ribbon, #studio-toolbar .studio-sub-ribbon')].map(e=>({clientWidth:e.clientWidth,scrollWidth:e.scrollWidth,clientHeight:e.clientHeight,scrollHeight:e.scrollHeight}));
                      return {viewport:{width:innerWidth,height:innerHeight,scrollWidth:document.documentElement.scrollWidth},canvas,toolbar,thumbnails:thumbs,bottom,ribbons,first_screen_canvas:!!canvas&&canvas.y<innerHeight&&canvas.y+canvas.height>0};
                    }""")
                    assert metrics['first_screen_canvas'], (width, metrics)
                    assert metrics['viewport']['scrollWidth'] <= width, metrics
                    assert metrics['canvas']['y'] < height, (width, metrics)
                    assert metrics['canvas']['y'] + metrics['canvas']['height'] <= metrics['bottom']['y'], (width, metrics)
                    if width <= 390:
                        assert 100 <= metrics['toolbar']['height'] <= 140, metrics
                        assert len(metrics['ribbons']) == 2 and all(r['scrollHeight'] - r['clientHeight'] <= 2 for r in metrics['ribbons']), metrics
                        page.screenshot(path=str(OUT / f'id312-studio-{width}-round{round_number}-start.png'), full_page=True)
                        reachability = page.evaluate("""() => {
                          const rail=document.querySelector('#studio-toolbar .studio-sub-ribbon');
                          const target=document.querySelector('#tool-stamp-btn');
                          rail.scrollTo({left:rail.scrollWidth,behavior:'instant'});
                          const clip=rail.getBoundingClientRect(), r=target.getBoundingClientRect();
                          return {rail:{clientWidth:rail.clientWidth,scrollWidth:rail.scrollWidth,scrollLeft:rail.scrollLeft},target:{left:r.left,right:r.right,inside:r.left>=clip.left&&r.right<=clip.right}};
                        }""")
                        assert reachability['rail']['scrollWidth'] > reachability['rail']['clientWidth'], reachability
                        assert reachability['target']['inside'], reachability
                        metrics['last_tool_reachability'] = reachability
                        primary_reachability = page.evaluate("""() => {
                          const rail=document.querySelector('#studio-toolbar .studio-primary-ribbon');
                          const target=document.querySelector('#studio-clear-pdf-btn');
                          rail.scrollTo({left:rail.scrollWidth,behavior:'instant'});
                          const clip=rail.getBoundingClientRect(), r=target.getBoundingClientRect();
                          return {rail:{clientWidth:rail.clientWidth,scrollWidth:rail.scrollWidth,scrollLeft:rail.scrollLeft},target:{left:r.left,right:r.right,inside:r.left>=clip.left&&r.right<=clip.right}};
                        }""")
                        assert primary_reachability['target']['inside'], primary_reachability
                        metrics['primary_last_tool_reachability'] = primary_reachability
                        page.evaluate("""() => document.querySelectorAll('.studio-primary-ribbon,.studio-sub-ribbon').forEach(e=>e.scrollTo({left:0,behavior:'instant'}))""")
                    assert not errors, errors
                    page.screenshot(path=str(OUT / f'id312-studio-{width}-round{round_number}.png'), full_page=True)
                    results.append({'round':round_number,'viewport':width,'metrics':metrics,'page_errors':errors})
                    context.close()
            browser.close()
        result = {'rounds': results}
        (OUT / 'browser-id312-studio-tablet-layout.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
