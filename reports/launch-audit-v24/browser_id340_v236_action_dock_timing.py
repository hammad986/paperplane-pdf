from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
VERSION = "v238"
OUT = Path(__file__).resolve().parent / f"browser-id340-{VERSION}-action-dock-timing.json"
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    result = {"version": "app.js v238 / styles.css v90 / service-worker v214", "viewport": [320, 844], "samples": [], "page_errors": [], "console_errors": []}
    with TemporaryDirectory(prefix="paperplane-v236-dock-timing-") as temp_name:
        app, base, _ = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            with sync_playwright() as p:
                browser = p.chromium.launch(channel="chrome", headless=False)
                page = browser.new_page(viewport={"width": 320, "height": 844})
                page.add_init_script("""
                  window.__scrollEvents = [];
                  window.__scrollRequests = [];
                  addEventListener('scroll', () => window.__scrollEvents.push({y:scrollY, at:performance.now()}), {passive:true});
                  const original = window.scrollTo.bind(window);
                  window.scrollTo = (...args) => { window.__scrollRequests.push({args, at:performance.now(), stack:(new Error()).stack?.split('\\n').slice(0,4)}); return original(...args); };
                """)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: result["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                for round_number in (1, 2):
                    for route in ("/summarize-pdf", "/translate-pdf"):
                        response = page.goto(base + route, wait_until="domcontentloaded")
                        navigation_return = time.perf_counter()
                        for delay in (200, 500, 800, 1200, 2000):
                            elapsed = (time.perf_counter() - navigation_return) * 1000
                            page.wait_for_timeout(max(0, delay - elapsed))
                            sample = page.evaluate("""() => {
                              const action=document.querySelector('#run-button'), nav=document.querySelector('.mobile-workspace-bar');
                              const a=action?.getBoundingClientRect(), n=nav?.getBoundingClientRect();
                              return {elapsedMs:performance.now(),action:a?{top:a.top,bottom:a.bottom,display:getComputedStyle(action).display,position:getComputedStyle(action).position}:null,
                                nav:n?{top:n.top,bottom:n.bottom}:null,scrollY:scrollY,viewport:innerWidth,clientWidth:document.documentElement.clientWidth,
                                overlaps:!!(a&&n&&a.top<n.bottom&&a.bottom>n.top&&a.left<n.right&&a.right>n.left),
                                activeView:typeof state!=='undefined'?state.activeView:null,operation:typeof state!=='undefined'?state.operation:null,
                                scrollRequests:(window.__scrollRequests||[]).slice(-6),scrollEvents:(window.__scrollEvents||[]).slice(-6)};
                            }""")
                            record = {"round": round_number, "route": route, "target_delay_ms": delay, "status": response.status if response else None, **sample}
                            result["samples"].append(record)
                            if round_number == 1 and delay == 500:
                                slug = route.strip("/")
                                page.screenshot(path=str(OUT.parent / f"browser-id340-{VERSION}-action-dock-{slug}-500ms.png"))
                page.set_viewport_size({"width": 1366, "height": 900})
                page.goto(base + "/summarize-pdf", wait_until="domcontentloaded")
                page.wait_for_timeout(600)
                page.set_viewport_size({"width": 320, "height": 844})
                page.wait_for_timeout(800)
                result["desktop_to_mobile_resize"] = page.evaluate("""() => {
                  const action=document.querySelector('#run-button'),nav=document.querySelector('.mobile-workspace-bar');
                  const a=action?.getBoundingClientRect(),n=nav?.getBoundingClientRect();
                  return {viewport:innerWidth,activeView:typeof state!=='undefined'?state.activeView:null,
                    overlap:!!(a&&n&&a.top<n.bottom&&a.bottom>n.top&&a.left<n.right&&a.right>n.left),
                    scrollWidth:document.documentElement.scrollWidth};
                }""")
                browser.close()
            result["action_clear_after_500ms"] = all(not item["overlaps"] for item in result["samples"] if item["target_delay_ms"] >= 500)
            result["passed"] = result["action_clear_after_500ms"] and result["desktop_to_mobile_resize"]["viewport"] == 320 and result["desktop_to_mobile_resize"]["activeView"] == "desk" and not result["desktop_to_mobile_resize"]["overlap"] and not result["page_errors"] and not result["console_errors"]
            OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps(result, indent=2))
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
