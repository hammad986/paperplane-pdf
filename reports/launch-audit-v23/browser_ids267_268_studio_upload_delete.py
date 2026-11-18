from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

results = []
for round_no in (1, 2):
    with TemporaryDirectory(prefix=f"paperplane-ids267-268-{round_no}-") as tmp:
        root = Path(tmp)
        source = root / "studio-ten-pages.pdf"
        pdf = fitz.open()
        for number in range(1, 11):
            pdf.new_page().insert_text((72, 72), f"Studio page {number} unique marker {number}")
        pdf.save(source)
        pdf.close()
        app, base, _ = helper.start_server(root / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=.2):
                        break
                except OSError:
                    time.sleep(.15)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                errors = []
                page.on("pageerror", lambda error: errors.append(str(error)))
                page.goto(base + "/studio", wait_until="networkidle")
                page.locator("#studio-file-input").set_input_files(str(source))
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '10' && document.querySelector('#studio-loading-overlay')?.hidden === true", timeout=25000)
                load_text = page.locator("#studio-toast-container").inner_text() if page.locator("#studio-toast-container").count() else ""
                assert "Failed to load PDF in Studio" not in load_text and not errors, (load_text, errors)
                page.evaluate("window.confirmAction = async () => true")
                page.locator("#editor-delete-page-btn").click()
                page.wait_for_function("document.querySelector('#page-total-indicator')?.textContent === '9'", timeout=20000)
                toast = page.locator("#toast-container").inner_text() if page.locator("#toast-container").count() else ""
                assert "Cannot delete all pages" not in toast and not errors, (toast, errors)
                results.append({"round": round_no, "upload_pages": 10, "load_failure_toast": False,
                                "toolbar_delete_result_pages": 9, "bogus_last_page_warning": False,
                                "page_errors": errors})
                page.screenshot(path=str(OUT / f"ids267-268-studio-round{round_no}.png"))
                page.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=5)

(OUT / "browser-ids267-268-studio-upload-delete.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
print(json.dumps(results, indent=2))
