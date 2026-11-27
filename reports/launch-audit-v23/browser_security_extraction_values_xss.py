"""Browser-test hostile AI-extraction values in invoice result rendering."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory
from urllib.request import urlopen

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
spec = importlib.util.spec_from_file_location(
    "browser_acceptance_v14", ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
)
helper = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helper)


def main() -> None:
    hostile = '<img src=x onerror="window.__extractionXss=true">'
    evidence = {"payload": hostile, "page_errors": []}
    with TemporaryDirectory(prefix="paperplane-extraction-xss-") as temp:
        app, base, _ = helper.start_server(Path(temp))
        try:
            for _ in range(60):
                try:
                    with urlopen(base + "/api/health", timeout=1) as health:
                        if health.status == 200:
                            break
                except Exception:
                    time.sleep(0.5)
            else:
                raise RuntimeError("isolated local server did not become healthy")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1280, "height": 850})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                response = page.goto(base + "/", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.wait_for_function("typeof window.renderExtractionResultsModal === 'function'")
                page.evaluate("""payload => window.renderExtractionResultsModal({
                  document_type: 'invoice', total_pages: 1, warnings: [],
                  invoice_data: {currency:'USD', line_items:[{description:'Synthetic item', quantity:payload, unit_price:1, amount:1}]},
                  source_pages: [payload], contact: {emails:[], phones:[]}
                })""", hostile)
                state = page.evaluate("""() => ({
                  invoiceHTML: document.querySelector('#extraction-items-tbody')?.innerHTML,
                  invoiceText: document.querySelector('#extraction-items-tbody')?.textContent,
                  pageHTML: document.querySelector('#extraction-source-pages')?.innerHTML,
                  pageText: document.querySelector('#extraction-source-pages')?.textContent,
                  injectedImages: document.querySelectorAll('#extraction-items-tbody img, #extraction-source-pages img').length,
                  handlerExecuted: window.__extractionXss === true
                })""")
                assert hostile in state["invoiceText"], state
                assert hostile in state["pageText"], state
                assert "&lt;img" in state["invoiceHTML"], state
                assert "&lt;img" in state["pageHTML"], state
                assert state["injectedImages"] == 0 and not state["handlerExecuted"], state
                assert not evidence["page_errors"], evidence
                evidence["rendered"] = state
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=20)

    destination = OUT / "browser-security-extraction-values-xss.json"
    destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
