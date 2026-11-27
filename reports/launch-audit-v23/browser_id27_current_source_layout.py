"""Responsive browser sweep for all current-source tool routes."""
from __future__ import annotations

import ast
import json
import re
from pathlib import Path
import socket
import sys
import time
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "reports" / "launch-audit-v14"))
import browser_acceptance_v14 as helper

tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
slugs = next(ast.literal_eval(node.value) for node in tree.body
             if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
app_version = re.search(r'/assets/app\.js\?v=(\d+)', (ROOT / "web" / "index.html").read_text(encoding="utf-8")).group(1)
widths = (320, 390, 820, 1366)
checks = 0
errors: list[str] = []
failures: list[dict] = []

with TemporaryDirectory(prefix="paperplane-id27-current-source-layout-") as temporary:
    app, base, _ = helper.start_server(Path(temporary) / "data")
    try:
        for _ in range(150):
            try:
                with socket.create_connection(("127.0.0.1", int(base.rsplit(":", 1)[1])), timeout=0.2):
                    break
            except OSError:
                time.sleep(0.2)
        else:
            raise RuntimeError("Local Paperplane app failed to start")

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(channel="chrome", headless=True)
            page = browser.new_page(viewport={"width": 1366, "height": 900})
            page.on("pageerror", lambda error: errors.append(str(error)))
            for round_number in (1, 2):
                for width in widths:
                    page.set_viewport_size({"width": width, "height": 844 if width < 500 else 900})
                    for operation, slug in slugs.items():
                        response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=20000)
                        assert response and response.status == 200, (operation, slug, response.status if response else None)
                        measure = page.evaluate("""() => {
                          const closed=document.querySelector('#sidebar:not(.sidebar-open)');
                          const clipped=[...document.querySelectorAll('body *')].filter(element=>{
                            if(closed&&(element===closed||closed.contains(element))) return false;
                            const style=getComputedStyle(element), rect=element.getBoundingClientRect();
                            return style.display!=='none'&&style.visibility!=='hidden'&&rect.width>0&&rect.height>0
                              &&(rect.right>innerWidth+1||rect.left < -1);
                          }).map(element=>({tag:element.tagName,id:element.id,cls:String(element.className).slice(0,80),
                            left:Math.round(element.getBoundingClientRect().left),right:Math.round(element.getBoundingClientRect().right)})).slice(0,6);
                          return {viewport:innerWidth,document:document.documentElement.scrollWidth,
                            body:document.body.scrollWidth,clipped};
                        }""")
                        checks += 1
                        if measure["document"] > width + 1 or measure["body"] > width + 1 or measure["clipped"]:
                            failures.append({"round": round_number, "width": width, "operation": operation,
                                             "slug": slug, "measure": measure})
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

report = {"base": base, "app_js": f"v{app_version}", "rounds": 2, "widths": widths,
          "routes": len(slugs), "checks": checks, "failures": failures, "page_errors": errors,
          "offscreen_closed_sidebar_excluded": True}
(OUT / "browser-id27-current-source-scroll-guard.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({key: value for key, value in report.items() if key != "failures"}, indent=2))
if failures or errors:
    print("first failure:", json.dumps(failures[0] if failures else errors[0], indent=2))
    raise SystemExit(1)
