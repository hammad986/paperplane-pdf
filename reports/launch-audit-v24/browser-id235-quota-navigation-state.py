"""Ensure usage badges do not revert to Checking usage during workspace navigation."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id235-quota-navigation-state.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id235-") as temp_name:
        app, base, _identities = helper.start_server(Path(temp_name) / "data")
        evidence = {"page_errors": [], "console_errors": [], "steps": []}
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
                page.set_default_timeout(20000)
                page.on("pageerror", lambda error: evidence["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: evidence["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                response = page.goto(base + "/tool-desk", wait_until="domcontentloaded")
                page.wait_for_function("!['Checking usage…','Checking usage...'].includes(document.querySelector('#quota-text')?.textContent.trim())")
                page.evaluate("""() => {
                  window.__quotaCheckingHistory = [];
                  const record = () => {
                    for (const selector of ['#quota-text', '#settings-quota-text']) {
                      const node = document.querySelector(selector);
                      if (node && /^Checking usage[.…]*$/.test(node.textContent.trim())) window.__quotaCheckingHistory.push(selector);
                    }
                  };
                  new MutationObserver(record).observe(document.body, {subtree:true, childList:true, characterData:true});
                  record();
                }""")
                for view in ("settings", "ai", "tool-desk", "pricing", "tool-desk"):
                    page.evaluate("view => switchWorkspaceView(view, 'account', false)", view)
                    page.wait_for_timeout(100)
                    evidence["steps"].append(page.evaluate("""() => ({view:state.activeView,
                      sidebar:document.querySelector('#quota-text')?.textContent.trim(),
                      settings:document.querySelector('#settings-quota-text')?.textContent.trim()})"""))
                evidence["checking_reappeared"] = page.evaluate("window.__quotaCheckingHistory")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and len(evidence["steps"]) == 5
            and all("Checking usage" not in step["sidebar"] and "Checking usage" not in step["settings"]
                    for step in evidence["steps"])
            and not evidence.get("checking_reappeared")
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
