import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:8774"
OUT = Path(__file__).resolve().parent
FIXTURE = OUT / "fixtures" / "live-id1-synthetic-10page.pdf"


def main():
    errors = {"page": [], "console": [], "request": []}
    results = {}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 390, "height": 844}, accept_downloads=True)
        page.on("pageerror", lambda error: errors["page"].append(str(error)))
        page.on("console", lambda message: errors["console"].append(message.text) if message.type == "error" else None)
        page.on("requestfailed", lambda request: errors["request"].append({"url": request.url, "failure": request.failure}) if request.failure != "net::ERR_ABORTED" else None)

        page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
        page.locator("#btn-more-tools-trigger").click()
        page.get_by_role("button", name="Convert to / from PDF").click()
        page.locator("#convert-modal").wait_for(state="visible")
        page.locator("#convert-tab-from-pdf").click()
        formats = page.locator("#convert-format-grid .format-card").evaluate_all(
            "cards => cards.map(card => ({format: card.dataset.format, badge: card.querySelector('.format-icon')?.textContent.trim(), label: card.querySelector('.format-name')?.textContent.trim()}))"
        )
        expected = {
            "docx": ("DOC", "Word (.docx)"),
            "png": ("PNG", "PNG Images"),
            "webp": ("WEBP", "WebP Images"),
            "md": ("MD", "Markdown (.md)"),
            "txt": ("TXT", "Plain Text (.txt)"),
        }
        for card in formats:
            if card["format"] in expected:
                assert (card["badge"], card["label"]) == expected[card["format"]], card
        assert all(value in {card["format"] for card in formats} for value in expected)
        results["id362_format_cards"] = [card for card in formats if card["format"] in expected]
        page.screenshot(path=str(OUT / "browser-id362-conversion-format-cards.png"), full_page=True)

        page.goto(f"{BASE}/add-page-numbers-to-pdf", wait_until="domcontentloaded")
        page.locator("#file-input").set_input_files(str(FIXTURE))
        page.get_by_text("Page 1 of 10", exact=False).wait_for(timeout=20000)
        preview = page.locator("#mark_preview")
        results["id365_page_number_preview"] = {
            "text": preview.inner_text(),
            "page_count": preview.get_attribute("data-pdf-page-count"),
            "file_name": FIXTURE.name,
        }
        assert results["id365_page_number_preview"]["page_count"] == "10"
        page.screenshot(path=str(OUT / "browser-id365-page-number-preview-390.png"), full_page=True)
        page.locator(".delete-file-btn").click()
        page.wait_for_function("document.querySelector('#mark_preview')?.dataset.pdfPageCount === undefined")
        results["id365_removed_file_preview"] = {
            "text": preview.inner_text(),
            "page_count": preview.get_attribute("data-pdf-page-count"),
        }
        assert "selected PDF" in results["id365_removed_file_preview"]["text"]
        assert results["id365_removed_file_preview"]["page_count"] is None
        page.screenshot(path=str(OUT / "browser-id366-page-numbers-preview-390.png"), full_page=True)
        backgrounds = {
            "page_numbers": preview.evaluate(
                "el => ({backgroundImage: getComputedStyle(el).backgroundImage, backgroundColor: getComputedStyle(el).backgroundColor})"
            )
        }
        for route, operation in [("watermark-pdf", "watermark"), ("sign-pdf", "sign")]:
            page.goto(f"{BASE}/{route}", wait_until="domcontentloaded")
            mark = page.locator("#mark_preview")
            mark.wait_for(state="visible")
            backgrounds[operation] = mark.evaluate(
                "el => ({backgroundImage: getComputedStyle(el).backgroundImage, backgroundColor: getComputedStyle(el).backgroundColor})"
            )
            if operation == "watermark":
                page.screenshot(path=str(OUT / "browser-id366-watermark-preview-390.png"), full_page=True)
        results["id366_unknown_background"] = {}
        page.screenshot(path=str(OUT / "browser-id366-sign-preview-390.png"), full_page=True)
        for operation, background in backgrounds.items():
            assert "repeating-linear-gradient" in background["backgroundImage"], (operation, background)
            results["id366_unknown_background"][operation] = background
        browser.close()

    results["browser_errors"] = errors
    assert not any(errors.values()), errors
    (OUT / "browser-id362-365-366.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
