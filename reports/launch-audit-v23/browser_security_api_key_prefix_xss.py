"""Browser-test hostile developer API-key prefixes in both key-list views."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import time
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
    hostile = '<img src=x onerror="window.__apiKeyPrefixXss=true">'
    evidence = {"payload": hostile, "views": [], "page_errors": []}
    intercepted = {"count": 0}
    with TemporaryDirectory(prefix="paperplane-api-key-prefix-xss-") as temp:
        app, base, _identities = helper.start_server(Path(temp))
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
                page = browser.new_page(viewport={"width": 1280, "height": 800})
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                def fulfill_key_list(route):
                    intercepted["count"] += 1
                    route.fulfill(
                        status=200,
                        content_type="application/json",
                        body=json.dumps({"keys": [{"id": "synthetic-key-id", "name": "Test key",
                                                   "key_prefix": hostile, "created_at": 0}]}),
                    )

                page.route("**/api/developer/keys", fulfill_key_list)
                response = page.goto(base + "/", wait_until="domcontentloaded")
                assert response and response.status == 200
                for global_name, list_selector in (
                    ("loadSettingsApiKeys", "#settings-api-keys-list"),
                    ("loadApiKeys", "#api-keys-list"),
                ):
                    page.wait_for_function(f"typeof window.{global_name} === 'function'")
                    if global_name == "loadApiKeys":
                        page.evaluate("""() => {
                          const list = document.createElement('div');
                          list.id = 'api-keys-list';
                          document.body.appendChild(list);
                        }""")
                    page.locator(list_selector).wait_for(state="attached")
                    page.evaluate(f"window.{global_name}()")
                    page.wait_for_timeout(500)
                    state = page.locator(list_selector).evaluate("node => ({html:node.innerHTML,text:node.textContent,images:node.querySelectorAll('img').length})")
                    if hostile not in state["text"]:
                        raise AssertionError({"global": global_name, "state": state, "intercepted": intercepted})
                    assert state["images"] == 0, state
                    assert hostile in state["text"], state
                    assert "&lt;img" in state["html"], state
                    assert not page.evaluate("window.__apiKeyPrefixXss === true")
                    evidence["views"].append({"global": global_name, "selector": list_selector, **state})
                assert not evidence["page_errors"], evidence
                assert intercepted["count"] >= 2, intercepted
                evidence["api_intercepts"] = intercepted["count"]
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=20)

    destination = OUT / "browser-security-api-key-prefix-xss.json"
    destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))


if __name__ == "__main__":
    main()
