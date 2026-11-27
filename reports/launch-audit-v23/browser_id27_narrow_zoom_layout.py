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
            # 1024px approximates the current 1536px desktop at 150% Chrome zoom;
            # 1280/1100/901 exercise compact-desktop reflow boundaries and
            # 683/512/320 add progressively narrower stress points.
            # These are viewport tests, not native Chromium zoom UI runs.
            for round_no in (1, 2):
              for width in (1280, 1100, 1024, 901, 900, 683, 512, 320):
                page.set_viewport_size({"width": width, "height": 900})
                for operation, slug in slugs.items():
                    response = page.goto(f"{base}/{slug}", wait_until="domcontentloaded", timeout=15000)
                    page.wait_for_timeout(40)
                    measurement = page.evaluate("""() => ({
                      viewport: innerWidth,
                      document: document.documentElement.scrollWidth,
                      body: document.body.scrollWidth,
                      title: document.title,
                      topbar: (() => {
                        const bar=document.querySelector('.topbar');
                        if(!bar) return null;
                        const box=el=>{const r=el.getBoundingClientRect();return {left:r.left,right:r.right,top:r.top,bottom:r.bottom,width:r.width,height:r.height}};
                        const groups=['.topbar-left','.workspace-tabs','.topbar-right']
                          .map(selector=>bar.querySelector(selector)).filter(el=>el&&getComputedStyle(el).display!=='none');
                        const boxes=groups.map(el=>({selector:el.className, ...box(el)}));
                        const overlaps=[];
                        for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
                          const a=boxes[i],b=boxes[j];
                          if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)
                            overlaps.push([a.selector,b.selector]);
                        }
                        const bounds=box(bar);
                        const outside=boxes.filter(a=>a.left<bounds.left-2||a.right>bounds.right+2||a.top<bounds.top-2||a.bottom>bounds.bottom+2).map(a=>a.selector);
                        return { ...box(bar), clientWidth:bar.clientWidth, scrollWidth:bar.scrollWidth,
                          groups:boxes.map(({selector,left,right,top,bottom})=>({selector,left:Math.round(left),right:Math.round(right),top:Math.round(top),bottom:Math.round(bottom)})), overlaps, outside };
                      })(),
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
                    header_overlap = measurement["topbar"] and measurement["topbar"]["overlaps"]
                    header_overflow = measurement["topbar"] and measurement["topbar"]["scrollWidth"] > measurement["topbar"]["clientWidth"] + 2
                    header_children_outside = measurement["topbar"] and measurement["topbar"]["outside"]
                    if not response or response.status != 200 or measurement["document"] > width + 2 or measurement["visibleOverflow"] or header_overlap or header_overflow or header_children_outside:
                        failures.append(str(row))
            browser.close()
    finally:
        app.terminate()
        try:
            app.wait(timeout=15)
        except Exception:
            app.kill()

payload = {"route_viewports": len(results), "failed_checks": failures, "results": results,
           "note": "Includes per-route topbar overlap/overflow assertions; native Chrome zoom is separately checked with Windows Computer Use."}
out = ROOT / "reports" / "launch-audit-v23" / "browser-id27-narrow-zoom-layout.json"
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(json.dumps({"route_viewports": len(results), "failures": len(failures), "evidence": str(out)}, indent=2))
assert not failures, failures[:10]
