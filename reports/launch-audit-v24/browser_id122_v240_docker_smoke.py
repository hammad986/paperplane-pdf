from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
BASE = "http://127.0.0.1:18506"
OUT = ROOT / "reports/launch-audit-v24/browser-id122-v240-docker-smoke.json"


def main() -> None:
    result = {
        "candidate": "paperplane-codex:v240-current",
        "image_id": "sha256:d0149a9dc050b707bcb7ceee70c69a0429a35aa00d2f1277d6c64da48307b4d3",
        "rounds": [], "page_errors": [], "console_errors": []
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="chrome", headless=True)
        for round_number in (1, 2):
            for width in (320, 390):
                page = browser.new_page(viewport={"width": width, "height": 844})
                page.on("pageerror", lambda error: result["page_errors"].append(str(error).splitlines()[0][:240]))
                page.on("console", lambda message: result["console_errors"].append(message.text[:240]) if message.type == "error" else None)
                response = page.goto(BASE + "/studio", wait_until="domcontentloaded")
                assert response and response.status == 200
                assets = page.evaluate("""async () => {
                  const app = await fetch('/assets/app.js?v=239');
                  const shell = await fetch('/service-worker.js');
                  return {appStatus: app.status, appContainsIdleScheduler: (await app.text()).includes('function scheduleInitialControlLabels()'),
                    shellStatus: shell.status, shellText: await shell.text(), width: innerWidth,
                    overflow: document.documentElement.scrollWidth > document.documentElement.clientWidth};
                }""")
                assert assets["appStatus"] == 200 and assets["appContainsIdleScheduler"], assets
                assert assets["shellStatus"] == 200 and "paperplane-shell-v215" in assets["shellText"] and "app.js?v=239" in assets["shellText"], assets
                assert assets["width"] == width and not assets["overflow"], assets
                page.wait_for_function("""() => [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
                  .every(control => control.labels?.length || control.getAttribute('aria-label') || control.title)""", timeout=8000)
                label_counts = page.evaluate("""() => ({controls: document.querySelectorAll('input:not([type=hidden]), select, textarea').length,
                  missing: [...document.querySelectorAll('input:not([type=hidden]), select, textarea')]
                    .filter(control => !control.labels?.length && !control.getAttribute('aria-label') && !control.title).length})""")
                page.evaluate("""() => { const input = document.createElement('input'); input.placeholder = 'Docker dynamic label probe'; document.body.append(input); }""")
                page.wait_for_function("document.querySelector('input[placeholder=\"Docker dynamic label probe\"]')?.labels?.length", timeout=3000)
                result["rounds"].append({"round": round_number, "width": width, "asset_cache_checks": "passed", "overflow": assets["overflow"], "label_counts": label_counts, "dynamic_label": page.locator('input[placeholder="Docker dynamic label probe"]').evaluate("input => input.labels[0].textContent")})
                assert label_counts["missing"] == 0
                page.close()
        browser.close()
    result["result"] = "passed" if len(result["rounds"]) == 4 and not result["page_errors"] and not result["console_errors"] else "failed"
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if result["result"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
