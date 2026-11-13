from __future__ import annotations

import json
from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(BASE, wait_until="domcontentloaded", timeout=20_000)
        page.locator("#sidebar-tools-container .sidebar-tool-item").first.wait_for(state="attached", timeout=20_000)
        results = []
        for currency in [None, "INR", "USD"]:
            page.evaluate("""currency => {
              renderExtractionResultsModal({
                document_type: 'invoice',
                invoice_data: {
                  currency,
                  total_amount: 1250.5,
                  subtotal: 1100,
                  tax_amount: 150.5,
                  line_items: [{description:'Audit item', quantity:1, unit_price:1100, amount:1100}]
                },
                warnings: []
              });
            }""", currency)
            extracted = page.evaluate("""() => ({
              fields: document.querySelector('#extraction-fields-grid').innerText,
              lineItems: document.querySelector('#extraction-items-tbody').innerText
            })""")
            results.append({"currency": currency, **extracted})
        browser.close()

    unknown, inr, usd = results
    assert "currency not identified" in unknown["fields"].lower()
    assert "$" not in unknown["fields"] + unknown["lineItems"]
    assert "INR 1250.5" in inr["fields"] and "INR 1100" in inr["lineItems"]
    assert "USD 1250.5" in usd["fields"] and "USD 1100" in usd["lineItems"]
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
