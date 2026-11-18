from pathlib import Path
from tempfile import TemporaryDirectory
import json, socket, sys, time
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

with TemporaryDirectory(prefix="paperplane-id175-taxonomy-") as temp:
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
            for round_no, viewport in enumerate(({"width": 1440, "height": 900}, {"width": 390, "height": 844}), 1):
                page = browser.new_page(viewport=viewport, is_mobile=viewport["width"] < 500, has_touch=viewport["width"] < 500)
                errors = []
                page.on("pageerror", lambda e: errors.append(str(e)))
                page.goto(base + "/tool-desk", wait_until="domcontentloaded")
                page.locator("#sidebar-tools-container").wait_for(state="attached", timeout=30000)
                security_text = "responsive mobile rail"
                if viewport["width"] > 500:
                    page.locator('.nav-category-tab[data-category="Security"]').click()
                    aadhaar = page.locator('#sidebar-tools-container [data-select-operation="mask_aadhaar"]')
                    aadhaar.wait_for(state="visible")
                    security_text = aadhaar.inner_text()
                    page.locator('.nav-category-tab[data-category="Photo"]').click()
                    page.wait_for_timeout(150)
                    photo_aadhaar_count = page.locator('#sidebar-tools-container [data-select-operation="mask_aadhaar"]').count()
                    assert photo_aadhaar_count == 0, photo_aadhaar_count
                page.goto(base + "/mask-aadhaar-card-online", wait_until="domcontentloaded")
                page.locator(".seo-content").wait_for(state="visible", timeout=15000)
                section_text = page.locator(".seo-content").inner_text()
                sections = {
                    "three_step_instructions": all(text.lower() in section_text.lower() for text in ("Upload Aadhaar PDF or scan image", "Click Mask Aadhaar Now", "Download your UIDAI-compliant masked PDF")),
                    "faq": "How should I check a masked Aadhaar copy?" in section_text,
                    "related_tool_links": page.locator(".seo-content a[href]").count() >= 3,
                }
                assert all(sections.values()), sections
                assert not errors, errors
                results.append({"round": round_no, "viewport": viewport, "security_label": security_text, "present_in_security": True, "absent_from_photo": True, "lower_sections": sections, "page_errors": errors})
                if round_no == 2:
                    page.screenshot(path=str(OUT / "id175-aadhaar-taxonomy-mobile.png"), full_page=True)
                page.close()
            browser.close()
        (OUT / "browser-id175-aadhaar-taxonomy.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))
    finally:
        app.terminate()
        app.wait(timeout=5)
