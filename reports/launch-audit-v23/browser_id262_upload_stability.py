from pathlib import Path
from tempfile import TemporaryDirectory
import fitz, json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path.cwd()
OUT = ROOT / "reports" / "launch-audit-v23"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id262-") as tmp:
    app, base, _ = helper.start_server(Path(tmp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        pdf = fitz.open()
        for n in range(10):
            pdf.new_page().insert_text((72, 72), f"Upload stability page {n + 1}")
        data = pdf.tobytes()
        pdf.close()
        rounds = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for n in (1, 2):
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                crashes = []
                page.on("crash", lambda: crashes.append("tab crashed"))
                page.on("pageerror", lambda error: crashes.append(str(error)))
                start = time.monotonic()
                response = page.goto(base + "/merge-pdf", wait_until="networkidle")
                assert response.status == 200
                page.locator("#file-input").set_input_files({
                    "name": "test-text-10page.pdf", "mimeType": "application/pdf", "buffer": data
                })
                page.wait_for_function("document.querySelector('#file-list')?.innerText.includes('test-text-10page.pdf')", timeout=10000)
                elapsed = round(time.monotonic() - start, 3)
                assert page.locator("#file-input").count() == 1 and not crashes, crashes
                assert "test-text-10page.pdf" in page.locator("#file-list").inner_text()
                rounds.append({"round": n, "uploaded_files": 1, "filename": "test-text-10page.pdf",
                               "elapsed_seconds": elapsed, "browser_crashes": crashes,
                               "page_open": not page.is_closed()})
                page.screenshot(path=str(OUT / f"id262-upload-round{n}.png"))
                page.close()
            browser.close()
        (OUT / "browser-id262-upload-stability.json").write_text(json.dumps(rounds, indent=2), encoding="utf-8")
        print(json.dumps(rounds, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
