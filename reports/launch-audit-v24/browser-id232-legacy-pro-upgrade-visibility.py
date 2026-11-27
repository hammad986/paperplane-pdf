"""Verify a Legacy Pro account does not see the free-plan upgrade CTA."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id232-legacy-pro-upgrade-visibility.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    with TemporaryDirectory(prefix="paperplane-id232-") as temp_name:
        app, base, _identities = helper.start_server(Path(temp_name) / "data")
        evidence = {"page_errors": [], "console_errors": []}
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
                evidence["tier_render"] = page.evaluate("""() => {
                  updateBillingUI({tier: 'pro', is_pro: true, is_dev: false, usage_today: 23, daily_limit: 200});
                  const button = document.querySelector('#settings-upgrade-plan-btn');
                  return {
                    tier_name: document.querySelector('#settings-tier-name')?.textContent,
                    tier_badge: document.querySelector('#settings-tier-badge')?.textContent,
                    quota_text: document.querySelector('#settings-quota-text')?.textContent,
                    button_display: getComputedStyle(button).display,
                    button_hidden: button.hidden || getComputedStyle(button).display === 'none',
                    visible_upgrade_ctas: ['#sidebar-upgrade-btn','#topbar-upgrade-btn','#settings-upgrade-plan-btn']
                      .filter(selector => { const el = document.querySelector(selector); return el && getComputedStyle(el).display !== 'none' && !el.hidden; })
                  };
                }""")
                page.locator("#sidebar-settings-gear-btn").click()
                page.locator("#settings-modal:not([hidden])").wait_for()
                page.locator("#settings-tab-btn-billing").click()
                page.locator("#pane-billing:not([hidden])").wait_for()
                evidence["billing_view"] = page.evaluate("""() => ({
                  tier_name: document.querySelector('#settings-tier-name')?.textContent,
                  upgrade_button_visible: (() => {const el=document.querySelector('#settings-upgrade-plan-btn');return getComputedStyle(el).display !== 'none' && !el.hidden;})(),
                  upgrade_button_text: document.querySelector('#settings-upgrade-plan-btn')?.innerText.trim()
                })""")
                browser.close()
            evidence["http_status"] = response.status if response else None
        finally:
            app.terminate()
            app.wait(timeout=5)
        evidence["overall"] = "passed" if (
            evidence.get("http_status") == 200
            and evidence.get("tier_render", {}).get("tier_name") == "Legacy Pro"
            and evidence.get("tier_render", {}).get("tier_badge") == "LEGACY PRO"
            and evidence.get("tier_render", {}).get("button_hidden") is True
            and evidence.get("tier_render", {}).get("visible_upgrade_ctas") == []
            and evidence.get("billing_view", {}).get("tier_name") == "Legacy Pro"
            and evidence.get("billing_view", {}).get("upgrade_button_visible") is False
            and not evidence["page_errors"] and not evidence["console_errors"]
        ) else "failed"
        OUT.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        print(json.dumps(evidence, indent=2))
        if evidence["overall"] != "passed":
            raise SystemExit(1)


if __name__ == "__main__":
    main()
