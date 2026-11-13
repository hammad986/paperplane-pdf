from pathlib import Path
import json
import re

import requests
from playwright.sync_api import sync_playwright


BASE = "http://127.0.0.1:8501"
WIDTHS = [360, 375, 390, 414, 768, 1024, 1280, 1366, 1920]


def main():
    js = Path("web/assets/app.js").read_text(encoding="utf-8")
    block = js.split("const TOOL_SLUGS = {", 1)[1].split("};", 1)[0]
    tools = dict(re.findall(r"\b(\w+)\s*:\s*'([^']+)'", block))
    catalog = requests.get(f"{BASE}/api/operations", timeout=10).json()
    results = []
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=1)
        page.on("pageerror", lambda error: errors.append(str(error)))
        # Exercise the stale-session route regression: prior state is AI, but
        # each explicit tool URL must still land on that tool's own workflow.
        page.add_init_script("sessionStorage.setItem('paperplane-active-view','ai')")
        for operation, slug in tools.items():
            page.goto(f"{BASE}/{slug}", wait_until="domcontentloaded", timeout=20000)
            page.add_style_tag(content="*,*::before,*::after{transition:none!important;animation:none!important;scroll-behavior:auto!important}")
            expected_label = catalog[operation]["label"]
            page.wait_for_function("label => document.querySelector('#tool-title')?.innerText.trim() === label", arg=expected_label, timeout=12000)
            expected_view = "ai" if operation == "ai_chat" else "desk"
            active_selector = "#view-ai-studio" if expected_view == "ai" else "#view-tool-desk"
            page.locator(active_selector).wait_for(state="visible", timeout=12000)
            page.wait_for_timeout(30)
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 812 if width <= 600 else 900})
                for theme in ["light", "dark"]:
                    page.evaluate("""theme => {
                      document.body.classList.toggle('dark-mode', theme === 'dark');
                      document.body.classList.toggle('light-mode', theme === 'light');
                    }""", theme)
                    for sidebar in ["open", "closed"]:
                        page.evaluate("""state => {
                          const shell=document.querySelector('#app-shell');
                          const sb=document.querySelector('#sidebar');
                          if(innerWidth<=900){sb?.classList.toggle('mobile-open',state==='open');shell?.classList.remove('sidebar-collapsed');}
                          else{sb?.classList.remove('mobile-open');shell?.classList.toggle('sidebar-collapsed',state==='closed');}
                        }""", sidebar)
                        result = page.evaluate("""({operation,slug,width,theme,sidebar,expectedView,activeSelector}) => {
                          const desk=document.querySelector('#view-tool-desk');
                          const active=document.querySelector(activeSelector);
                          const rect=e=>{const b=e.getBoundingClientRect();return {x:Math.round(b.x),right:Math.round(b.right),width:Math.round(b.width),height:Math.round(b.height)}};
                          const h1=active?.querySelector('h1');
                          const controls=[...active.querySelectorAll('button,input,select,textarea')].filter(e=>{const b=e.getBoundingClientRect();const s=getComputedStyle(e);return b.width>0&&b.height>0&&s.display!=='none'&&s.visibility!=='hidden';});
                          const smallTargets=innerWidth<=768?controls.filter(e=>{const b=e.getBoundingClientRect();return b.height>0&&b.height<40&&e.type!=='file'&&e.type!=='hidden'&&!e.matches('input[type=checkbox],input[type=radio]')}).map(e=>({tag:e.tagName,text:(e.innerText||e.getAttribute('aria-label')||e.placeholder||'').trim().slice(0,36),height:Math.round(e.getBoundingClientRect().height)})).slice(0,8):[];
                          const visibleView=!!active&&!active.hidden&&getComputedStyle(active).display!=='none';
                          return {operation,slug,width,theme,sidebar,path:location.pathname,expectedView,visibleView,heading:h1?.innerText||null,headingRect:h1?rect(h1):null,docWidth:document.documentElement.scrollWidth,bodyWidth:document.body.scrollWidth,overflow:Math.max(document.documentElement.scrollWidth,document.body.scrollWidth)>innerWidth+1,smallTargets};
                        }""", {"operation": operation, "slug": slug, "width": width, "theme": theme, "sidebar": sidebar, "expectedView": expected_view, "activeSelector": active_selector})
                        results.append(result)
        failures = [x for x in results if x["overflow"] or not x["visibleView"] or not x["heading"]]
        touch = [x for x in results if x["smallTargets"]]
        summary = {"operations": len(tools), "cases": len(results), "widths": WIDTHS, "themes": ["light", "dark"], "sidebar_states": ["open", "closed"], "failures": failures, "small_touch_targets": touch, "page_errors": errors, "all_results": results}
        Path("reports/launch-audit-v3/operation-layout-matrix.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps({"operations": len(tools), "cases": len(results), "failure_count": len(failures), "failures": failures[:20], "small_touch_target_cases": len(touch), "small_touch_target_examples": [{"operation":x["operation"],"width":x["width"],"theme":x["theme"],"sidebar":x["sidebar"],"targets":x["smallTargets"]} for x in touch[:12]], "page_errors": errors}, ensure_ascii=False, indent=2))
        browser.close()


if __name__ == "__main__":
    main()
