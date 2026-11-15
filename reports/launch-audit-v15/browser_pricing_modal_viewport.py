"""Verify pricing modal scroll keeps each plan action reachable at short heights."""
from __future__ import annotations
import importlib.util, json, socket, time
from pathlib import Path
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / "reports" / "launch-audit-v14" / "browser_acceptance_v14.py"
spec = importlib.util.spec_from_file_location("pricing_modal_helpers", HELPER)
helpers = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(helpers)

def main() -> None:
    report = []
    with helpers.TemporaryDirectory(prefix="paperplane-pricing-modal-") as temp:
        app, base, _ = helpers.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2): break
                except OSError:
                    if app.poll() is not None: raise RuntimeError("Local app exited")
                    time.sleep(0.1)
            else: raise RuntimeError("Local app did not become ready")
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                for width, height in ((1920, 998), (390, 700)):
                    for n in (1, 2):
                        page = browser.new_page(viewport={"width": width, "height": height})
                        errors = []
                        page.on("pageerror", lambda e: errors.append(str(e)))
                        page.goto(base + "/", wait_until="domcontentloaded")
                        if width < 600:
                            page.locator("#mobile-menu-btn").click()
                        page.locator("#sidebar-upgrade-btn").click()
                        modal = page.locator("#upgrade-modal")
                        modal.wait_for(state="visible")
                        card = page.locator("#upgrade-modal .pricing-modal-card")
                        dimensions = card.evaluate("el => ({client: el.clientHeight, scroll: el.scrollHeight, max: getComputedStyle(el).maxHeight, overflow: getComputedStyle(el).overflowY})")
                        actions = []
                        for selector in ("#exam-cashfree-checkout-btn", "#student-cashfree-checkout-btn", "#cybercafe-cashfree-checkout-btn"):
                            button = page.locator(selector)
                            button.scroll_into_view_if_needed()
                            box = button.bounding_box()
                            actions.append({"id": selector[1:], "visible": button.is_visible(),
                                            "within_viewport": bool(box and box["y"] >= 0 and box["y"] + box["height"] <= height)})
                        assert all(item["visible"] and item["within_viewport"] for item in actions), (width, height, actions, dimensions)
                        assert dimensions["overflow"] in ("auto", "scroll")
                        assert not errors, errors
                        report.append({"viewport": [width, height], "card": dimensions, "actions": actions, "page_errors": errors})
                        page.close()
                browser.close()
        finally:
            app.terminate(); app.wait(timeout=10)
    out = ROOT / "reports" / "launch-audit-v15" / "browser-pricing-modal-viewport.json"
    out.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))

if __name__ == "__main__": main()
