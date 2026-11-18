from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
import fitz
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id356-batch-") as temp:
    root = Path(temp)
    inputs = []
    for index in range(11):
        path = root / f"batch-{index + 1}.pdf"
        with fitz.open() as doc:
            doc.new_page().insert_text((72, 72), f"Batch fixture {index + 1}")
            doc.save(path)
        inputs.append(path)
    app, base, identity = helper.start_server(root / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        token = identity["accounts"][0][1]
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                context = browser.new_context(viewport={"width": 1366, "height": 900})
                context.add_cookies([{"name": "paperplane_token", "value": token, "url": base, "httpOnly": True}])
                page = context.new_page()
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/merge-pdf", wait_until="domcontentloaded")
                page.wait_for_function("document.querySelector('#file-hint')?.textContent.includes('up to 10 PDF files')", timeout=15000)
                hint = page.locator("#file-hint").inner_text()
                page.locator("#file-input").set_input_files([str(item) for item in inputs])
                page.wait_for_function("[...document.querySelectorAll('.toast-notice')].some(x=>x.textContent.includes('up to 10 files'))", timeout=15000)
                feedback = page.locator(".toast-notice").inner_text()
                assert "up to 10 files" in feedback, feedback
                assert page.locator("#run-button").is_disabled(), "over-limit input must not enable Run"
                assert "10 PDF files" in hint
                assert not errors, errors
                results.append({"round": round_no, "plan": "Student Pro", "hint": hint, "selected_files": 11, "ui_rejection": feedback, "run_disabled": True, "page_errors": errors})
                if round_no == 2:
                    page.screenshot(path=str(OUT / "id356-student-batch-limit-round2.png"))
                context.close()
            browser.close()
        (OUT / "browser-id356-student-batch-limit.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
