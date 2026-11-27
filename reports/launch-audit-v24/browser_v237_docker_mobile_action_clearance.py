from __future__ import annotations

import json
import os
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
VERSION = os.environ.get("PAPERPLANE_DOCKER_VERSION", "v237")
OUT = ROOT / "reports/launch-audit-v24" / f"browser-{VERSION}-docker-mobile-action-clearance.json"
BASE = os.environ.get("PAPERPLANE_DOCKER_BASE", "http://127.0.0.1:18502")


def main() -> None:
    result = {"base": BASE, "image": f"paperplane-codex:{VERSION}-current", "viewport": [320, 844], "routes": [], "page_errors": [], "console_errors": []}
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=False)
        page = browser.new_page(viewport={"width": 320, "height": 844})
        page.on("pageerror", lambda error: result["page_errors"].append(str(error).splitlines()[0][:200]))
        page.on("console", lambda message: result["console_errors"].append(message.text[:200]) if message.type == "error" else None)
        for route in ("/summarize-pdf", "/translate-pdf"):
            response = page.goto(BASE + route, wait_until="domcontentloaded")
            start = time.perf_counter()
            samples = []
            for delay in (500, 800, 1200, 2000):
                elapsed = (time.perf_counter() - start) * 1000
                page.wait_for_timeout(max(0, delay - elapsed))
                samples.append(page.evaluate("""() => {
                  const action=document.querySelector('#run-button'),nav=document.querySelector('.mobile-workspace-bar');
                  const a=action?.getBoundingClientRect(),n=nav?.getBoundingClientRect();
                  return {elapsed:performance.now(),activeView:typeof state!=='undefined'?state.activeView:null,
                    action:a?{top:a.top,bottom:a.bottom}:null,nav:n?{top:n.top,bottom:n.bottom}:null,
                    overlap:!!(a&&n&&a.top<n.bottom&&a.bottom>n.top&&a.left<n.right&&a.right>n.left),
                    viewport:innerWidth,scrollWidth:document.documentElement.scrollWidth};
                }"""))
            if route == "/summarize-pdf":
                page.screenshot(path=str(OUT.parent / f"browser-{VERSION}-docker-summarize-320.png"))
            result["routes"].append({"route": route, "status": response.status if response else None, "samples": samples,
                                    "passed": bool(response and response.status == 200 and all(not sample["overlap"] for sample in samples) and all(sample["scrollWidth"] <= sample["viewport"] for sample in samples) and all(sample["activeView"] == "desk" for sample in samples))})
        browser.close()
    result["passed"] = all(route["passed"] for route in result["routes"]) and not result["page_errors"] and not result["console_errors"]
    OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
