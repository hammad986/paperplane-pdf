import json
import time
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASE = "http://127.0.0.1:8774"
FIXTURE = ROOT / "reports" / "launch-audit-v23" / "fixtures" / "v23-id2-69-pages.pdf"


def main():
    errors = {"page": [], "console": []}
    result = {"fixture": FIXTURE.name, "viewport": {"width": 390, "height": 844}}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport=result["viewport"])
        page = context.new_page()
        page.on("pageerror", lambda error: errors["page"].append(str(error)))
        page.on("console", lambda message: errors["console"].append(message.text) if message.type == "error" else None)

        page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
        page.locator("#studio-file-input").set_input_files(str(FIXTURE))
        page.wait_for_function(
            "document.querySelector('#studio-page-count')?.textContent === '69' && document.querySelector('#studio-loading-overlay')?.hidden === true",
            timeout=30000,
        )
        result["first_open"] = page.evaluate(
            "({pages: Number(document.querySelector('#studio-page-count').textContent), file: state.studio.srcFile?.name, savedMarker: sessionStorage.getItem('paperplane-last-local-document:guest')})"
        )

        page.goto(f"{BASE}/compress-pdf", wait_until="domcontentloaded")
        restore_started = time.perf_counter()
        page.goto(f"{BASE}/studio", wait_until="domcontentloaded")
        page.wait_for_function(
            "document.querySelector('#studio-page-count')?.textContent === '69' && document.querySelector('#studio-loading-overlay')?.hidden === true",
            timeout=30000,
        )
        result["after_navigation"] = page.evaluate(
            "({pages: Number(document.querySelector('#studio-page-count').textContent), file: state.studio.srcFile?.name, title: document.title})"
        )
        result["restore_seconds"] = round(time.perf_counter() - restore_started, 3)
        page.screenshot(path=str(OUT / "browser-id369-studio-reload-local.png"), full_page=True)

        fresh = browser.new_page(viewport=result["viewport"])
        fresh.goto(f"{BASE}/studio", wait_until="domcontentloaded")
        fresh.wait_for_function("document.querySelector('#studio-page-count')?.textContent === '0'", timeout=10000)
        result["fresh_context"] = fresh.evaluate(
            "({pages: Number(document.querySelector('#studio-page-count').textContent), empty: document.body.innerText.includes('No document open')})"
        )
        browser.close()

    result["browser_errors"] = errors
    result["historical_stale_document_reproduced"] = False
    result["notes"] = "The same PDF was restored in the same browser context after route reload; a fresh context remained empty. This does not prove the reported 2026-11-16 file / AI workspace case or the deployed v154 behavior."
    assert result["first_open"]["pages"] == 69
    assert result["after_navigation"]["pages"] == 69
    assert result["fresh_context"]["pages"] == 0 and result["fresh_context"]["empty"]
    assert not any(errors.values()), errors
    (OUT / "browser-id369-studio-restore.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
