from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    evidence: dict = {"page_errors": [], "console_errors": [], "surfaces": []}
    with TemporaryDirectory(prefix="paperplane-v24-id192-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(150):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.on("pageerror", lambda err: evidence["page_errors"].append(str(err)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                response = page.goto(base + "/tool-desk", wait_until="domcontentloaded", timeout=20000)
                page.wait_for_function("document.querySelector('#tool-desk-tools-catalog')?.innerText.length > 100")
                billing_response = page.request.get(base + "/api/billing/status")
                public_pricing = billing_response.json()["pricing"]
                for surface, selector in (("sidebar", "#sidebar-upgrade-btn"), ("topbar", "#topbar-upgrade-btn")):
                    label = page.locator(selector).inner_text()
                    page.locator(selector).click()
                    page.locator("#upgrade-modal:not([hidden])").wait_for()
                    plans = page.locator("#upgrade-modal .pricing-tier-card .tier-title").all_inner_texts()
                    pricing_copy = page.locator("#upgrade-modal").inner_text()
                    price_matches = {key: (f"₹{entry['inr']}" in pricing_copy)
                                     for key, entry in public_pricing.items()}
                    evidence["surfaces"].append({"surface": surface, "trigger_label": label,
                                                 "plan_names": plans,
                                                 "public_pricing": public_pricing,
                                                 "displayed_prices_match_public_catalog": price_matches,
                                                 "stale_legacy_name_present": "Pro Power User" in pricing_copy,
                                                 "stale_legacy_price_present": "₹250" in pricing_copy})
                    page.locator("#close-upgrade-modal").click()
                    page.wait_for_function("document.querySelector('#upgrade-modal')?.hidden")
                evidence["http_status"] = response.status if response else None
                page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / "browser-id192-plan-labels.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
    evidence["billing_status_http_status"] = billing_response.status if 'billing_response' in locals() else None
    evidence["passed"] = (evidence.get("http_status") == 200 and evidence["billing_status_http_status"] == 200
                           and len(evidence["surfaces"]) == 2
                           and all(x["plan_names"] == ["Free", "Exam Pass", "Student & Educator", "All-In-One Pro & Developer"]
                                   and all(x["displayed_prices_match_public_catalog"].values())
                                   and not x["stale_legacy_name_present"] and not x["stale_legacy_price_present"]
                                   for x in evidence["surfaces"])
                           and not evidence["page_errors"] and not evidence["console_errors"])
    path = ROOT / "reports" / "launch-audit-v24" / "browser-id192-plan-labels.json"
    path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
