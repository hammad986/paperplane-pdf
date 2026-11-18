from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from zipfile import ZipFile
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id85-") as temp:
    root = Path(temp)
    sources = helper.documents(root)
    app, base, _ = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        rounds = []
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no, width in ((1, 320), (2, 390)):
                context = browser.new_context(viewport={"width": width, "height": 844}, is_mobile=True,
                                              has_touch=True, accept_downloads=True)
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                ops = []
                for slug, source, options in (
                    ("split-pdf", sources[0], {"split_mode": "all_pages"}),
                    ("rotate-pdf", sources[0], {"degrees": "90"}),
                ):
                    page.goto(base + "/" + slug, wait_until="domcontentloaded")
                    page.locator("#file-input").set_input_files(str(source))
                    page.wait_for_function("document.querySelector('#file-list')?.children.length > 0")
                    for selector, value in options.items():
                        control = page.locator(f"#{selector}")
                        if control.count():
                            control.select_option(value)
                    page.locator("#run-button").click()
                    page.wait_for_function("document.querySelector('#result-download-link')?.hidden === false", timeout=60000)
                    result_box = page.locator("#result")
                    result_box.scroll_into_view_if_needed()
                    metrics = result_box.evaluate("""el => {
                      const nav = document.querySelector('.mobile-workspace-bar');
                      const run = document.querySelector('#run-button');
                      const rect = e => { const r=e.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}; };
                      const overlaps = (a,b) => a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top;
                      const actions = [...el.querySelectorAll('.result-actions a, .result-actions button, #result-download-link, #result-view-studio-btn')]
                        .filter(x => !x.hidden && x.getBoundingClientRect().width > 0)
                        .map(x => { const r=rect(x), hit=document.elementFromPoint((r.left+r.right)/2,(r.top+r.bottom)/2); return {text:x.innerText.trim(),rect:r,withinViewport:r.left>=0&&r.right<=innerWidth&&r.top>=0&&r.bottom<=innerHeight,notCovered:hit===x||x.contains(hit),minHeight:r.height}; });
                      const navRect=nav?rect(nav):null;
                      const runRect=run&&!run.hidden?rect(run):null;
                      return {result:rect(el),actions,nav:navRect,run:runRect,documentWidth:document.documentElement.scrollWidth};
                    }""")
                    # Force the same real toast component used by completion/error paths.
                    page.evaluate("window.showToast('ID 85 overlap probe', 'success', 5000)")
                    toast = page.locator(".toast-notice").last
                    toast.wait_for(state="visible")
                    toast_geometry = toast.evaluate("""el => {
                      const r=el.getBoundingClientRect(), nav=document.querySelector('.mobile-workspace-bar')?.getBoundingClientRect(), run=document.querySelector('#run-button')?.getBoundingClientRect();
                      const overlap=b=>!!b&&r.left<b.right&&r.right>b.left&&r.top<b.bottom&&r.bottom>b.top;
                      return {rect:{left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height},overlapsNav:overlap(nav),overlapsRun:overlap(run)};
                    }""")
                    with page.expect_download(timeout=30000) as event:
                        page.locator("#result-download-link").click()
                    download = event.value
                    output_path = root / download.suggested_filename
                    download.save_as(output_path)
                    if slug == "split-pdf":
                        with ZipFile(output_path) as archive:
                            pages = []
                            for name in archive.namelist():
                                with fitz.open(stream=archive.read(name), filetype="pdf") as output:
                                    assert output.page_count == 1
                                    pages.append(output[0].get_text().strip())
                        assert len(pages) == 2 and all("Synthetic v13 acceptance page" in p for p in pages)
                    else:
                        with fitz.open(output_path) as output:
                            assert output.page_count == 2
                            assert all(p.rotation == 90 for p in output)
                            assert all("Synthetic v13 acceptance page" in p.get_text() for p in output)
                    ops.append({"slug":slug,"download":download.suggested_filename,
                                "content_checked":True,"result_metrics":metrics,
                                "toast_geometry":toast_geometry})
                assert not errors, errors
                for op in ops:
                    assert op["result_metrics"]["documentWidth"] == width
                    assert op["result_metrics"]["actions"]
                    assert all(a["withinViewport"] and a["notCovered"] and a["minHeight"] >= 44 for a in op["result_metrics"]["actions"])
                    assert not op["toast_geometry"]["overlapsNav"] and not op["toast_geometry"]["overlapsRun"]
                page.screenshot(path=str(OUT / f"id85-mobile-result-round{round_no}.png"), full_page=True)
                rounds.append({"round":round_no,"viewport":{"width":width,"height":844},"operations":ops,"page_errors":errors})
                context.close()
            browser.close()
        result={"rounds":rounds}
        (OUT / "browser-id85-mobile-result-cards.json").write_text(json.dumps(result,indent=2),encoding="utf-8")
        print(json.dumps(result,indent=2))
    finally:
        app.terminate()
        try: app.wait(timeout=5)
        except Exception: app.kill(); app.wait(timeout=5)
