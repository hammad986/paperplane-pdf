"""Browser-test password reset response text and development reset-link handling."""
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
    evidence = {"rounds": [], "page_errors": []}
    hostile = '<img src=x onerror="window.__resetResponseXss=true">'
    with TemporaryDirectory(prefix="paperplane-reset-response-xss-") as temp:
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
                responses = [
                    {"message": hostile, "dev_reset_url": "javascript:window.__resetResponseXss=true"},
                    {"message": "Synthetic reset instructions.", "dev_reset_url": f"{base}/?reset_token=synthetic-safe-token"},
                ]
                def fulfill_reset(route):
                    response = responses.pop(0)
                    route.fulfill(status=200, content_type="application/json", body=json.dumps(response))

                page.route("**/api/auth/forgot-password", fulfill_reset)
                response = page.goto(base + "/", wait_until="domcontentloaded")
                assert response and response.status == 200
                page.locator("#topbar-signin-btn").click()
                page.locator("#link-forgot-password").click()
                page.locator("#forgot-email").fill("synthetic@example.invalid")
                for round_number in (1, 2):
                    page.locator("#forgot-password-form button[type=submit]").click()
                    page.wait_for_function("document.querySelector('#forgot-message')?.hidden === false")
                    state = page.locator("#forgot-message").evaluate("node => ({html:node.innerHTML,text:node.textContent,images:node.querySelectorAll('img').length,links:[...node.querySelectorAll('a')].map(a=>a.href)})")
                    if round_number == 1:
                        assert hostile in state["text"] and "&lt;img" in state["html"], state
                        assert state["images"] == 0 and not state["links"], state
                        assert not page.evaluate("window.__resetResponseXss === true")
                    else:
                        assert "Synthetic reset instructions." in state["text"], state
                        assert len(state["links"]) == 1 and state["links"][0] == f"{base}/?reset_token=synthetic-safe-token", state
                    evidence["rounds"].append({"round": round_number, **state})
                assert not evidence["page_errors"], evidence
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=20)

    destination = OUT / "browser-security-password-reset-response-xss.json"
    destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
