import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
RUNTIME = os.environ.get("PAPERPLANE_TEST_RUNTIME", "local")
OUT = ROOT / "reports" / "launch-audit-v23" / (
    "browser-id37-processing-disclosure.json" if RUNTIME == "local"
    else f"browser-id37-processing-disclosure-{RUNTIME}.json"
)
URL = os.environ.get("PAPERPLANE_TEST_BASE", "http://127.0.0.1:8501") + "/"


def main():
    evidence = {"rounds": [], "pageErrors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for round_no, width in enumerate((1366, 390), 1):
            page = browser.new_page(viewport={"width": width, "height": 900})
            page.on("pageerror", lambda error: evidence["pageErrors"].append(str(error)))
            response = page.goto(URL, wait_until="domcontentloaded")
            page.wait_for_function("typeof selectOperation === 'function' && document.querySelector('#client-privacy-toggle')")
            initial_support = page.locator("#privacy-mode-support").inner_text()
            settings_support = page.locator("#settings-client-privacy-support").inner_text()
            page.evaluate("selectOperation('pdf_to_word')")
            word = {
                "toggleEnabled": not page.locator("#client-privacy-toggle").is_disabled(),
                "browserModeSelected": page.locator("#client-privacy-toggle").is_checked(),
                "supportText": page.locator("#privacy-mode-support").inner_text(),
                "optionsDisclosure": page.locator("#options").inner_text(),
                "toolModeDisclosed": "runs in your browser" in page.locator("#privacy-mode-support").inner_text(),
            }
            page.evaluate("selectOperation('compress')")
            compress = {
                "toggleDisabled": page.locator("#client-privacy-toggle").is_disabled(),
                "serverModeSelected": not page.locator("#client-privacy-toggle").is_checked(),
            }
            evidence["rounds"].append({
                "round": round_no,
                "viewportWidth": width,
                "httpStatus": response.status if response else None,
                "scriptVersion": page.locator('script[src*="app.js"]').get_attribute("src"),
                "initialDisclosure": initial_support,
                "settingsDisclosureHasWord": "PDF-to-Word (text-first)" in settings_support,
                "pdfToWord": word,
                "compress": compress,
                "horizontalOverflow": page.evaluate("document.documentElement.scrollWidth > document.documentElement.clientWidth"),
            })
            page.close()
        browser.close()
    evidence["passed"] = all(
        item["httpStatus"] == 200
        and item["settingsDisclosureHasWord"]
        and item["pdfToWord"]["toggleEnabled"]
        and item["pdfToWord"]["browserModeSelected"]
        and item["pdfToWord"]["toolModeDisclosed"]
        and "text-first DOCX" in item["pdfToWord"]["optionsDisclosure"]
        and item["compress"]["toggleDisabled"]
        and item["compress"]["serverModeSelected"]
        and not item["horizontalOverflow"]
        for item in evidence["rounds"]
    ) and not evidence["pageErrors"]
    OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
