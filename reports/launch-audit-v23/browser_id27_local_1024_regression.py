"""Verify current local candidate fixes the deployed 1024px topbar overlap."""
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
index_html = (ROOT / "web" / "index.html").read_text(encoding="utf-8")
assets = {
    "app_js": "v" + re.search(r"/assets/app\.js\?v=(\d+)", index_html).group(1),
    "styles_css": "v" + re.search(r"/assets/styles\.css\?v=(\d+)", index_html).group(1),
}
results: list[dict] = []
page_errors: list[str] = []

with TemporaryDirectory(prefix="paperplane-id27-local-1024-") as temporary:
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
            page = browser.new_page(viewport={"width": 1024, "height": 900})
            page.on("pageerror", lambda error: page_errors.append(str(error)[:300]))
            for round_number in (1, 2):
                for operation, slug in slugs.items():
                    response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=20000)
                    measurement = page.evaluate("""() => {
                      const bar=document.querySelector('.topbar');
                      const selectors=['.topbar-left','.workspace-tabs','.topbar-right'];
                      const boxes=selectors.map(selector=>bar?.querySelector(selector)).filter(el=>
                        el && getComputedStyle(el).display!=='none').map(el=>{
                          const r=el.getBoundingClientRect();
                          return {selector:el.className,left:r.left,right:r.right,top:r.top,bottom:r.bottom};
                        });
                      const overlaps=[];
                      for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
                        const a=boxes[i],b=boxes[j];
                        if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2 &&
                           Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)
                          overlaps.push([a.selector,b.selector]);
                      }
                      return {width:innerWidth,documentWidth:document.documentElement.scrollWidth,
                        topbarWidth:bar?.clientWidth,topbarScrollWidth:bar?.scrollWidth,boxes,overlaps};
                    }""")
                    results.append({"round": round_number, "operation": operation, "route": f"/{slug}",
                                    "status": response.status if response else None, "layout": measurement})
            browser.close()
    finally:
        app.terminate()
        app.wait(timeout=10)

failures = [row for row in results if row["status"] != 200 or row["layout"]["overlaps"]
            or row["layout"]["documentWidth"] > 1026
            or row["layout"]["topbarScrollWidth"] > row["layout"]["topbarWidth"] + 2]
report = {"base": base, **assets, "viewport": 1024, "routes": len(slugs), "rounds": 2,
          "checks": len(results), "failures": failures, "page_errors": page_errors,
          "result": "PASS" if not failures and not page_errors else "FAIL"}
path = OUT / "browser-id27-local-1024-regression.json"
path.write_text(json.dumps({**report, "results": results}, indent=2), encoding="utf-8")
print(json.dumps({**report, "results": f"stored in {path}"}, indent=2))
assert not failures, json.dumps(failures[:5], indent=2)
assert not page_errors, page_errors[:5]
