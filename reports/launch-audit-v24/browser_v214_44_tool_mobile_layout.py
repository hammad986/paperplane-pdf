"""Run the current source through all 44 tool routes at narrow phone widths."""
from __future__ import annotations

import json
import socket
import sys
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "reports/launch-audit-v24/browser-v214-44-tool-mobile-layout.json"
ROUTE_MATRIX = ROOT / "reports/launch-audit-v24/route-layout-matrix.json"
sys.path.insert(0, str(ROOT / "reports/launch-audit-v14"))
import browser_acceptance_v14 as helper  # noqa: E402


def main():
    routes = [row["route"] for row in json.loads(ROUTE_MATRIX.read_text(encoding="utf-8"))["copy_routes"] if row["route"] not in ("/", "/pricing")]
    with TemporaryDirectory(prefix="paperplane-v207-44-mobile-") as temp_name:
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
            result = {"candidate": "app.js v211 / styles.css v75 / pdf_runtime.js v27 / local_pdf_worker.js v28 / service-worker v169", "route_count": len(routes), "widths": [320, 390], "checks": [], "page_errors": [], "console_errors": []}
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(channel="chrome", headless=True)
                page = browser.new_page(viewport={"width": 320, "height": 844})
                page.set_default_navigation_timeout(20000)
                page.set_default_timeout(12000)
                page.on("pageerror", lambda error: result["page_errors"].append(str(error).splitlines()[0][:200]))
                page.on("console", lambda message: result["console_errors"].append(message.text[:200]) if message.type == "error" else None)
                for width in result["widths"]:
                    page.set_viewport_size({"width": width, "height": 844})
                    for route in routes:
                        response = page.goto(base + route, wait_until="domcontentloaded")
                        page.wait_for_function("() => [...document.querySelectorAll('h1')].some(h => h.checkVisibility({checkOpacity:true,checkVisibilityCSS:true}))")
                        row = page.evaluate("""() => ({
                          viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
                          bodyWidth:document.body.scrollWidth,
                          heading:[...document.querySelectorAll('h1')].filter(h=>h.checkVisibility({checkOpacity:true,checkVisibilityCSS:true})).map(h=>h.innerText.trim()),
                          clippedControls:[...document.querySelectorAll('button,input,select,textarea,[role=button]')].filter(e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return s.display!=='none'&&s.visibility!=='hidden'&&!e.closest('[inert],[aria-hidden="true"]')&&r.width>0&&r.height>0&&(r.left<0||r.right>innerWidth)}).slice(0,8).map(e=>({label:e.getAttribute('aria-label')||e.innerText||e.id,box:{left:e.getBoundingClientRect().left,right:e.getBoundingClientRect().right}})),
                          actionLayout:(()=>{const b=document.querySelector('#run-button');if(!b||!b.checkVisibility())return null;const r=b.getBoundingClientRect();const controls=[...document.querySelectorAll('#options input,#options select,#options textarea,#options button')].filter(e=>e.checkVisibility()).map(e=>{const q=e.getBoundingClientRect();return {tag:e.tagName,type:e.type||null,top:q.top,bottom:q.bottom}});const overlaps=controls.filter(q=>q.bottom>r.top&&q.top<r.bottom);b.scrollIntoView({block:'end'});const a=b.getBoundingClientRect(),n=document.querySelector('.mobile-workspace-bar')?.getBoundingClientRect();return {initial:{top:r.top,bottom:r.bottom},controlOverlaps:overlaps,afterScroll:{top:a.top,bottom:a.bottom,navTop:n?.top??null,clearOfNav:!n||n.height===0||a.bottom<=n.top}}})(),
                          mobileSidebar:{inert:document.querySelector('#sidebar')?.inert,ariaHidden:document.querySelector('#sidebar')?.getAttribute('aria-hidden')}
                        })""")
                        row.update({"route": route, "status": response.status if response else None, "width": width})
                        sidebar_closed_accessible = row["mobileSidebar"] == {"inert": True, "ariaHidden": "true"}
                        action_clear = row["actionLayout"] is None or (not row["actionLayout"]["controlOverlaps"] and row["actionLayout"]["afterScroll"]["clearOfNav"])
                        row["result"] = "passed" if row["status"] == 200 and row["documentWidth"] <= width + 2 and row["bodyWidth"] <= width + 2 and row["heading"] and not row["clippedControls"] and sidebar_closed_accessible and action_clear else "failed"
                        result["checks"].append(row)
                browser.close()
            result["issues"] = [row for row in result["checks"] if row["result"] != "passed"]
            result["result"] = "passed" if len(routes) == 44 and len(result["checks"]) == 88 and not result["issues"] and not result["page_errors"] and not result["console_errors"] else "failed"
            OUT.write_text(json.dumps(result, indent=2), encoding="utf-8")
            print(json.dumps({"route_count": result["route_count"], "checks": len(result["checks"]), "issues": result["issues"][:15], "page_errors": result["page_errors"], "console_errors": result["console_errors"], "result": result["result"]}, indent=2))
            if result["result"] != "passed":
                raise SystemExit(1)
        finally:
            app.terminate()
            app.wait(timeout=5)


if __name__ == "__main__":
    main()
