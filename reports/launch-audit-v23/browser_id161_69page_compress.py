from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
FIXTURE = ROOT / "reports" / "launch-audit-v8" / "test-files" / "notes-69page.pdf"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id161-compress-") as temp:
    app, base, identity = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        source_bytes = FIXTURE.stat().st_size
        with fitz.open(FIXTURE) as source:
            assert len(source) == 69
            marker = source[0].get_text().splitlines()[0]
        token = identity["accounts"][0][1]
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.on("dialog", lambda dialog: dialog.accept())
                page.goto(base + "/compress-pdf", wait_until="domcontentloaded")
                page.wait_for_function("state.operation==='compress' && document.querySelector('#preset')")
                page.locator("#preset").select_option("100kb")
                page.locator("#file-input").set_input_files(str(FIXTURE))
                page.wait_for_function("!document.querySelector('#run-button').disabled", timeout=30000)
                page.locator("#run-button").click()
                page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden", timeout=90000)
                with page.expect_download(timeout=30000) as download_event:
                    page.locator("#result-download-link").click()
                download = download_event.value
                output = Path(temp) / f"id161-round{round_no}.pdf"
                download.save_as(output)
                with fitz.open(output) as result:
                    assert len(result) == 69, len(result)
                    text = "\n".join(page.get_text() for page in result)
                    assert marker in text, marker
                output_bytes = output.stat().st_size
                result_meta = page.locator("#result-meta").inner_text()
                target_warning = "requested target could not be reached" in result_meta.lower()
                assert output_bytes < 100 * 1024 or target_warning, {"output_bytes": output_bytes, "result_meta": result_meta}
                assert not errors, errors
                results.append({"round": round_no, "source_bytes": source_bytes, "source_pages": 69, "output_bytes": output_bytes, "output_pages": 69, "source_marker_preserved": marker in text, "preset": "100kb", "target_reached": output_bytes < 100 * 1024, "missed_target_warning_visible": target_warning, "result_meta": result_meta, "browser_download": download.suggested_filename, "page_errors": errors})
                page.screenshot(path=str(OUT / f"id161-compress-round{round_no}.png"))
                context.close()
            browser.close()
        (OUT / "browser-id161-69page-compress.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
