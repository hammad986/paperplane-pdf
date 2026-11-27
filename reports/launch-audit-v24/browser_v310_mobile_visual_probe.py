from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
ROUTES = ["/", "/merge-pdf", "/studio", "/ai-intelligence", "/apps", "/download"]
VIEWPORTS = [(320, 568), (390, 844), (820, 900), (1366, 900)]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main() -> None:
    with TemporaryDirectory(prefix="paperplane-v310-visual-probe-") as temp:
        app, base, _ = helper.start_server(Path(temp) / "data")
        result: dict = {"base": base, "routes": [], "page_errors": [], "console_errors": []}
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
                for width, height in VIEWPORTS:
                    context = browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=1)
                    for route in ROUTES:
                        page = context.new_page()
                        page.on("pageerror", lambda error: result["page_errors"].append(str(error)[:200]))
                        page.on("console", lambda message: result["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                        response = page.goto(base + route, wait_until="domcontentloaded")
                        page.wait_for_timeout(700)
                        snapshot = page.evaluate("""() => {
                          const rect = e => { const r=e.getBoundingClientRect(); return {x:r.x,y:r.y,width:r.width,height:r.height,top:r.top,bottom:r.bottom,left:r.left,right:r.right}; };
                          const pill = document.querySelector('#mobile-view-pill');
                          const pillStatus = document.querySelector('#mobile-view-pill-sr');
                          const dock = document.querySelector('.mobile-bottom-nav, #mobile-bottom-nav, .mobile-nav');
                          const dockRect = dock && getComputedStyle(dock).position === 'fixed' ? rect(dock) : null;
                          const controls = [...document.querySelectorAll('a,button,input,select,textarea,[role=button]')]
                            .filter(e => { const r=e.getBoundingClientRect(), s=getComputedStyle(e); return s.display!=='none' && s.visibility!=='hidden' && r.width>0 && r.height>0; })
                            .map(e => ({name:(e.innerText||e.getAttribute('aria-label')||e.getAttribute('title')||e.id||e.tagName).trim().slice(0,70),...rect(e)}));
                          return {title:document.title,h1:[...document.querySelectorAll('h1')].map(x=>x.innerText),scrollWidth:document.documentElement.scrollWidth,clientWidth:document.documentElement.clientWidth,scrollHeight:document.documentElement.scrollHeight,dock:dockRect,pill:pill?{text:pill.textContent.trim(),ariaHidden:pill.getAttribute('aria-hidden'),srText:pillStatus?.textContent.trim()||'',title:pill.title,...rect(pill)}:null,controls};
                        }""")
                        obscured = []
                        if snapshot["dock"]:
                            d = snapshot["dock"]
                            obscured = [c["name"] for c in snapshot["controls"] if c["bottom"] > d["top"] + 1 and c["top"] < d["bottom"] - 1 and c["left"] < d["right"] and c["right"] > d["left"]]
                        record = {"route": route, "viewport": [width, height], "http_status": response.status if response else None,
                                  "title": snapshot["title"], "h1": snapshot["h1"], "scroll_width": snapshot["scrollWidth"],
                                  "client_width": snapshot["clientWidth"], "scroll_height": snapshot["scrollHeight"],
                                  "fixed_dock": snapshot["dock"], "mobile_view_pill": snapshot["pill"], "controls_overlapped_by_dock": obscured}
                        if route == "/ai-intelligence":
                            record["pill_assertion_passed"] = snapshot["pill"] and snapshot["pill"]["text"] == "AI" and snapshot["pill"]["ariaHidden"] == "true" and snapshot["pill"]["srText"] == "AI Intelligence workspace" and snapshot["pill"]["title"] == "AI Intelligence workspace"
                        elif route == "/apps":
                            record["pill_assertion_passed"] = snapshot["pill"] and snapshot["pill"]["text"] == "Apps" and snapshot["pill"]["ariaHidden"] == "true" and snapshot["pill"]["srText"] == "Native Apps workspace" and snapshot["pill"]["title"] == "Native Apps workspace"
                        elif route == "/download":
                            record["pill_assertion_passed"] = snapshot["pill"] and snapshot["pill"]["text"] == "Apps" and snapshot["pill"]["ariaHidden"] == "true" and snapshot["pill"]["srText"] == "Downloads workspace" and snapshot["pill"]["title"] == "Downloads workspace"
                        result["routes"].append(record)
                        if width in (320, 390):
                            slug = route.strip("/").replace("/", "-") or "home"
                            page.screenshot(path=str(OUT / f"browser-v312-{slug}-{width}.png"), full_page=False)
                        page.close()
                    context.close()
                browser.close()
            result["passed"] = all(r["http_status"] == 200 and r["scroll_width"] <= r["client_width"] + 1 and r.get("pill_assertion_passed", True) for r in result["routes"]) and not result["page_errors"] and not result["console_errors"]
            path = OUT / "browser-v312-mobile-visual-probe.json"
            path.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps({"passed": result["passed"], "route_viewports": len(result["routes"]),
                              "horizontal_overflow": [r for r in result["routes"] if r["scroll_width"] > r["client_width"] + 1],
                              "dock_overlaps": [{"route": r["route"], "viewport": r["viewport"], "controls": r["controls_overlapped_by_dock"]} for r in result["routes"] if r["controls_overlapped_by_dock"]],
                              "page_errors": result["page_errors"], "console_errors": result["console_errors"]}, indent=2))
            if not result["passed"]:
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=10)


if __name__ == "__main__":
    main()
