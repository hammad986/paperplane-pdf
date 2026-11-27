"""Verify the current app shell caches and serves app.js v121 offline in Chromium."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import time
from tempfile import TemporaryDirectory

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
    with TemporaryDirectory(prefix="paperplane-shell-v53-") as temp:
        app, base, _ = helper.start_server(Path(temp))
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(100):
                try:
                    import socket
                    with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                        break
                except OSError:
                    time.sleep(0.2)
            else:
                raise RuntimeError("isolated server did not start")

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                for round_number in (1, 2):
                    context = browser.new_context(viewport={"width": 390, "height": 844})
                    page = context.new_page()
                    page.on("pageerror", lambda error: evidence["page_errors"].append(str(error)))
                    response = page.goto(base + "/", wait_until="networkidle")
                    assert response and response.status == 200
                    page.evaluate("navigator.serviceWorker.ready")
                    page.wait_for_function("!!navigator.serviceWorker.controller", timeout=10000)
                    cached = page.evaluate("""async () => {
                      const names = await caches.keys();
                      const cache = await caches.open('paperplane-shell-v53');
                      const urls = await cache.keys();
                      return {names, urls:urls.map(request => new URL(request.url).pathname + new URL(request.url).search)};
                    }""")
                    assert "paperplane-shell-v53" in cached["names"], cached
                    assert "/assets/app.js?v=121" in cached["urls"], cached
                    assert "/assets/styles.css?v=56" in cached["urls"], cached
                    context.set_offline(True)
                    offline = page.reload(wait_until="domcontentloaded", timeout=15000)
                    assert offline and offline.status == 200
                    page.wait_for_function("typeof window.loadSettingsApiKeys === 'function'", timeout=10000)
                    result = {
                        "round": round_number,
                        "shell_cache": "paperplane-shell-v53",
                        "cached_app_asset": "/assets/app.js?v=121",
                        "cached_styles_asset": "/assets/styles.css?v=56",
                        "offline_http_status": offline.status,
                        "app_script_loaded_offline": True,
                        "page_errors": [],
                    }
                    evidence["rounds"].append(result)
                    context.close()
                browser.close()
        finally:
            app.terminate()
            app.wait(timeout=20)

    destination = OUT / "browser-id357-offline-v53-smoke.json"
    destination.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    if evidence["page_errors"] or len(evidence["rounds"]) != 2:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
