"""Check all PDF tool routes at desktop-zoom-equivalent narrow CSS widths."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
slugs = next(ast.literal_eval(node.value) for node in tree.body
             if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
results = []
failures = []
with TemporaryDirectory(prefix="paperplane-id27-zoom-layout-") as temporary:
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
        with sync_playwright() as p:
            browser = p.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.on("pageerror", lambda error: failures.append(str(error)))
            # 683px approximates a 1366 CSS-pixel desktop at 200% browser zoom;
            # 512px adds a narrower reflow stress point. They are viewport tests,
            # not a claim that Chromium's native zoom UI was invoked.
            for round_no in (1, 2):
              for width in (683, 512):
                page.set_viewport_size({"width": width, "height": 900})
                for operation, slug in slugs.items():
                    response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(40)
                    measurement = page.evaluate("""() => ({
                      viewport: innerWidth,
                      document: document.documentElement.scrollWidth,
                      body: document.body.scrollWidth,
                      title: document.title,
                      visibleOverflow: [...document.querySelectorAll('body *')]
                        .filter(el => { const r=el.getBoundingClientRect(), s=getComputedStyle(el);
                          return r.width>0 && s.visibility!=='hidden' && Number(s.opacity)>0 &&
                            r.right>0 && r.left<innerWidth && (r.left < -2 || r.right > innerWidth + 2); })
                        .slice(0, 12).map(el => ({tag:el.tagName,id:el.id,className:String(el.className).slice(0,100),
                          left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right)}))
                    })""")
                    row = {"round": round_no, "operation": operation, "route": f"/{slug}", "viewport": width,
                           "status": response.status if response else None, "layout": measurement}
                    results.append(row)
                    if not response or response.status != 200 or measurement["document"] > width + 2 or measurement["visibleOverflow"]:
                        failures.append(str(row))
            browser.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()

payload = {"route_viewports": len(results), "failed_checks": failures, "results": results,
           "note": "Equivalent narrow CSS viewport stress, not native browser zoom validation."}
out = ROOT / "reports" / "launch-audit-v23" / "browser-id27-narrow-zoom-layout.json"
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps({"route_viewports": len(results), "failures": len(failures), "evidence": str(out)}, indent=2))
assert not failures, failures[:10]
