from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id244-quota-") as temp:
    root = Path(temp)
    source = root / "quota-compress.pdf"
    with fitz.open() as doc:
        page = doc.new_page()
        page.insert_text((72, 72), "Paid quota consistency fixture")
        doc.save(source)
    app, base, identity = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        token = identity["accounts"][0][1]  # Student Pro is a paid account with no daily cap.
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900}, accept_downloads=True)
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/compress-pdf", wait_until="domcontentloaded")
                page.wait_for_function("!document.body.classList.contains('auth-pending') && document.querySelector('#quota-text')?.textContent.includes('No daily operation cap')", timeout=20000)
                page.locator("#file-input").set_input_files(str(source))
                page.locator("#run-button").click()
                page.wait_for_function("document.querySelector('#result') && !document.querySelector('#result').hidden", timeout=30000)
                with page.expect_download(timeout=15000) as download_event:
                    page.locator("#result-download-link").click()
                download = download_event.value
                downloaded = root / f"quota-round-{round_no}.pdf"
                download.save_as(downloaded)
                with fitz.open(downloaded) as output:
                    assert len(output) == 1 and "Paid quota consistency fixture" in output[0].get_text()
                state = page.evaluate("""() => ({
                  header: document.querySelector('#quota-text')?.textContent.trim(),
                  settings: document.querySelector('#settings-quota-text')?.textContent.trim(),
                  badge: document.querySelector('#tool-tier-badge')?.textContent.trim(),
                  fillWidth: document.querySelector('#quota-fill')?.style.width,
                  fillClass: document.querySelector('#quota-fill')?.className
                })""")
                assert state["header"] == state["settings"] == "No daily operation cap", state
                assert "Student & Educator" in state["badge"] and "no daily operation cap" in state["badge"].lower(), state
                assert state["fillWidth"] == "0%" and "pro" in state["fillClass"], state
                assert not errors, errors
                results.append({"round": round_no, "operation": "compress", "download": download.suggested_filename, "content_checked": True, **state, "page_errors": errors})
                page.close()
                context.close()
            browser.close()
        (OUT / "browser-id244-paid-quota-consistency.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
