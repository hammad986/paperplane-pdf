from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id355-edit-claims-") as temp:
    app, base, _identity = helper.start_server(Path(temp) / "data")
    try:
        port = int(base.rsplit(":", 1)[1])
        for _ in range(100):
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=.2):
                    break
            except OSError:
                time.sleep(.15)
        results = []
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            for round_no, viewport in enumerate(({"width": 1366, "height": 900}, {"width": 390, "height": 844}), 1):
                page = browser.new_page(viewport=viewport, is_mobile=viewport["width"] < 500, has_touch=viewport["width"] < 500)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                response = page.goto(base + "/edit-pdf", wait_until="domcontentloaded")
                assert response.status == 200
                page.locator("#tool-title").wait_for(state="visible", timeout=15000)
                title = page.locator("#tool-title").inner_text()
                seo = page.locator(".seo-content").inner_text()
                assert title == "Add Text & Stamps", title
                description = page.locator("#tool-description").inner_text()
                assert "Existing PDF text cannot be selected or replaced" in description, description
                faq = page.locator(".seo-faq-item").filter(has_text="Can I edit existing PDF text?")
                faq.locator("summary").click()
                answer = faq.locator("p").inner_text()
                assert answer == "No. Existing text cannot currently be selected, replaced, or rewritten. This tool adds new content over the page.", answer
                assert "Add Text, Stamps & Shapes to PDF Pages" in seo
                assert not errors, errors
                results.append({"round": round_no, "viewport": viewport, "tool_title": title, "existing_text_limitation": answer, "browser_errors": errors})
                if round_no == 2:
                    page.screenshot(path=str(OUT / "id355-honest-edit-mobile.png"))
                page.close()
            browser.close()
        (OUT / "browser-id355-edit-claims.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
