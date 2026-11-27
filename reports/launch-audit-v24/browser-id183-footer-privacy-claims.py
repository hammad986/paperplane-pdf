"""Check footer links, copyright, and privacy claim at mobile/desktop widths."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id183-footer-privacy-claims.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402

REQUIRED_LINKS = {"/pricing", "/faq", "/dashboard"}


def main():
    with TemporaryDirectory(prefix="paperplane-id183-") as temp_name:
        app, base, _identities = helper.start_server(Path(temp_name) / "data")
        evidence = {"page_errors": [], "console_errors": [], "viewports": []}
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    if app.poll() is not None:
                        raise RuntimeError("Local Paperplane server exited before startup")
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 1366, "height": 900})
                page.set_default_timeout(15000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/", wait_until="domcontentloaded")
                for width in (390, 1366):
                    page.set_viewport_size({"width": width, "height": 900})
                    footer = page.locator(".app-global-footer")
                    footer.scroll_into_view_if_needed()
                    page.wait_for_function("document.documentElement.classList.contains('footer-revealed')")
                    evidence["viewports"].append(page.evaluate("""() => {
                      const footer = document.querySelector('.app-global-footer');
                      const rect = footer.getBoundingClientRect();
                      return {
                        width: innerWidth,
                        copyright: footer.querySelector('.footer-left')?.innerText,
                        links: [...footer.querySelectorAll('a.footer-link')].map(a => ({label:a.textContent.trim(), href:a.getAttribute('href'), visible:a.getBoundingClientRect().width > 0 && getComputedStyle(a).display !== 'none'})),
                        footer_rect: {left:rect.left, right:rect.right},
                        document_overflow_x: document.documentElement.scrollWidth > document.documentElement.clientWidth,
                        privacy_claim_present: document.body.innerText.includes('100% Private')
                      };
                    }"""))
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and len(evidence["viewports"]) == 2
            and all(REQUIRED_LINKS.issubset({link["href"] for link in view["links"] if link["visible"]})
                    and "2026 Paperplane PDF" in view["copyright"]
                    and not view["document_overflow_x"]
                    and not view["privacy_claim_present"] for view in evidence["viewports"])
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
