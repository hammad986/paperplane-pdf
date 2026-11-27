"""Read-only Chromium layout sweep against the currently deployed Paperplane site."""
from __future__ import annotations

import ast
import json
from pathlib import Path
import time

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
LIVE_BASE = "https://paperplane.qd.je"
WIDTHS = (320, 390, 683, 820, 1024, 1366, 1920)
tree = ast.parse((ROOT / "server.py").read_text(encoding="utf-8"))
slugs = next(ast.literal_eval(node.value) for node in tree.body
             if isinstance(node, ast.Assign)
             and any(isinstance(target, ast.Name) and target.id == "OPERATION_SLUGS" for target in node.targets))
results: list[dict] = []
failures: list[dict] = []
page_errors: list[str] = []
console_errors: list[str] = []
started = time.perf_counter()

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="chrome", headless=True)
    context = browser.new_context(viewport={"width": 1366, "height": 900}, service_workers="block")
    page = context.new_page()
    page.set_default_timeout(10_000)
    page.on("pageerror", lambda error: page_errors.append(str(error)[:300]))
    page.on("console", lambda message: console_errors.append(message.text[:300]) if message.type == "error" else None)
    health = page.request.get(LIVE_BASE + "/api/health", timeout=20_000)
    health_body = health.json()
    if health.status != 200 or health_body.get("status") != "ok":
        raise RuntimeError(f"Live health check failed: {health.status} {health_body}")
    asset_probe = page.goto(LIVE_BASE + "/", wait_until="domcontentloaded", timeout=30_000)
    assert asset_probe and asset_probe.status == 200
    live_app_asset = page.locator("script[src*='/assets/app.js']").first.get_attribute("src")
    live_styles_asset = page.locator("link[href*='/assets/styles.css']").first.get_attribute("href")

    for round_number in (1, 2):
        for width in WIDTHS:
            page.set_viewport_size({"width": width, "height": 900})
            for operation, slug in slugs.items():
                response = page.goto(f"{LIVE_BASE}/{slug}", wait_until="domcontentloaded", timeout=30_000)
                page.wait_for_timeout(25)
                measurement = page.evaluate("""() => {
                  const bar = document.querySelector('.topbar');
                  let topbar = null;
                  if (bar) {
                    const rect = el => { const r=el.getBoundingClientRect(); return {left:r.left,right:r.right,top:r.top,bottom:r.bottom}; };
                    const groups=['.topbar-left','.workspace-tabs','.topbar-right']
                      .map(selector=>bar.querySelector(selector)).filter(el=>el&&getComputedStyle(el).display!=='none');
                    const boxes=groups.map(el=>({selector:el.className,...rect(el)}));
                    const overlaps=[];
                    for(let i=0;i<boxes.length;i++) for(let j=i+1;j<boxes.length;j++) {
                      const a=boxes[i],b=boxes[j];
                      if(Math.min(a.right,b.right)-Math.max(a.left,b.left)>2 && Math.min(a.bottom,b.bottom)-Math.max(a.top,b.top)>2)
                        overlaps.push([a.selector,b.selector]);
                    }
                    topbar={clientWidth:bar.clientWidth,scrollWidth:bar.scrollWidth,overlaps};
                  }
                  const visibleOverflow=[...document.querySelectorAll('body *')]
                    .filter(el=>{const r=el.getBoundingClientRect(),s=getComputedStyle(el);
                      return r.width>0&&s.visibility!=='hidden'&&Number(s.opacity)>0&&r.right>0&&r.left<innerWidth&&
                        (r.left < -2 || r.right > innerWidth+2);})
                    .slice(0,8).map(el=>({tag:el.tagName,id:el.id,className:String(el.className).slice(0,80),
                      left:Math.round(el.getBoundingClientRect().left),right:Math.round(el.getBoundingClientRect().right)}));
                  return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
                    bodyWidth:document.body.scrollWidth,topbar,visibleOverflow};
                }""")
                row = {"round": round_number, "operation": operation, "route": f"/{slug}", "viewport": width,
                       "status": response.status if response else None, "layout": measurement}
                results.append(row)
                topbar = measurement["topbar"] or {}
                if (not response or response.status != 200
                        or measurement["documentWidth"] > width + 2
                        or measurement["bodyWidth"] > width + 2
                        or measurement["visibleOverflow"]
                        or topbar.get("overlaps")
                        or topbar.get("scrollWidth", 0) > topbar.get("clientWidth", 0) + 2):
                    failures.append(row)
    browser.close()

evidence = {
    "runtime": LIVE_BASE,
    "health": health_body,
    "live_app_asset": live_app_asset,
    "live_styles_asset": live_styles_asset,
    "rounds": 2,
    "widths": list(WIDTHS),
    "route_viewport_checks": len(results),
    "failures": failures,
    "page_errors": page_errors,
    "console_errors": console_errors,
    "elapsed_seconds": round(time.perf_counter() - started, 2),
    "read_only": True,
}
out = ROOT / "reports" / "launch-audit-v23" / "browser-id27-live-layout-v154-2026-11-22.json"
out.write_text(json.dumps({**evidence, "results": results}, indent=2), encoding="utf-8")
print(json.dumps({**evidence, "results": f"stored in {out}"}, indent=2))
assert not failures, json.dumps(failures[:10], indent=2)
assert not page_errors, page_errors[:10]
assert not console_errors, console_errors[:10]

