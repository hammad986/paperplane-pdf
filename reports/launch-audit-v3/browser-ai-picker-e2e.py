from __future__ import annotations

import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
PDF = str(Path("web/assets/sample_document.pdf").resolve())


def main() -> None:
    results = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        for width, height, name in [(1440, 1000, "desktop"), (375, 812, "phone")]:
            context = browser.new_context(
                viewport={"width": width, "height": height},
                is_mobile=width < 600,
                has_touch=width < 600,
            )
            page = context.new_page()
            page_errors: list[str] = []
            page.on("pageerror", lambda error: page_errors.append(str(error)))
            page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
            page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(
                state="attached", timeout=20_000
            )
            nav = page.locator("#mob-nav-ai" if width < 600 else "#tab-ai-view")
            if width < 600:
                nav.tap()
            else:
                nav.click()
            page.locator("#view-ai-studio").wait_for(state="visible", timeout=10_000)

            started = time.monotonic()
            with page.expect_file_chooser(timeout=10_000) as chooser_event:
                button = page.locator("#ai-upload-btn")
                button.tap() if width < 600 else button.click()
            chooser = chooser_event.value
            chooser.set_files(PDF)
            page.locator("#ai-doc-name").wait_for(state="visible", timeout=10_000)
            page.locator("#ai-doc-name").get_by_text("sample_document.pdf")
            if page.locator("#ai-doc-name").inner_text().strip() != "sample_document.pdf":
                raise AssertionError(f"{name}: chooser selected the wrong document")

            page.locator("#chat-input").fill("What does page 1 say about Advanced PDF Studio?")
            page.locator("#chat-send-btn").click()
            page.get_by_text("Complete", exact=True).last.wait_for(timeout=20_000)
            answer = page.locator(".ai-stream-text").last.inner_text()
            citations = [tag.inner_text() for tag in page.locator(".ai-citation-tag").all()]
            mode = page.locator(".ai-response-mode").last.inner_text()
            result = {
                "device_profile": name,
                "viewport": width,
                "file_chooser_event": True,
                "filename_loaded": page.locator("#ai-doc-name").inner_text().strip(),
                "answer": answer,
                "citations": citations,
                "mode": mode,
                "elapsed_seconds": round(time.monotonic() - started, 2),
                "page_errors": page_errors,
            }
            page.screenshot(path=f"reports/launch-audit-v3/{name}-picker-answer.png")
            if "verified test page #1" not in answer.lower() or not citations or page_errors:
                raise AssertionError(f"{name}: file-to-grounded-answer flow failed: {result}")
            results.append(result)
            context.close()
        browser.close()

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    Path("reports/launch-audit-v3").mkdir(parents=True, exist_ok=True)
    main()
