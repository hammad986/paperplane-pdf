"""Check tool action/navigation separation in short, zoom-equivalent viewports."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

results: list[dict] = []
errors: list[str] = []
with TemporaryDirectory(prefix="paperplane-id27-compact-height-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            for round_no in (1, 2):
                for width, height in ((877, 514), (768, 432)):
                    page = browser.new_page(viewport={"width": width, "height": height})
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    response = page.goto(f"{base}/merge-pdf", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(80)
                    layout = page.evaluate("""() => {
                      const rect = element => {
                        const r = element.getBoundingClientRect();
                        return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height};
                      };
                      const button = document.querySelector('#run-button');
                      const nav = document.querySelector('.mobile-workspace-bar');
                      const content = [document.querySelector('.tool-hero-card'),document.querySelector('#dropzone')].filter(Boolean);
                      const b = rect(button), n = rect(nav);
                      return {
                        viewport:{width:innerWidth,height:innerHeight},
                        documentWidth:document.documentElement.scrollWidth,
                        actionPosition:getComputedStyle(button).position,
                        action:b,
                        nav:n,
                        overlapsContent:content.filter(el=>{
                          const r=rect(el);
                          return Math.min(r.right,b.right)-Math.max(r.left,b.left)>2 &&
                            Math.min(r.bottom,b.bottom)-Math.max(r.top,b.top)>2;
                        }).map(el=>el.id||el.className),
                        actionNavOverlap:Math.min(b.right,n.right)-Math.max(b.left,n.left)>2 &&
                          Math.min(b.bottom,n.bottom)-Math.max(b.top,n.top)>2
                      };
                    }""")
                    result = {"round": round_no, "width": width, "height": height,
                              "status": response.status if response else None, "layout": layout}
                    results.append(result)
                    if (not response or response.status != 200 or
                            layout["documentWidth"] > width + 2 or
                            layout["actionPosition"] != "static" or
                            layout["overlapsContent"] or layout["actionNavOverlap"]):
                        errors.append(str(result))
                    page.close()
            browser.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()

payload = {"checks": results, "failures": errors,
           "note": "The short-viewport rule models Chrome native 175% and 200% zoom on the available desktop screen."}
out = ROOT / "reports" / "launch-audit-v23" / "browser-id27-compact-height-zoom.json"
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps({"checks": len(results), "failures": len(errors), "evidence": str(out)}, indent=2))
assert not errors, errors
