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

ROUTES = {
    "privacy": {"heading": "Paperplane Privacy Policy & Data Protection", "title": "Privacy Policy | Paperplane", "required": ["AI provider configured for this deployment", "Cashfree", "support@paperplane.qd.je"]},
    "terms": {"heading": "Terms of Service", "title": "Terms of Service | Paperplane", "required": ["DRAFT — owner review required before launch", "Cashfree payment orders", "refund policy"]},
    "refund": {"heading": "Refund, Tax & Billing Information", "title": "Refund and Tax Information — Draft | Paperplane", "required": ["DRAFT", "order ID", "refund eligibility"]},
    "contact": {"heading": "Contact Paperplane Support", "title": "Contact Paperplane Support — Draft | Paperplane", "required": ["DRAFT", "support@paperplane.qd.je", "response expectation"]},
}


def main() -> None:
    evidence: dict = {"rounds": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v24-id348-") as temp:
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
                context = browser.new_context(viewport={"width": 390, "height": 844})
                page = context.new_page()
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                page.on("console", lambda msg: evidence["console_errors"].append(msg.text) if msg.type == "error" else None)
                for round_no in (1, 2):
                    for slug, expected in ROUTES.items():
                        response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded")
                        assert response and response.status == 200, (slug, response.status if response else None)
                        title = page.title()
                        heading = page.locator("#legal-page-title" if slug in {"privacy", "terms"} else ".seo-content h2").inner_text()
                        body = page.locator("body").inner_text()
                        assert expected["heading"] in heading, (slug, heading)
                        assert title == expected["title"], (slug, title)
                        if slug in {"refund", "contact"}:
                            assert not page.locator("#view-tool-desk-directory").is_visible(), slug
                            assert page.locator(".seo-content").is_visible(), slug
                        missing = [item for item in expected["required"] if item.lower() not in body.lower()]
                        assert not missing, (slug, missing)
                        assert page.locator("a[href='/contact']").count() or slug == "contact"
                        evidence["rounds"].append({"round": round_no, "route": f"/{slug}", "http": response.status,
                            "title": title, "route_heading": heading, "required_copy_present": True,
                            "draft_or_configuration_disclosure_present": True})
                        if round_no == 1 and slug in {"refund", "contact"}:
                            page.screenshot(path=str(ROOT / "reports" / "launch-audit-v24" / f"browser-id348-{slug}.png"), full_page=True)
                browser.close()
        finally:
            app.terminate()
    evidence["passed"] = len(evidence["rounds"]) == 8 and not evidence["page_errors"] and not evidence["console_errors"]
    out = ROOT / "reports" / "launch-audit-v24" / "browser-id348-legal-support-pages.json"
    out.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if not evidence["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
