"""Check feedback widget mounting and authenticated visibility across all 44 tool routes."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-id147-feedback-route-mounts.json"
ROUTES_FILE = ROOT / "reports/launch-audit-v24/route-layout-matrix.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    routes = [row["route"] for row in json.loads(ROUTES_FILE.read_text(encoding="utf-8"))["copy_routes"] if row["route"] not in ("/", "/pricing")]
    with TemporaryDirectory(prefix="paperplane-id147-routes-") as temp_name:
        app, base, _ = helper.start_server(Path(temp_name) / "data")
        try:
            port = int(base.rsplit(":", 1)[1])
            for _ in range(120):
                try:
                    with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                        break
                except OSError:
                    time.sleep(0.15)
            else:
                raise RuntimeError("Local Paperplane server did not start")
            result = {"route_count": len(routes), "routes": [], "page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 390, "height": 844})
                page.set_default_navigation_timeout(20000)
                page.set_default_timeout(10000)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: result["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                for route in routes:
                    page.goto(base + route, wait_until="domcontentloaded")
                    page.locator("#pp-feedback-launcher").wait_for(state="attached")
                    page.wait_for_timeout(200)
                    page.evaluate("document.dispatchEvent(new CustomEvent('paperplane:auth-changed', {detail:{userId:'synthetic-id147-route-user'}}))")
                    page.wait_for_function("document.querySelector('#pp-feedback-launcher')?.hidden === false")
                    page.wait_for_timeout(100)
                    row = page.evaluate("""() => {
                      const launcher=document.querySelector('#pp-feedback-launcher'),r=launcher.getBoundingClientRect();
                      const a=[...document.querySelectorAll('.main-area h1,.main-area h2,.main-area h3,#file-list .file-row-card,.home-tool-title,.home-tool-desc')].some(e=>{
                        const s=getComputedStyle(e),b=e.getBoundingClientRect();
                        return s.display!=='none'&&s.visibility!=='hidden'&&b.width>0&&b.height>0&&b.bottom>0&&b.top<innerHeight&&b.left<r.right&&b.right>r.left&&b.top<r.bottom&&b.bottom>r.top;
                      });
                      return {attached:!!launcher,visible:!launcher.hidden&&getComputedStyle(launcher).visibility==='visible',inBounds:r.x>=0&&r.y>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,collision:a};
                    }""")
                    result["routes"].append({"route": route, **row})
                browser.close()
            result["result"] = "passed" if len(routes) == 44 and all(row["attached"] and row["visible"] and row["inBounds"] and not row["collision"] for row in result["routes"]) and not result["page_errors"] and not result["console_errors"] else "failed"
            OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps({"route_count": result["route_count"], "failed_routes": [row for row in result["routes"] if not (row["attached"] and row["visible"] and row["inBounds"] and not row["collision"])], "page_errors": result["page_errors"], "console_errors": result["console_errors"], "result": result["result"]}, indent=2))
            if result["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
