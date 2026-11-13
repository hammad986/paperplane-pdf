from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
import server

OUT = ROOT / "reports" / "launch-audit-v5"
BASE = "http://127.0.0.1:8501"
WIDTHS = (360, 375, 390, 414, 768)
ZOOMS = (80, 100, 125, 150)


def surface(page, kind: str) -> None:
    if kind in {"/" + slug for slug in server.OPERATION_SLUGS.values()} | {"/", "/tool-desk", "/studio", "/download"}:
        page.goto(BASE + kind, wait_until="domcontentloaded")
    elif kind == "/ai-docs":
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.locator("#mob-nav-ai").click()
    elif kind == "/settings":
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.evaluate("window.openSettingsModal('account')")
    elif kind == "/pricing":
        page.goto(BASE + "/", wait_until="domcontentloaded")
        page.evaluate("document.querySelector('#upgrade-modal').hidden = false")
    page.wait_for_timeout(100)


def main() -> None:
    routes = ["/", "/tool-desk", "/studio", "/ai-docs", "/download", "/settings", "/pricing"]
    routes.extend("/" + slug for slug in server.OPERATION_SLUGS.values())
    rows: list[dict[str, object]] = []
    screenshots: list[str] = []
    console_errors: list[dict[str, str]] = []
    page_errors: list[dict[str, str]] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 375, "height": 812}, is_mobile=True, has_touch=True)
        page = context.new_page()
        page.on("console", lambda msg: console_errors.append({"url": page.url, "text": msg.text}) if msg.type == "error" else None)
        page.on("pageerror", lambda error: page_errors.append({"url": page.url, "text": str(error)}))

        for route in routes:
            surface(page, route)
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 812})
                batch = page.evaluate(
                    """({zooms,width}) => {
                      const rows=[];
                      const controls=[...document.querySelectorAll('input:not([type=hidden]),select,textarea')];
                      const missing=controls.filter(e=>!e.closest('label')&&!e.labels?.length).map(e=>e.id||e.name||e.tagName);
                      const focus=[...document.querySelectorAll('button,a,input,select,textarea,[role=button]')];
                      for (const zoom of zooms) for (const theme of ['light','dark']) for (const drawer of ['closed','open']) {
                        document.documentElement.style.zoom=`${zoom}%`;
                        document.body.classList.remove('light-mode','dark-mode');
                        document.body.classList.add(`${theme}-mode`);
                        document.querySelector('#sidebar')?.classList.toggle('mobile-open',drawer==='open');
                        const html=document.documentElement;
                        const out=[];
                        for (const e of focus) {
                          if (!(e.offsetWidth||e.offsetHeight||e.getClientRects().length) || getComputedStyle(e).visibility==='hidden') continue;
                          const r=e.getBoundingClientRect();
                          if (r.width>0 && (r.right>width+1 || r.left < -1)) out.push({tag:e.tagName,id:e.id,cls:String(e.className).slice(0,60),left:Math.round(r.left),right:Math.round(r.right)});
                        }
                        rows.push({viewport:width,zoom,theme,sidebar:drawer,documentWidth:html.scrollWidth,clientWidth:html.clientWidth,horizontalOverflow:html.scrollWidth>html.clientWidth+1,focusOutsideViewport:out.slice(0,8),controlsMissingLabels:missing.slice(0,20),toolbarAfterLabels:[...document.querySelectorAll('.studio-toolbar button')].map(b=>({text:b.innerText.trim(),pseudo:getComputedStyle(b,'::after').content})),sidebarZ:getComputedStyle(document.querySelector('#sidebar')||document.body).zIndex,toolbarZ:getComputedStyle(document.querySelector('.studio-toolbar')||document.body).zIndex});
                      }
                      return rows;
                    }""",
                    {"zooms": ZOOMS, "width": width},
                )
                for row in batch:
                    rows.append({"route": route, **row})
                if width == 375:
                    page.evaluate("({zoom}) => { document.documentElement.style.zoom=`${zoom}%`; document.body.classList.remove('light-mode'); document.body.classList.add('dark-mode'); document.querySelector('#sidebar')?.classList.remove('mobile-open'); }", {"zoom": 100})
                    page.wait_for_timeout(300)
                    shot = OUT / ("mobile-" + (route.strip("/").replace("/", "-") or "home") + "-375.png")
                    page.screenshot(path=str(shot), full_page=False)
                    screenshots.append(str(shot))

        result = {
            "base": BASE,
            "routes": routes,
            "widths": WIDTHS,
            "zoom_simulation_percent": ZOOMS,
            "themes": ["light", "dark"],
            "sidebar_states": ["closed", "open"],
            "native_browser_zoom_tested": False,
            "screenshots": screenshots,
            "console_errors": console_errors,
            "page_errors": page_errors,
            "cases": rows,
            "overflow_cases": [r for r in rows if r["horizontalOverflow"]],
            "unlabeled_controls_cases": [r for r in rows if r["controlsMissingLabels"]],
        }
        (OUT / "mobile-layout-matrix.json").write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
        print(json.dumps({
            "routes": len(routes),
            "cases": len(rows),
            "overflow_cases": len(result["overflow_cases"]),
            "unlabeled_controls_cases": len(result["unlabeled_controls_cases"]),
            "console_errors": len(console_errors),
            "page_errors": len(page_errors),
            "screenshots": len(screenshots),
            "report": str(OUT / "mobile-layout-matrix.json"),
        }, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
