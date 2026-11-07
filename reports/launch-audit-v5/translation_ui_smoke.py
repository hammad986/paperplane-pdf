from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
REPORT_DIR = Path(__file__).resolve().parent
SOURCE_PDF = REPORT_DIR / "phase0_color-audit_merge.pdf"
BASE_URL = "http://127.0.0.1:8501"


def main() -> None:
    errors: list[str] = []
    results: list[dict] = []
    mocked_modes: list[str] = []
    response_headers: list[dict] = []
    payload = SOURCE_PDF.read_bytes()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1366, "height": 900})
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.on("requestfailed", lambda request: errors.append(f"{request.method} {request.url}: {request.failure}"))
        page.on("response", lambda response: response_headers.append(response.headers) if "/api/ai/translate" in response.url else None)

        page.goto(f"{BASE_URL}/translate-pdf", wait_until="domcontentloaded")
        page.locator("#options select#target_language").wait_for(timeout=10000)
        page.evaluate(
            """({pdfHex}) => {
              const bytes = Uint8Array.from(pdfHex.match(/.{2}/g), pair => parseInt(pair, 16));
              state.operation = 'translate';
              state.clientSideMode = false;
              state.operations.translate.available = true;
              state.operations.translate.status = 'AVAILABLE';
              state.files = [new File([bytes], 'translation-ui-test.pdf', { type: 'application/pdf' })];
              document.querySelector('#tool-availability-notice').hidden = true;
              renderFiles();
              updateButton();
            }""",
            {"pdfHex": payload.hex()},
        )

        def make_fulfill(current_mode: str):
            def fulfill(route):
                mocked_modes.append(current_mode)
                route.fulfill(
                    status=200,
                    body=payload,
                    headers={
                        "Content-Type": "application/pdf",
                        "X-Paperplane-Translation-Mode": current_mode,
                        "X-Paperplane-Translation-Warnings": "1",
                    },
                    )
            return fulfill

        for mode in ("failed", "partial"):
            fulfill = make_fulfill(mode)
            page.route("**/api/ai/translate", fulfill)
            page.locator("#run-button").click()
            try:
                page.locator("#result-title").wait_for(timeout=10000)
            except Exception:
                (REPORT_DIR / "translation-ui-debug.html").write_text(page.content(), encoding="utf-8")
                page.screenshot(path=str(REPORT_DIR / "translation-ui-debug.png"), full_page=True)
                print(json.dumps({"mode": mode, "url": page.url, "button": page.locator("#run-button").inner_text(), "file_list": page.locator("#file-list").inner_text(), "options": page.locator("#options").inner_text(), "body": page.locator("body").inner_text()[-2500:], "errors": errors}, indent=2))
                raise
            download = page.locator(".btn-download:visible")
            result = {
                "mode": mode,
                "heading": page.locator("#result-title").inner_text(),
                "download_links": download.count(),
                "download_label": download.first.inner_text() if download.count() else None,
            }
            results.append(result)
            page.unroute("**/api/ai/translate", fulfill)

        browser.close()

    report = {"url": f"{BASE_URL}/translate-pdf", "mocked_modes": mocked_modes, "response_headers": response_headers, "results": results, "page_or_console_errors": errors}
    (REPORT_DIR / "translation-ui-smoke.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if errors or results[0]["download_links"] != 0 or results[1]["download_label"] != "Download partial translation":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
